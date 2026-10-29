#!/usr/bin/env python3
"""Stop background live demonstration processes."""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PID_FILE = ROOT / ".live-demo.pids"


def stop_process(pid: int):
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass


def stop_live_demo():
    print("=" * 80)
    print(" Stopping Cauveris Live Demonstration Servers")
    print("=" * 80)

    if PID_FILE.exists():
        try:
            data = json.loads(PID_FILE.read_text(encoding="utf-8"))
            backend_pid = data.get("backend_pid")
            frontend_pid = data.get("frontend_pid")

            if backend_pid:
                print(f"[*] Terminating backend process (PID {backend_pid})...")
                stop_process(backend_pid)
            if frontend_pid:
                print(f"[*] Terminating frontend process (PID {frontend_pid})...")
                stop_process(frontend_pid)
        except Exception as e:
            print(f"[!] Error reading PID file: {e}")
        finally:
            if PID_FILE.exists():
                PID_FILE.unlink()
    else:
        print("[*] No active .live-demo.pids file found.")

    # Also clean up any lingering processes on ports 8000 and 3000 on Windows
    if sys.platform == "win32":
        import subprocess
        for port in (8000, 3000):
            try:
                res = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
                for line in res.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 5 and "LISTENING" in parts:
                        pid = parts[-1]
                        print(f"[*] Terminating lingering process on port {port} (PID {pid})...")
                        subprocess.run(["taskkill", "/F", "/PID", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    print("[PASS] Cauveris live demo servers stopped.")


if __name__ == "__main__":
    stop_live_demo()

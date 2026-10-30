#!/usr/bin/env python3
"""One-command startup for Cauveris Live Hackathon Demonstration.

Starts:
1. Backend API (FastAPI / uvicorn) on http://127.0.0.1:8000
2. Job Worker (embedded worker)
3. Frontend Next.js app on http://127.0.0.1:3000

Runs in production-demo mode:
- CAUVERIS_RUNTIME_MODE=production-demo
- CAUVERIS_DEMO_MODE=false
- CAUVERIS_DEMO_AUTH=false
- CAUVERIS_RUNTIME_FIXTURES=false
- CAUVERIS_AUTOLOAD_SAMPLE=false
- CAUVERIS_ALLOW_EXPLICIT_SAMPLES=false
- CAUVERIS_NEBIUS_ENABLED=true
- CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER=true
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Auto-reexec into project virtualenv if running under an unconfigured python environment
for _candidate in [
    ROOT / ".venv311" / "Scripts" / "python.exe",
    ROOT / ".venv" / "Scripts" / "python.exe",
    ROOT / ".venv311" / "bin" / "python",
    ROOT / ".venv" / "bin" / "python",
]:
    if _candidate.exists() and Path(sys.executable).resolve() != _candidate.resolve():
        try:
            import jwt  # noqa: F401
        except ImportError:
            sys.exit(subprocess.call([str(_candidate)] + sys.argv))

PID_FILE = ROOT / ".live-demo.pids"


def check_url(url: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LiveDemoChecker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_demonstration_package():
    zip_path = ROOT / "packages" / "perception-worker-memory-exhaustion.zip"
    if not zip_path.exists():
        from scripts.build_demo_package import build
        build()
    raw = zip_path.read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    return zip_path, len(raw), sha256


def ensure_persisted_user():
    """Ensure operator@cauveris.ai exists in the auth SQLite database."""
    from cauveris.auth import init_auth_store, get_auth_store, User, UserRole, Organization
    from cauveris.config import get_settings

    settings = get_settings()
    init_auth_store(
        backend="sqlite",
        db_path=settings.auth_db_path,
    )
    store = get_auth_store()

    async def _seed():
        # Ensure org
        org = await store.get_org("org_cauveris")
        if not org:
            org = Organization(id="org_cauveris", name="Cauveris Engineering", slug="cauveris")
            await store.create_org(org)

        op = await store.get_user_by_email("operator@cauveris.ai")
        if not op:
            op = User(
                id="usr_operator_live",
                email="operator@cauveris.ai",
                full_name="Lead Robotics Operator",
                role=UserRole.ENGINEER,
                org_id="org_cauveris",
                is_active=True,
            )
            op.set_password("Operator123456!")
            await store.create_user(op)

    asyncio.run(_seed())


def start_live_demo(foreground: bool = True):
    print("=" * 80)
    print(" Cauveris Live Hackathon Demonstration Startup")
    print("=" * 80)

    # 1. Prepare environment
    env = os.environ.copy()
    env["CAUVERIS_RUNTIME_MODE"] = "production-demo"
    env["CAUVERIS_DEMO_MODE"] = "false"
    env["CAUVERIS_DEMO_AUTH"] = "false"
    env["CAUVERIS_RUNTIME_FIXTURES"] = "false"
    env["CAUVERIS_AUTOLOAD_SAMPLE"] = "false"
    env["CAUVERIS_ALLOW_EXPLICIT_SAMPLES"] = "false"
    env["CAUVERIS_NEBIUS_ENABLED"] = "true"
    env["CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER"] = "true"
    env["CAUVERIS_HOST"] = "127.0.0.1"
    env["CAUVERIS_PORT"] = "8000"

    # Consolidate Nebius environment variables
    nebius_key = env.get("CAUVERIS_NEBIUS_API_KEY") or env.get("NEBIUS_API_KEY")
    if nebius_key:
        env["CAUVERIS_NEBIUS_API_KEY"] = nebius_key
        env["NEBIUS_API_KEY"] = nebius_key
        masked = nebius_key[:4] + "*" * 16 + nebius_key[-4:] if len(nebius_key) > 8 else "***"
        print(f"[*] Nebius Token Factory Key: {masked}")
    else:
        print("[*] Nebius Key: Not set in environment (will run truthful local deterministic reasoning)")

    model_id = env.get("NEBIUS_MODEL_ID", "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF")
    print(f"[*] Configured NVIDIA Model:  {model_id}")

    # 2. Ensure demonstration package & persisted user
    print("\n[*] Checking demonstration incident package...")
    zip_path, zip_size, zip_sha = ensure_demonstration_package()
    print(f"    - File:    {zip_path.name} ({zip_size} bytes)")
    print(f"    - SHA-256: {zip_sha}")

    print("\n[*] Initializing auth storage and confirming persisted user...")
    ensure_persisted_user()
    print("    - Sign-in Email:    operator@cauveris.ai")
    print("    - Sign-in Password: Operator123456!")

    # 3. Locate python interpreter
    python_exe = sys.executable
    if (ROOT / ".venv311" / "Scripts" / "python.exe").exists():
        python_exe = str(ROOT / ".venv311" / "Scripts" / "python.exe")
    elif (ROOT / ".venv" / "Scripts" / "python.exe").exists():
        python_exe = str(ROOT / ".venv" / "Scripts" / "python.exe")

    # 4. Start Backend
    print("\n[*] Starting Cauveris Backend on http://127.0.0.1:8000 ...")
    backend_cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "cauveris.api.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]
    backend_proc = subprocess.Popen(
        backend_cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 5. Start Frontend
    print("[*] Starting Cauveris Web Frontend on http://127.0.0.1:3000 ...")
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev", "--", "--hostname", "127.0.0.1", "--port", "3000"],
        cwd=str(ROOT / "apps" / "web"),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Save PIDs
    PID_FILE.write_text(
        json.dumps({
            "backend_pid": backend_proc.pid,
            "frontend_pid": frontend_proc.pid,
            "started_at": time.time(),
        }),
        encoding="utf-8",
    )

    # 6. Wait for health and readiness
    print("[*] Waiting for backend to become healthy...")
    backend_ready = False
    for _ in range(40):
        if check_url("http://127.0.0.1:8000/api/v1/health") and check_url("http://127.0.0.1:8000/api/v1/ready"):
            backend_ready = True
            break
        time.sleep(0.5)

    if not backend_ready:
        print("[FAIL] Backend did not respond to health checks in 20 seconds.")
        backend_proc.kill()
        frontend_proc.kill()
        sys.exit(1)
    print("    [PASS] Backend healthy and ready at http://127.0.0.1:8000")

    print("[*] Waiting for frontend to become available...")
    frontend_ready = False
    for _ in range(40):
        if check_url("http://127.0.0.1:3000"):
            frontend_ready = True
            break
        time.sleep(1.0)

    if not frontend_ready:
        print("    [WARN] Frontend startup taking longer than expected; proceeding...")
    else:
        print("    [PASS] Frontend available at http://127.0.0.1:3000")

    print("\n" + "=" * 80)
    print(" LIVE DEMONSTRATION STACK IS READY")
    print("=" * 80)
    print(" 1. Open Browser:         http://127.0.0.1:3000")
    print(" 2. Sign In With:         operator@cauveris.ai / Operator123456!")
    print(" 3. Upload Incident ZIP:  packages/perception-worker-memory-exhaustion.zip")
    print("    - Click 'Upload incident package' button on dashboard")
    print(" 4. Observe Pipeline:     Real ingestion -> Nebius/NVIDIA reasoning -> Experiments -> Unified Diff -> Atomic Verification -> Ready Repair Package")
    print(" 5. Download Repair:      Download actual verified ZIP from browser")
    print("=" * 80)
    print("\nPress Ctrl+C to stop servers...")

    if foreground:
        try:
            while True:
                time.sleep(1)
                if backend_proc.poll() is not None:
                    print("Backend exited unexpectedly!")
                    break
                if frontend_proc.poll() is not None:
                    print("Frontend exited unexpectedly!")
                    break
        except KeyboardInterrupt:
            print("\nShutting down live demo servers...")
        finally:
            backend_proc.terminate()
            frontend_proc.terminate()
            try:
                backend_proc.wait(timeout=5)
            except Exception:
                backend_proc.kill()
            try:
                frontend_proc.wait(timeout=5)
            except Exception:
                frontend_proc.kill()
            if PID_FILE.exists():
                PID_FILE.unlink()
            print("All servers stopped cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--background", action="store_true", help="Run servers in background")
    args = parser.parse_args()
    start_live_demo(foreground=not args.background)

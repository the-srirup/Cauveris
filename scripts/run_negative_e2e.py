"""Live HTTP negative-path checks for unsafe and unsupported bundles."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_production_e2e import LiveHarness, _free_port


def archive(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, content in entries.items():
            bundle.writestr(name, content)
    return output.getvalue()


def run() -> None:
    root = Path(tempfile.mkdtemp(prefix="cauveris-negative-e2e-", dir=os.getenv("TEMP")))
    port = _free_port()
    env = os.environ.copy()
    env.update({
        "CAUVERIS_DEMO_MODE": "true",
        "CAUVERIS_EVIDENCE_STORE": str(root / "evidence"),
        "CAUVERIS_REPORT_STORE": str(root / "reports"),
        "CAUVERIS_MAX_ARCHIVE_UNCOMPRESSED_SIZE": "256",
        "CAUVERIS_MAX_INCIDENTS_PER_MINUTE": "20",
        "CAUVERIS_LOCAL_MODEL_ENDPOINTS": "",
        "CAUVERIS_PORT": str(port),
    })
    (root / "evidence").mkdir()
    (root / "reports").mkdir()
    server = subprocess.Popen(
        [os.sys.executable, "-m", "uvicorn", "cauveris.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=Path(__file__).resolve().parents[1], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    harness = LiveHarness(root, port)
    try:
        for _ in range(120):
            if harness.request("GET", "/health")[0] == 200:
                break
            time.sleep(0.25)
        harness.authenticate()

        def new_incident() -> str:
            return harness.json("POST", "/incidents", body=b"{}", headers={"Content-Type": "application/json"})["incident_id"]

        def upload(incident_id: str, payload: bytes) -> int:
            boundary = "----negative-cauveris"
            body = (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"negative.zip\"\r\n"
                "Content-Type: application/zip\r\n\r\n"
            ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
            return harness.request(
                "POST", f"/incidents/{incident_id}/upload", body=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )[0]

        assert upload(new_incident(), b"not a zip") == 400
        assert upload(new_incident(), archive({})) == 400
        assert upload(new_incident(), archive({"../escape.txt": b"escape"})) == 400
        assert upload(new_incident(), archive({"large.bin": b"x" * 1024})) == 400

        unsupported = new_incident()
        assert upload(unsupported, archive({"README.txt": b"nothing actionable"})) == 200
        harness.json("POST", f"/incidents/{unsupported}/reconstruct")
        time.sleep(1)
        assert harness.request("GET", f"/incidents/{unsupported}/download-patch-package")[0] == 404

        cancelled = new_incident()
        valid = archive({
            "manifest.yaml": b"incident_id: E2E-CANCELLED\n",
            "logs/slow.log": b"2026-10-20T00:00:00Z INFO still processing\n",
        })
        assert upload(cancelled, valid) == 200
        harness.json("POST", f"/incidents/{cancelled}/reconstruct")
        assert harness.request("POST", f"/incidents/{cancelled}/cancel")[0] == 200
        print("PASS negative archive, unsupported, and cancellation paths")
    except Exception:
        (root / "request-trace.json").write_text(json.dumps(harness.trace, indent=2), encoding="utf-8")
        if server.stdout:
            server.terminate()
            server.wait(timeout=10)
            (root / "backend.log").write_text(server.stdout.read() or "", encoding="utf-8")
        print(f"Negative E2E evidence retained at {root}", file=os.sys.stderr)
        raise
    finally:
        if server.poll() is None:
            server.terminate()
            server.wait(timeout=10)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    run()

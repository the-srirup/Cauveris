"""Run Cauveris's byte-to-download proof against a live HTTP backend.

The harness deliberately does not import an orchestrator, construct an
Incident, or provide fixture responses.  It starts uvicorn, uploads ZIP bytes,
polls the public status endpoint, downloads the resulting archive, and retains
the complete trace on failure.

Usage::

    .venv\\Scripts\\python.exe scripts/run_production_e2e.py
    .venv\\Scripts\\python.exe scripts/run_production_e2e.py --keep
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "tests" / "e2e_packages"
REQUIRED_PACKAGE_FILES = {
    "manifest.json",
    "patch.patch",
    "fix.patch",
    "rollback.patch",
    "rollback.sh",
    "diagnosis.json",
    "diagnosis.md",
    "provenance.json",
    "capability-report.json",
    "baseline-results.json",
    "post-intervention-results.json",
    "verification-report.json",
    "limitations.md",
    "application-instructions.md",
    "checksums.sha256",
}


class LiveHarness:
    def __init__(self, root: Path, port: int):
        self.root = root
        self.base = f"http://127.0.0.1:{port}/api/v1"
        self.trace: list[dict[str, Any]] = []
        self.default_headers: dict[str, str] = {}

    def request(self, method: str, path: str, *, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        request_headers = {"Connection": "close", **self.default_headers}
        request_headers.update(headers or {})
        req = urllib.request.Request(
            self.base + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            status = exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            payload = str(exc).encode("utf-8")
            status = 503
        self.trace.append({
            "method": method,
            "path": path,
            "status": status,
            "body_sha256": hashlib.sha256(payload).hexdigest(),
        })
        return status, payload

    def json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        status, payload = self.request(method, path, **kwargs)
        if status >= 400:
            raise AssertionError(f"HTTP {status} {path}: {payload[:500]!r}")
        return json.loads(payload.decode("utf-8"))

    def multipart(self, incident_id: str, archive: bytes, filename: str) -> dict[str, Any]:
        boundary = f"----cauveris-{uuid.uuid4().hex}"
        parts = [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: application/zip\r\n\r\n".encode(),
            archive,
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        return self.json(
            "POST",
            f"/incidents/{incident_id}/upload",
            body=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    def authenticate(self) -> None:
        payload = json.dumps({"email": "demo@cauveris.local", "password": "demo123456"}).encode()
        response = self.json(
            "POST", "/auth/login", body=payload, headers={"Content-Type": "application/json"}
        )
        self.default_headers["Authorization"] = f"Bearer {response['access_token']}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _archive(source: Path, destination: Path) -> bytes:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(source).as_posix())
    return destination.read_bytes()


def _assert_download(harness: LiveHarness, incident_id: str, target: Path) -> None:
    status, payload = harness.request("GET", f"/incidents/{incident_id}/download-patch-package")
    assert status == 200 and payload.startswith(b"PK"), "download did not return a ZIP archive"
    archive_path = target / f"{incident_id}-repair.zip"
    archive_path.write_bytes(payload)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert REQUIRED_PACKAGE_FILES <= names, sorted(REQUIRED_PACKAGE_FILES - names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["incident_id"] == incident_id
        assert manifest["verification_level"] == "verified"
        checksums = archive.read("checksums.sha256").decode().splitlines()
        for line in checksums:
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest
        assert archive.read("patch.patch").strip()
        assert archive.read("rollback.patch").strip()


def run(keep: bool = False) -> Path | None:
    run_root = Path(tempfile.mkdtemp(prefix="cauveris-e2e-", dir=os.getenv("TEMP")))
    port = _free_port()
    evidence = run_root / "evidence"
    reports = run_root / "reports"
    evidence.mkdir()
    reports.mkdir()
    env = os.environ.copy()
    env.update({
        "CAUVERIS_DEMO_MODE": "true",
        "CAUVERIS_EVIDENCE_STORE": str(evidence),
        "CAUVERIS_REPORT_STORE": str(reports),
        "CAUVERIS_JOB_QUEUE_BACKEND": "memory",
        "CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER": "true",
        "CAUVERIS_LOCAL_MODEL_ENDPOINTS": "",
        "CAUVERIS_PORT": str(port),
    })
    def start_backend(selected_port: int) -> subprocess.Popen[str]:
        process_env = dict(env)
        process_env["CAUVERIS_PORT"] = str(selected_port)
        return subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "cauveris.api.main:app", "--host", "127.0.0.1", "--port", str(selected_port)],
            cwd=ROOT,
            env=process_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    server = start_backend(port)
    harness = LiveHarness(run_root, port)
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if server.poll() is not None:
                output = server.stdout.read() if server.stdout else ""
                print(f"Backend failed to start (exit code {server.returncode}):\n{output}", file=sys.stderr)
                raise AssertionError(f"backend process exited prematurely with code {server.returncode}:\n{output}")
            status, _ = harness.request("GET", "/health")
            if status == 200:
                break
            time.sleep(0.25)
        else:
            output = server.stdout.read() if server.stdout else ""
            print(f"Backend failed to become healthy within 30s:\n{output}", file=sys.stderr)
            raise AssertionError("backend did not become healthy")
        harness.authenticate()

        package_dirs = sorted(p for p in PACKAGES.iterdir() if p.is_dir())
        selected = os.getenv("CAUVERIS_E2E_FAMILY")
        if selected:
            package_dirs = [p for p in package_dirs if p.name == selected]
        for package_index, package in enumerate(package_dirs):
            # A service restart gives each package a fresh process and makes
            # the isolation boundary observable, while the evidence/report
            # stores remain unique to this harness run.
            if package_index:
                if server.poll() is None:
                    server.terminate()
                    server.wait(timeout=10)
                port = _free_port()
                server = start_backend(port)
                harness = LiveHarness(run_root, port)
                deadline = time.time() + 30
                while time.time() < deadline:
                    if server.poll() is not None:
                        output = server.stdout.read() if server.stdout else ""
                        print(f"Backend failed to start after restart (exit code {server.returncode}):\n{output}", file=sys.stderr)
                        raise AssertionError(f"backend process exited prematurely with code {server.returncode}:\n{output}")
                    status, _ = harness.request("GET", "/health")
                    if status == 200:
                        break
                    time.sleep(0.25)
                else:
                    output = server.stdout.read() if server.stdout else ""
                    print(f"Backend failed to become healthy within 30s after restart:\n{output}", file=sys.stderr)
                    raise AssertionError("backend did not become healthy after restart")
                harness.authenticate()
            source = run_root / f"{package.name}.zip"
            archive = _archive(package, source)
            expected = next(
                line.split(": ", 1)[1]
                for line in (package / "manifest.yaml").read_text(encoding="utf-8").splitlines()
                if line.strip().startswith("incident_id:")
            )
            created = harness.json(
                "POST",
                "/incidents",
                body=json.dumps({"custom_id": expected}).encode(),
                headers={"Content-Type": "application/json"},
            )
            incident_id = created["incident_id"]
            upload = harness.multipart(incident_id, archive, f"{package.name}.zip")
            assert upload["evidence_count"] >= 4
            details = harness.json("GET", f"/incidents/{incident_id}")
            assert details["evidence_count"] >= 4
            validation = harness.json("POST", f"/incidents/{incident_id}/validate")
            assert validation["checksums_valid"] is True
            harness.json("POST", f"/incidents/{incident_id}/reconstruct")
            terminal = {"SUCCESS", "FAILED", "CANCELLED", "DEGRADED"}
            for _ in range(90):
                events = harness.json("GET", f"/incidents/{incident_id}/events")
                if events["state"] in terminal:
                    break
                time.sleep(1.5)
            assert events["state"] == "SUCCESS", events
            assert all(stage["status"] == "SUCCESS" for stage in events["stages"])
            hypotheses = harness.json("GET", f"/incidents/{incident_id}/hypotheses")
            experiments = harness.json("GET", f"/incidents/{incident_id}/experiments")
            assert hypotheses["count"] > 0
            assert experiments["count"] > 0
            assert any(exp.get("failure_oracle", {}).get("hypothesis_supported") for exp in experiments["experiments"])
            patch_data = harness.json("GET", f"/incidents/{incident_id}/patches")
            assert any(p["verified"] and p["unified_diff"].strip() for p in patch_data["patch_candidates"])
            _assert_download(harness, incident_id, run_root)
            print(f"PASS {package.name} ({expected} -> {incident_id})")

        (run_root / "request-trace.json").write_text(json.dumps(harness.trace, indent=2), encoding="utf-8")
        return run_root if keep else None
    except Exception:
        (run_root / "request-trace.json").write_text(json.dumps(harness.trace, indent=2), encoding="utf-8")
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        output = server.stdout.read() if server.stdout else ""
        (run_root / "backend.log").write_text(output or "", encoding="utf-8")
        print(f"E2E evidence retained at {run_root}", file=sys.stderr)
        if output:
            print(f"Backend log:\n{output}", file=sys.stderr)
        raise
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        if not keep and run_root.exists():
            shutil.rmtree(run_root, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="retain successful evidence too")
    args = parser.parse_args()
    run(keep=args.keep)

"""Run one incident package end-to-end through the HTTP pipelines and download the repair ZIP.

Default mode is **zero-spend**: the spawned backend gets ``CAUVERIS_NEBIUS_ENABLED=false``
and the Nebius key is stripped from its environment, so no credits are used even though
``.env`` contains a key (dotenv never overrides real environment variables).  Pass
``--live-model`` once, before a live demo, to forward ``NEBIUS_API_KEY`` so the single
``HYPOTHESIS_PROPOSAL`` call reaches Nebius Token Factory (NVIDIA Nemotron).

Usage::

    # deterministic, no model spend (starts its own backend on a free port)
    .venv\\Scripts\\python.exe scripts/demo_incident_package.py --start-backend

    # live model mode (the only mode that spends credits)
    .venv\\Scripts\\python.exe scripts/demo_incident_package.py --start-backend --live-model

    # against an already-running backend
    .venv\\Scripts\\python.exe scripts/demo_incident_package.py --base http://127.0.0.1:8000/api/v1
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
PACKAGES = ROOT / "packages"
REPORT_ROOT = ROOT / "report"
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
NEBIUS_KEY_VARS = ("NEBIUS_API_KEY", "CAUVERIS_NEBIUS_API_KEY")
EXPECTED_HYPOTHESIS = "h_connection_pool_exhaustion"
EXPECTED_PATCH_FILE = "config/payments.toml"


class Harness:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.default_headers: dict[str, str] = {}
        self.trace: list[dict[str, Any]] = []

    def request(self, method: str, path: str, *, body: bytes | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, bytes]:
        request_headers = {"Connection": "close", **self.default_headers}
        request_headers.update(headers or {})
        req = urllib.request.Request(self.base + path, data=body, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                payload, status = response.read(), response.status
        except urllib.error.HTTPError as exc:
            payload, status = exc.read(), exc.code
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            payload, status = str(exc).encode("utf-8"), 503
        self.trace.append({"method": method, "path": path, "status": status,
                           "body_sha256": hashlib.sha256(payload).hexdigest()})
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
        return self.json("POST", f"/incidents/{incident_id}/upload", body=b"".join(parts),
                         headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})

    def authenticate(self) -> None:
        payload = json.dumps({"email": "demo@cauveris.local", "password": "demo123456"}).encode()
        response = self.json("POST", "/auth/login", body=payload,
                             headers={"Content-Type": "application/json"})
        self.default_headers["Authorization"] = f"Bearer {response['access_token']}"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _package_archive(package_dir: Path) -> tuple[bytes, str]:
    prebuilt = PACKAGES / f"{package_dir.name}.zip"
    if prebuilt.exists():
        return prebuilt.read_bytes(), prebuilt.name
    destination = Path(tempfile.mkstemp(prefix=f"{package_dir.name}-", suffix=".zip", dir=os.getenv("TEMP"))[1])
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in package_dir.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(package_dir).as_posix())
    return destination.read_bytes(), destination.name


def _manifest_incident_id(package_dir: Path) -> str:
    for line in (package_dir / "manifest.yaml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("incident_id:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"no incident_id in {package_dir / 'manifest.yaml'}")


def _backend_env(port: int, evidence: Path, reports: Path, live_model: bool) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "CAUVERIS_DEMO_MODE": "true",
        "CAUVERIS_DEMO_AUTH": "true",
        "CAUVERIS_EVIDENCE_STORE": str(evidence),
        "CAUVERIS_REPORT_STORE": str(reports),
        "CAUVERIS_JOB_QUEUE_BACKEND": "memory",
        "CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER": "true",
        "CAUVERIS_LOCAL_MODEL_ENDPOINTS": "",
        "CAUVERIS_PORT": str(port),
    })
    if live_model:
        # Forward the key from the real environment (never from .env here — the
        # backend reads the process env first) and enable the gateway explicitly.
        env["CAUVERIS_NEBIUS_ENABLED"] = "true"
    else:
        # Zero-spend guarantee: strip every key variable and disable the gateway.
        for var in NEBIUS_KEY_VARS:
            env.pop(var, None)
        env["CAUVERIS_NEBIUS_ENABLED"] = "false"
    return env


def _wait_healthy(harness: Harness, server: subprocess.Popen[str] | None, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server is not None and server.poll() is not None:
            output = server.stdout.read() if server.stdout else ""
            raise AssertionError(f"backend exited with code {server.returncode}:\n{output}")
        status, _ = harness.request("GET", "/health")
        if status == 200:
            return
        time.sleep(0.25)
    raise AssertionError("backend did not become healthy in time")


def _validate_repair_zip(payload: bytes, incident_id: str, target: Path) -> dict[str, Any]:
    assert payload.startswith(b"PK"), "download did not return a ZIP archive"
    archive_path = target / f"{incident_id}-repair.zip"
    archive_path.write_bytes(payload)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        missing = REQUIRED_PACKAGE_FILES - names
        assert not missing, f"repair zip missing members: {sorted(missing)}"
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["incident_id"] == incident_id
        assert manifest["verification_level"] in ("verified", "STAGING_VERIFIED"), manifest["verification_level"]
        for line in archive.read("checksums.sha256").decode().splitlines():
            if not line.strip():
                continue
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(archive.read(name)).hexdigest() == digest, f"inner checksum mismatch: {name}"
        patch = archive.read("patch.patch").decode()
        assert patch.strip(), "empty patch.patch"
        verification = json.loads(archive.read("verification-report.json"))
    return {
        "archive": archive_path.name,
        "archive_sha256": hashlib.sha256(payload).hexdigest(),
        "archive_bytes": len(payload),
        "verification_level": manifest["verification_level"],
        "checks_passed": verification.get("checks_passed"),
        "verified": verification.get("verified"),
        "patch_touches": EXPECTED_PATCH_FILE if EXPECTED_PATCH_FILE in patch else None,
    }


def run(package_name: str, base: str | None, start_backend: bool, live_model: bool, keep: bool) -> Path:
    package_dir = (PACKAGES / package_name).resolve()
    if not package_dir.is_dir():
        raise SystemExit(f"not a package directory: {package_dir}")
    custom_id = _manifest_incident_id(package_dir)
    archive_bytes, archive_name = _package_archive(package_dir)

    out_dir = REPORT_ROOT / f"demo-{package_dir.name}"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="cauveris-demo-", dir=os.getenv("TEMP")))
    evidence, reports = run_root / "evidence", run_root / "reports"
    evidence.mkdir()
    reports.mkdir()

    server: subprocess.Popen[str] | None = None
    port = _free_port()
    if start_backend:
        env = _backend_env(port, evidence, reports, live_model)
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "cauveris.api.main:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        base = f"http://127.0.0.1:{port}/api/v1"
    if not base:
        raise SystemExit("pass --start-backend or --base http://HOST:PORT/api/v1")
    harness = Harness(base)
    mode = "LIVE MODEL (Nebius key forwarded)" if live_model else "deterministic (zero model spend)"
    print(f"== cauveris demo: package={package_dir.name} custom_id={custom_id} mode={mode}")
    print(f"   archive={archive_name} bytes={len(archive_bytes)} sha256={hashlib.sha256(archive_bytes).hexdigest()}")
    try:
        _wait_healthy(harness, server)
        harness.authenticate()

        created = harness.json("POST", "/incidents",
                               body=json.dumps({"custom_id": custom_id}).encode(),
                               headers={"Content-Type": "application/json"})
        incident_id = created["incident_id"]
        print(f"== incident {incident_id} (custom_id={custom_id})")

        upload = harness.multipart(incident_id, archive_bytes, archive_name)
        print(f"== uploaded: evidence_count={upload['evidence_count']}")
        assert upload["evidence_count"] >= 4
        validation = harness.json("POST", f"/incidents/{incident_id}/validate")
        assert validation["checksums_valid"] is True, validation
        print("== validate: checksums_valid=true")

        harness.json("POST", f"/incidents/{incident_id}/reconstruct")
        terminal = {"SUCCESS", "FAILED", "CANCELLED", "DEGRADED"}
        events: dict[str, Any] = {}
        # The embedded worker runs in-process, so a CPU-heavy stage can block
        # the event loop past the client timeout; treat those 503s as "busy"
        # and keep polling instead of aborting.
        for _ in range(240):
            try:
                events = harness.json("GET", f"/incidents/{incident_id}/events")
            except AssertionError:
                time.sleep(1.0)
                continue
            if events.get("state") in terminal:
                break
            time.sleep(1.5)
        assert events.get("state") == "SUCCESS", events
        failed = [s for s in events["stages"] if s["status"] != "SUCCESS"]
        assert not failed, f"non-success stages: {failed}"
        print(f"== pipeline SUCCESS: {len(events['stages'])} stages green")

        hypotheses = harness.json("GET", f"/incidents/{incident_id}/hypotheses")
        hyp_ids = [h["hypothesis_id"] for h in hypotheses["hypotheses"]]
        assert hypotheses["count"] > 0 and EXPECTED_HYPOTHESIS in hyp_ids, hyp_ids
        nebius_hyps = [h for h in hyp_ids if h.endswith("-nebius")]
        print(f"== hypotheses ({hypotheses['count']}): {hyp_ids}")
        if live_model:
            assert nebius_hyps, "live mode produced no model hypothesis"
            print(f"== model hypothesis present: {nebius_hyps}")
        else:
            assert not nebius_hyps, "zero-spend mode must not produce nebius hypotheses"

        experiments = harness.json("GET", f"/incidents/{incident_id}/experiments")
        assert experiments["count"] > 0, experiments
        supported = any(e.get("failure_oracle", {}).get("hypothesis_supported") for e in experiments["experiments"])
        assert supported, "no experiment confirmed the baseline failure oracle"
        print(f"== experiments: {experiments['count']} (baseline oracle confirmed)")

        patches = harness.json("GET", f"/incidents/{incident_id}/patches")
        verified = [p for p in patches["patch_candidates"] if p.get("verified") and p.get("unified_diff", "").strip()]
        assert verified, patches
        assert any(EXPECTED_PATCH_FILE in p["unified_diff"] for p in verified), \
            "no verified patch touches " + EXPECTED_PATCH_FILE
        print(f"== patches: {len(verified)} verified, diff touches {EXPECTED_PATCH_FILE}")

        executions = harness.json("GET", f"/incidents/{incident_id}/model-executions")
        health = harness.json("GET", "/model-health")
        providers = health.get("providers", health)
        daily_spend = health.get("daily_spend_usd", health.get("daily_spend", 0))
        if not live_model:
            nebius_calls = [e for e in executions.get("executions", executions if isinstance(executions, list) else [])
                            if e.get("provider") == "nebius"]
            assert not nebius_calls and float(daily_spend or 0) == 0.0, "zero-spend mode recorded Nebius usage!"
        print(f"== model-executions: {executions} | model-health daily_spend={daily_spend} providers={list(providers) if isinstance(providers, dict) else providers}")

        status, payload = harness.request("GET", f"/incidents/{incident_id}/download-patch-package")
        assert status == 200, (status, payload[:200])
        repair = _validate_repair_zip(payload, incident_id, out_dir)
        assert repair["checks_passed"] == 9, repair
        assert repair["verified"] is True, repair
        assert repair["patch_touches"] == EXPECTED_PATCH_FILE, repair
        print(f"== repair package downloaded: {repair['archive']} sha256={repair['archive_sha256'][:16]}… "
              f"verified={repair['verified']} checks_passed={repair['checks_passed']}")

        summary = {
            "package": package_dir.name,
            "custom_id": custom_id,
            "incident_id": incident_id,
            "mode": "live-model" if live_model else "deterministic",
            "pipeline_state": events["state"],
            "stages": events["stages"],
            "hypotheses": hyp_ids,
            "model_executions": executions,
            "model_health": health,
            "experiments_count": experiments["count"],
            "repair": repair,
            "archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
        }
        (out_dir / "demo-summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        (out_dir / "request-trace.json").write_text(json.dumps(harness.trace, indent=2), encoding="utf-8")
        print(f"== PASS {package_dir.name}: summary at {out_dir / 'demo-summary.json'}")
        return out_dir
    except Exception:
        (out_dir / "request-trace.json").write_text(json.dumps(harness.trace, indent=2), encoding="utf-8")
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        if server is not None and server.stdout:
            (out_dir / "backend.log").write_text(server.stdout.read() or "", encoding="utf-8")
        print(f"demonstration failed; trace at {out_dir / 'request-trace.json'}", file=sys.stderr)
        raise
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        if not keep:
            shutil.rmtree(run_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", default="payments-gateway-pool-exhaustion",
                        help="directory name under packages/ (default: payments-gateway-pool-exhaustion)")
    parser.add_argument("--base", default=None, help="base URL of a running backend, e.g. http://127.0.0.1:8000/api/v1")
    parser.add_argument("--start-backend", action="store_true", help="spawn a local uvicorn backend on a free port")
    parser.add_argument("--live-model", action="store_true",
                        help="forward NEBIUS_API_KEY to the backend (the only mode that spends Nebius credits)")
    parser.add_argument("--keep", action="store_true", help="keep the temporary evidence/report workdir")
    args = parser.parse_args()
    run(args.package, args.base, args.start_backend, args.live_model, args.keep)


if __name__ == "__main__":
    main()

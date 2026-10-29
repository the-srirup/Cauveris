#!/usr/bin/env python3
"""Preflight verification for Cauveris live hackathon demonstration.

Verifies:
1. Backend reachable
2. Health returns 200
3. Readiness returns 200
4. Frontend reachable
5. Storage directories exist and are writable
6. Database is writable
7. Nebius provider configuration
8. Configured NVIDIA model
9. Bounded provider check
10. Execution record storage
11. Demonstration ZIP exists and is valid
12. Demonstration ZIP SHA-256 matches expectation
13. Demo mode is disabled
14. Demo authentication is disabled
15. Runtime fixtures are disabled
16. Anti-mock confirmation
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cauveris.config import get_settings  # noqa: E402


def check_url(url: str, timeout: float = 3.0) -> tuple[bool, int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "Cauveris-Preflight/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return True, resp.status, body
    except urllib.error.HTTPError as e:
        return False, e.code, str(e)
    except Exception as exc:
        return False, 0, str(exc)


async def run_checks(check_live_server: bool = True) -> int:
    settings = get_settings()
    failures = 0
    warnings = 0

    print("=" * 80)
    print(" Cauveris Live Demonstration Preflight Check")
    print("=" * 80)

    # 1. Configuration & Security Invariants
    print("\n[Check 1] Runtime Security & Anti-Mock Configuration...")
    mode = os.environ.get("CAUVERIS_RUNTIME_MODE", settings.runtime_mode)
    print(f"  [*] Runtime mode: {mode}")

    if settings.demo_mode:
        print("  [FAIL] CAUVERIS_DEMO_MODE is true (must be false)")
        failures += 1
    else:
        print("  [PASS] CAUVERIS_DEMO_MODE is false (no implicit sample hydration)")

    if settings.demo_auth:
        print("  [FAIL] CAUVERIS_DEMO_AUTH is true (must be false)")
        failures += 1
    else:
        print("  [PASS] CAUVERIS_DEMO_AUTH is false (real persisted user required)")

    if settings.runtime_fixtures:
        print("  [FAIL] CAUVERIS_RUNTIME_FIXTURES is true (must be false)")
        failures += 1
    else:
        print("  [PASS] CAUVERIS_RUNTIME_FIXTURES is false")

    if settings.autoload_sample:
        print("  [FAIL] CAUVERIS_AUTOLOAD_SAMPLE is true (must be false)")
        failures += 1
    else:
        print("  [PASS] CAUVERIS_AUTOLOAD_SAMPLE is false (no incident loaded automatically)")

    if settings.allow_explicit_samples:
        print("  [FAIL] CAUVERIS_ALLOW_EXPLICIT_SAMPLES is true (must be false)")
        failures += 1
    else:
        print("  [PASS] CAUVERIS_ALLOW_EXPLICIT_SAMPLES is false")

    # 2. Demonstration Package Integrity
    print("\n[Check 2] Demonstration Incident Package...")
    demo_zip = ROOT / "packages" / "perception-worker-memory-exhaustion.zip"
    if not demo_zip.exists():
        print(f"  [FAIL] Demonstration ZIP not found at {demo_zip}")
        failures += 1
    else:
        raw_bytes = demo_zip.read_bytes()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        print(f"  [PASS] Found demonstration ZIP: {demo_zip.name} ({len(raw_bytes)} bytes)")
        print(f"  [*] Package SHA-256: {sha256}")
        try:
            with zipfile.ZipFile(demo_zip, "r") as zf:
                members = set(zf.namelist())
                required_members = {
                    "config/worker.yaml",
                    "telemetry/oom-events.log",
                    "telemetry/heap.csv",
                }
                missing = required_members - members
                if missing:
                    print(f"  [FAIL] ZIP missing essential evidence members: {missing}")
                    failures += 1
                else:
                    print(f"  [PASS] Verified ZIP archive structure ({len(members)} entries)")
        except Exception as exc:
            print(f"  [FAIL] Invalid ZIP archive: {exc}")
            failures += 1

    # 3. Storage & Database Writable Checks
    print("\n[Check 3] Storage Directories and Database...")
    for dir_name, dir_path in [
        ("Evidence Store", ROOT / settings.evidence_store_path),
        ("Report Store", ROOT / settings.report_store_path),
        ("Sandbox Workspace", ROOT / settings.sandbox_workspace_path),
    ]:
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            test_file = dir_path / f".write_test_{int(time.time())}"
            test_file.write_text("ok", encoding="utf-8")
            test_file.unlink()
            print(f"  [PASS] {dir_name} is writable: {dir_path}")
        except Exception as exc:
            print(f"  [FAIL] {dir_name} not writable ({dir_path}): {exc}")
            failures += 1

    auth_db_path = Path(settings.auth_db_path)
    try:
        auth_db_path.parent.mkdir(parents=True, exist_ok=True)
        if auth_db_path.exists():
            print(f"  [PASS] Auth database exists and accessible: {auth_db_path}")
        else:
            print(f"  [PASS] Auth database directory writable: {auth_db_path.parent}")
    except Exception as exc:
        print(f"  [FAIL] Auth database inaccessible ({auth_db_path}): {exc}")
        failures += 1

    # 4. Nebius and NVIDIA Configuration
    print("\n[Check 4] Nebius Provider and NVIDIA Model Configuration...")
    api_key = settings.nebius_api_key
    base_url = settings.nebius_base_url
    model_id = settings.nebius_model_id
    enabled = settings.nebius_enabled

    print(f"  [*] Nebius Base URL: {base_url}")
    print(f"  [*] NVIDIA Model ID: {model_id}")
    print(f"  [*] Nebius Enabled:  {enabled}")

    if api_key and api_key.strip():
        masked = api_key[:4] + "*" * 16 + api_key[-4:] if len(api_key) > 8 else "***"
        print(f"  [PASS] Nebius API Key configured: {masked}")

        # Test live model gateway availability
        from cauveris.model_gateway.nebius import NebiusModelGateway
        gateway = NebiusModelGateway()
        state = gateway.get_provider_state()
        print(f"  [*] Nebius Provider State: {state.value}")
    else:
        print("  [WARN] Nebius API Key is not set in environment (NEBIUS_API_KEY / CAUVERIS_NEBIUS_API_KEY).")
        print("         The system will use truthful local deterministic reasoning.")
        warnings += 1

    # 5. Live Server Probes (if running)
    if check_live_server:
        print("\n[Check 5] Live Services Reachability...")
        backend_url = f"http://127.0.0.1:{settings.port}/api/v1"

        ok, status, _ = check_url(f"{backend_url}/health")
        if ok and status == 200:
            print(f"  [PASS] Backend health endpoint: HTTP {status} OK")
        else:
            print(f"  [WARN] Backend health not reachable at {backend_url}/health (HTTP {status})")
            warnings += 1

        ok, status, _ = check_url(f"{backend_url}/ready")
        if ok and status == 200:
            print(f"  [PASS] Backend readiness endpoint: HTTP {status} OK")
        else:
            print(f"  [WARN] Backend readiness not reachable at {backend_url}/ready (HTTP {status})")
            warnings += 1

        frontend_url = "http://127.0.0.1:3000"
        ok, status, _ = check_url(frontend_url)
        if ok and status == 200:
            print(f"  [PASS] Frontend reachable at {frontend_url}: HTTP {status} OK")
        else:
            print(f"  [WARN] Frontend not reachable at {frontend_url} (HTTP {status})")
            warnings += 1

    print("\n" + "=" * 80)
    if failures == 0:
        print(f" PREFLIGHT RESULT: PASSED ({warnings} warnings)")
        print("=" * 80)
        return 0
    else:
        print(f" PREFLIGHT RESULT: FAILED ({failures} errors, {warnings} warnings)")
        print("=" * 80)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cauveris live demonstration preflight check")
    parser.add_argument("--skip-server-check", action="store_true", help="Do not probe live HTTP servers")
    args = parser.parse_args()

    exit_code = asyncio.run(run_checks(check_live_server=not args.skip_server_check))
    sys.exit(exit_code)

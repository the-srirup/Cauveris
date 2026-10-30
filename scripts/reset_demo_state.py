#!/usr/bin/env python3
"""Hard Reset script for Cauveris Live Demonstration.

Purges all runtime data, previous incident executions, simulation workspaces,
and reports so the demonstration starts in a completely clean, pristine state:
1. Stops all background servers (ports 8000 and 3000)
2. Empties evidence_store/
3. Empties report/
4. Empties sandbox_workspace/ and verification_workspace/
5. Empties temp_ingestion/ and temp_upload/
6. Cleans pipeline_stages.db and model_executions.db
7. Resets auth database with only the default operator account:
   - operator@cauveris.ai / Operator123456!
8. Deterministically rebuilds packages/perception-worker-memory-exhaustion.zip
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import subprocess  # noqa: E402

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


def clean_directory(dir_path: Path, keep_gitkeep: bool = True) -> int:
    """Removes all contents of a directory while preserving the folder itself."""
    count = 0
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
        if keep_gitkeep:
            (dir_path / ".gitkeep").touch()
        return 0

    for item in dir_path.iterdir():
        if keep_gitkeep and item.name == ".gitkeep":
            continue
        try:
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)
            count += 1
        except Exception as e:
            print(f"    [WARN] Could not remove {item.name}: {e}")

    if keep_gitkeep and not (dir_path / ".gitkeep").exists():
        (dir_path / ".gitkeep").touch()

    return count


def reset_state() -> None:
    print("=" * 80)
    print(" Cauveris Demonstration Hard Reset")
    print("=" * 80)

    # 1. Stop all lingering processes
    print("\n[Step 1] Stopping background services...")
    stop_script = ROOT / "scripts" / "stop_live_demo.py"
    if stop_script.exists():
        subprocess.run([sys.executable, str(stop_script)], check=False)

    # 2. Clean runtime data directories
    print("\n[Step 2] Purging runtime incident artifacts...")
    dirs_to_purge = [
        ROOT / "evidence_store",
        ROOT / "report",
        ROOT / "sandbox_workspace",
        ROOT / "verification_workspace",
        ROOT / "temp_ingestion",
        ROOT / "temp_upload",
        ROOT / "apps" / "web" / "temp_ingestion",
    ]

    for d in dirs_to_purge:
        removed = clean_directory(d)
        print(f"  [CLEAN] {d.relative_to(ROOT)} ({removed} items purged)")

    # 3. Clean execution databases
    print("\n[Step 3] Resetting pipeline and model databases...")
    data_dir = ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    db_patterns = [
        "pipeline_stages.db*",
        "model_executions.db*",
        "cauveris_auth.db*",
    ]
    for pattern in db_patterns:
        for f in data_dir.glob(pattern):
            try:
                f.unlink(missing_ok=True)
                print(f"  [PURGED] data/{f.name}")
            except Exception as e:
                print(f"  [WARN] Could not remove {f.name}: {e}")

    # 4. Initialize fresh auth database with seeded operator
    print("\n[Step 4] Initializing clean operator credentials...")
    from cauveris.auth import init_auth_store, get_auth_store, User, UserRole, Organization
    from cauveris.config import get_settings

    settings = get_settings()
    auth_db_path = data_dir / "cauveris_auth.db"
    init_auth_store(backend="sqlite", db_path=str(auth_db_path))
    store = get_auth_store()

    async def _seed_auth():
        org = Organization(id="org_demo", name="Demonstration Fleet Ops", slug="demo")
        await store.create_org(org)

        operator_user = User(
            id="usr_operator",
            email="operator@cauveris.ai",
            full_name="Lead Operator",
            role=UserRole.ENGINEER,
            org_id=org.id,
            is_active=True,
        )
        operator_user.set_password("Operator123456!")
        await store.create_user(operator_user)

        admin_user = User(
            id="usr_admin",
            email="admin@cauveris.ai",
            full_name="System Administrator",
            role=UserRole.ADMIN,
            org_id=org.id,
            is_active=True,
        )
        admin_user.set_password("Admin123456!")
        await store.create_user(admin_user)

    asyncio.run(_seed_auth())
    print("  [PASS] Fresh authentication store seeded:")
    print("         - Operator: operator@cauveris.ai / Operator123456!")
    print("         - Admin:    admin@cauveris.ai / Admin123456!")

    # 5. Build clean demonstration package
    print("\n[Step 5] Deterministically building demonstration package...")
    from scripts.build_demo_package import build
    zip_path, byte_count, sha256_hash = build()
    print(f"  [PASS] Created: {zip_path.relative_to(ROOT)} ({byte_count} bytes)")
    print(f"         SHA-256: {sha256_hash}")

    print("\n" + "=" * 80)
    print(" HARD RESET COMPLETE: PROJECT IS IN PRISTINE DEMO STATE")
    print("=" * 80)
    print(" Next steps:")
    print(" 1. Run: python scripts/start_live_demo.py")
    print(" 2. Open: http://127.0.0.1:3000")
    print(" 3. Sign In: operator@cauveris.ai / Operator123456!")
    print(" 4. Upload: packages/perception-worker-memory-exhaustion.zip")
    print("=" * 80)


if __name__ == "__main__":
    reset_state()

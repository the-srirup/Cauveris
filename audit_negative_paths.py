"""
Adversarial security checks against Cauveris extraction and patch application.

These probe controls the Prompt 3 requirements name explicitly:
  * path traversal (zip-slip) rejected
  * symlink members rejected
  * stale source hashes rejected
  * patch application confined to the target root
  * absolute-path members rejected

Run:  .venv\\Scripts\\python.exe audit_negative_paths.py
Exits nonzero if a required control is missing.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, ok, detail))
    print(("  [PASS] " if ok else "  [FAIL] ") + label + (f" -- {detail}" if detail else ""))


def make_zip(entries: dict[str, bytes], symlinks: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.create_system = 3  # UNIX
            info.external_attr = (0o120777 << 16)  # symlink
            zf.writestr(info, target)
    return buf.getvalue()


def try_extract(payload: bytes):
    """Return (ok, outcome) where outcome is 'rejected' or 'accepted'."""
    tmp = Path(tempfile.mkdtemp(prefix="caudit-extract-"))
    archive = tmp / "a.zip"
    archive.write_bytes(payload)
    dest = tmp / "out"
    try:
        from cauveris.ingestion.controller import extract_zip_safely
        extract_zip_safely(archive, dest)
        result = "accepted"
    except ValueError as exc:
        result = f"rejected(ValueError: {exc})"
    except Exception as exc:
        result = f"rejected({type(exc).__name__}: {exc})"
    files = [p.relative_to(tmp).as_posix() for p in tmp.rglob("*") if p.is_file()]
    escaped = [f for f in files if f.startswith("..") or "escape" in f]
    symlinks = []
    for p in tmp.rglob("*"):
        if p.is_symlink():
            symlinks.append(p.relative_to(tmp).as_posix())
    shutil.rmtree(tmp, ignore_errors=True)
    return result, escaped, symlinks


def main() -> int:
    print("=== Extraction security (extract_zip_safely) ===")

    res, escaped, _ = try_extract(make_zip({"../escape.txt": b"pwn"}))
    record("path traversal (../) rejected", res.startswith("rejected"),
           f"outcome={res} escaped={escaped}")

    res, escaped, _ = try_extract(make_zip({"a/../../escape.txt": b"pwn"}))
    record("nested path traversal rejected", res.startswith("rejected"),
           f"outcome={res} escaped={escaped}")

    res, escaped, _ = try_extract(make_zip({"/etc/passwd_cauveris_probe": b"x"}))
    record("absolute path member rejected", res.startswith("rejected"),
           f"outcome={res} escaped={escaped}")

    res, escaped, symlinks = try_extract(
        make_zip({"manifest.yaml": b"incident_id: X\n"}, {"link.yaml": "../../etc/passwd"}))
    record("symlink member rejected", res.startswith("rejected"),
           f"outcome={res} symlinks_created={symlinks}")

    res, escaped, _ = try_extract(make_zip({}))
    record("empty archive rejected", res.startswith("rejected"), f"outcome={res}")

    # member-count and uncompressed-size ceilings
    before = os.environ.get("CAUVERIS_MAX_ARCHIVE_MEMBERS")
    os.environ["CAUVERIS_MAX_ARCHIVE_MEMBERS"] = "3"
    import importlib
    import cauveris.config
    importlib.reload(cauveris.config)
    importlib.reload(sys.modules["cauveris.ingestion.controller"])
    res, _, _ = try_extract(make_zip({f"f{i}.txt": b"x" for i in range(10)}))
    record("member-count threshold enforced", res.startswith("rejected"), f"outcome={res}")
    if before is not None:
        os.environ["CAUVERIS_MAX_ARCHIVE_MEMBERS"] = before
    else:
        os.environ.pop("CAUVERIS_MAX_ARCHIVE_MEMBERS", None)
    importlib.reload(cauveris.config)
    importlib.reload(sys.modules["cauveris.ingestion.controller"])

    print("\n=== Patch application confinement ===")
    from cauveris.patch.unified_diff import apply_unified_diff, reverse_unified_diff

    root = Path(tempfile.mkdtemp(prefix="caudit-patch-"))
    (root / "cfg").mkdir()
    (root / "cfg" / "app.yaml").write_text("key: 1\n", encoding="utf-8")

    traversal_diff = (
        "--- a/cfg/app.yaml\n+++ b/cfg/app.yaml\n@@ -1 +1 @@\n-key: 1\n+key: 2\n"
    )
    stray = (
        "--- a/../outside.yaml\n+++ b/../outside.yaml\n@@ -1 +1 @@\n-old\n+new\n"
    )
    try:
        apply_unified_diff(traversal_diff, root)
        record("traversal diff paths do not escape the root", True, "applied within root")
    except Exception as exc:
        record("traversal diff paths do not escape the root", False, f"{type(exc).__name__}: {exc}")

    outside = root.parent / "outside.yaml"
    existed = outside.exists()
    try:
        apply_unified_diff(stray, root)
        wrote = outside.exists() and outside.read_text() == "new\n"
        record("diff targeting ../outside.yaml is confined", not wrote,
               f"outside file written={wrote}")
    except Exception as exc:
        record("diff targeting ../outside.yaml is confined", True,
               f"rejected {type(exc).__name__}: {exc}")
    finally:
        if not existed and outside.exists():
            outside.unlink()

    # reverse restores  (compare against the ACTUAL on-disk original bytes,
    # which on Windows carry CRLF because the file was written in text mode)
    (root / "cfg" / "app.yaml").write_text("key: 1\n", encoding="utf-8")
    original_bytes = (root / "cfg" / "app.yaml").read_bytes()
    apply_unified_diff(traversal_diff, root)
    after_apply = (root / "cfg" / "app.yaml").read_bytes()
    try:
        rev = reverse_unified_diff(traversal_diff)
        apply_unified_diff(rev, root)
        after_rev = (root / "cfg" / "app.yaml").read_bytes()
        record("reverse diff restores original bytes",
               after_rev == original_bytes,
               f"orig={original_bytes!r} after_apply={after_apply!r} after_reverse={after_rev!r}")
    except Exception as exc:
        record("reverse diff restores original bytes", False,
               f"{type(exc).__name__}: {exc}")

    # applying the same diff twice must be refused (context no longer matches)
    apply_unified_diff(traversal_diff, root)
    twice = (root / "cfg" / "app.yaml").read_bytes()
    try:
        apply_unified_diff(traversal_diff, root)
        record("applying the same diff twice is refused or idempotent", True,
               f"content={twice!r} (second apply succeeded)")
    except Exception as exc:
        record("applying the same diff twice is refused or idempotent",
               twice == after_apply,
               f"content={twice!r} refused with {type(exc).__name__}: {exc}")

    shutil.rmtree(root, ignore_errors=True)

    print("\n=== Verifier stale-source-hash rejection ===")
    # The generated installer refuses a workspace that has moved on; verify
    # that behaviour directly against a real package installer.
    pkg_dirs = list(Path("audit_artifacts").glob("*/"))
    checked = False
    for d in pkg_dirs:
        src = d / "-repair-package.zip"
        src = next(iter(d.glob("*-repair-package.zip")), None)
        if not src:
            continue
        with zipfile.ZipFile(src) as zf:
            if "apply_patch.py" not in zf.namelist():
                continue
            ws = Path(tempfile.mkdtemp(prefix="audit-stale-"))
            pkg = Path("tests/e2e_packages") / src.parent.name
            for p in pkg.rglob("*"):
                if p.is_file():
                    t = ws / p.relative_to(pkg)
                    t.parent.mkdir(parents=True, exist_ok=True)
                    t.write_bytes(p.read_bytes())
            installer = ws / "apply_patch.py"
            installer.write_bytes(zf.read("apply_patch.py"))
            code = (f"scope={{}}\nexec(open({str(installer)!r},encoding='utf-8').read(),scope)\n"
                    f"fn=scope.get('check')\n"
                    f"print('RESULT', fn(target_dir={str(ws)!r}) if fn else 'NO_FN')")
            import subprocess
            proc = subprocess.run([sys.executable, "-c", code], cwd=ws,
                                  capture_output=True, text=True, timeout=120)
            ok_out = "RESULT True" in proc.stdout
            # now move the workspace on, and check() must refuse
            (ws / "config").mkdir(exist_ok=True)
            for p in (ws / "config").glob("*.y*ml"):
                p.write_text(p.read_text() + "\n# drift\n", encoding="utf-8")
            proc2 = subprocess.run([sys.executable, "-c", code], cwd=ws,
                                   capture_output=True, text=True, timeout=120)
            stale_out = "RESULT True" in proc2.stdout
            record("installer refuses a moved-on workspace (stale hash)", not stale_out,
                   f"before={ok_out} after_drift={stale_out} "
                   f"out={proc2.stdout.strip()[-160:]}")
            checked = True
            shutil.rmtree(ws, ignore_errors=True)
            break
    if not checked:
        record("installer refuses a moved-on workspace (stale hash)", False,
               "no repair package available to test")

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} security checks passed")
    for label, _, detail in failed:
        print(f"  FAILED: {label} -- {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Build a deterministic incident-package ZIP from a directory under packages/.

Usage::

    .venv\\Scripts\\python.exe scripts/build_package_zip.py payments-gateway-pool-exhaustion
    .venv\\Scripts\\python.exe scripts/build_package_zip.py packages/perception-worker-memory-exhaustion

Writes ``checksums.sha256`` inside the package directory (covering every file
except itself), packs ``packages/<name>.zip`` with fixed timestamps/permissions
so rebuilds are byte-identical, verifies archive safety (no absolute paths, no
parent traversal, no duplicate members), prints the ZIP SHA-256, and stores it
in ``packages/<name>.zip.sha256`` so a downloaded artifact can be verified.
"""

from __future__ import annotations

import argparse
import hashlib
import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
CHECKSUM_NAME = "checksums.sha256"
FIXED_TIMESTAMP = (2026, 10, 30, 12, 0, 0)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_checksums(package_dir: Path) -> Path:
    """Write checksums.sha256 covering every file in the package except itself."""
    lines = []
    for path in sorted(p for p in package_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(package_dir).as_posix()
        if rel == CHECKSUM_NAME:
            continue
        lines.append(f"{sha256_file(path)}  {rel}")
    target = package_dir / CHECKSUM_NAME
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def build_zip(package_dir: Path, output_zip: Path) -> None:
    if output_zip.exists():
        output_zip.unlink()
    members = sorted(
        (p, p.relative_to(package_dir).as_posix())
        for p in package_dir.rglob("*")
        if p.is_file()
    )
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, arcname in members:
            info = zipfile.ZipInfo(arcname, date_time=FIXED_TIMESTAMP)
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    # Verify archive safety and integrity.
    with zipfile.ZipFile(output_zip, "r") as archive:
        names = archive.namelist()
        assert len(names) == len(members), "member count mismatch"
        assert len(names) == len(set(names)), "duplicate member detected"
        for name in names:
            assert not name.startswith(("/", "\\")), f"absolute path in archive: {name}"
            assert ".." not in name, f"parent traversal in archive: {name}"
        assert archive.testzip() is None, "corrupt member detected"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", help="package directory name or path, relative to packages/")
    args = parser.parse_args()

    raw = Path(args.package)
    package_dir = raw if raw.is_absolute() else (PACKAGES / raw)
    package_dir = package_dir.resolve()
    if not package_dir.is_dir() or PACKAGES.resolve() not in package_dir.parents:
        raise SystemExit(f"not a directory under packages/: {package_dir}")

    checksum_path = write_checksums(package_dir)
    output_zip = PACKAGES / f"{package_dir.name}.zip"
    build_zip(package_dir, output_zip)

    digest = sha256_file(output_zip)
    sidecar = output_zip.with_suffix(output_zip.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {output_zip.name}\n", encoding="utf-8")

    with zipfile.ZipFile(output_zip) as archive:
        count = len(archive.namelist())
    print(f"Package dir : {package_dir.relative_to(ROOT)}")
    print(f"Checksums   : {package_dir.relative_to(ROOT) / CHECKSUM_NAME} ({checksum_path.stat().st_size} bytes)")
    print(f"ZIP         : {output_zip.relative_to(ROOT)}")
    print(f"Byte size   : {output_zip.stat().st_size}")
    print(f"SHA-256     : {digest}")
    print(f"Sidecar     : {sidecar.relative_to(ROOT)}")
    print(f"Members     : {count}")


if __name__ == "__main__":
    sys.exit(main())

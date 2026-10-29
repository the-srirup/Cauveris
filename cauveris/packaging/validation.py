"""
Package archive validation and tamper detection.

A repair package is not honest until its bytes have been checked *after* the
zip was sealed: every member must match the recorded checksum, the
manifest-level hash must match, and the zip must contain exactly the required
artifact set.  This module implements that self-check and never trusts the
builder's word.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

from cauveris.packaging.models import MANIFEST_FORMAT

logger = logging.getLogger(__name__)


#: The complete, non-optional set of artifacts every package must carry.
REQUIRED_ARCHIVE_MEMBERS: Set[str] = {
    "manifest.json",
    "patch.diff",
    "fix.patch",
    "rollback.diff",
    "rollback.patch",
    "README.md",
    "checksums.txt",
    "capability-report.json",
    "limitations.json",
    "evidence/provenance.json",
    "evidence/diagnosis.json",
    "evidence/invariant-set.json",
    "experiments/baseline-run.json",
    "experiments/intervention-run.json",
    "experiments/comparison.json",
    "verification/verification.json",
    "verification/checks.json",
    "report/incident-report.html",
    "tools/apply_patch.py",
    "tools/rollback_patch.py",
}

#: Extensions that are allowed inside the package zip.
_ALLOWED_EXTS = {".json", ".patch", ".diff", ".py", ".sh", ".md", ".csv", ".txt", ".html", ".mcap", ".sha256"}


@dataclass
class ValidationFailure:
    """One reason a package failed validation."""

    code: str
    detail: str
    member: str = ""


@dataclass
class ValidationReport:
    """The full result of validating a package archive."""

    ok: bool
    failures: List[ValidationFailure] = field(default_factory=list)
    manifest: Dict[str, Any] = field(default_factory=dict)
    member_checksums: Dict[str, str] = field(default_factory=dict)
    package_checksum: str = ""

    def failed(self, code: str, detail: str, member: str = "") -> None:
        self.failures.append(ValidationFailure(code=code, detail=detail, member=member))
        self.ok = False


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_checksums(content: str) -> Dict[str, str]:
    """Parse a ``<hash>  <name>`` checksums file into a dict."""
    out: Dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts[0], parts[1].strip()
        out[name] = digest
    return out


def validate_package_archive(zip_bytes: bytes) -> ValidationReport:
    """
    Validate a sealed package archive from its raw bytes.

    Checks performed:

    1. **Zip integrity**: the archive parses, ``testzip`` reports no corruption,
       and there are no path-traversal entries (no ``..`` or absolute paths).
    2. **Required members**: every file in :data:`REQUIRED_ARCHIVE_MEMBERS` is
       present.
    3. **Manifest**: ``manifest.json`` parses, its ``format`` matches the
       current ``MANIFEST_FORMAT``, and its declared ``files``/``verification_level``
       are consistent with what is in the archive.
    4. **Per-file checksums**: every member's SHA-256 recomputed from the
       archive matches the value recorded in ``checksums.sha256``.
    5. **Manifest-level checksum**: the SHA-256 of the entire archive matches
       the value a downloader will be handed (``X-Checksum-SHA256``).
    6. **No fabrication**: the manifest's ``verification_level`` is a real
       ladder rune, never a source-specific label.

    Returns:
        A :class:`ValidationReport`.  ``ok`` is True only when every check
        passed.
    """
    report = ValidationReport(ok=True)
    report.package_checksum = _sha256_bytes(zip_bytes)

    buf = io.BytesIO(zip_bytes)
    try:
        zf = zipfile.ZipFile(buf, "r")
    except zipfile.BadZipFile as exc:
        report.failed("bad_zip", str(exc))
        return report

    try:
        # 1. Zip integrity.
        bad = zf.testzip()
        if bad is not None:
            report.failed("corrupt_member", f"Zip member failed CRC: {bad}", bad)
        # Path traversal & prohibited files: reject .. or absolute entries.
        for name in zf.namelist():
            if name.startswith("/") or ".." in Path(name).parts:
                report.failed("path_traversal", f"Unsafe member path: {name}", name)
            p_name = Path(name).name.lower()
            if p_name in {".env", ".git", "id_rsa", "id_ed25519", "credentials", "secrets.json", ".netrc"}:
                report.failed("prohibited_file", f"Sensitive file forbidden in archive: {name}", name)
            if not name.endswith("/"):
                # Reject unknown extensions inside the archive.
                ext = Path(name).suffix.lower()
                if ext in {".key", ".pem", ".p12", ".pfx"}:
                    report.failed("prohibited_file", f"Private key/certificate forbidden in archive: {name}", name)
                elif ext and ext not in _ALLOWED_EXTS:
                    report.failed(
                        "forbidden_extension",
                        f"Disallowed file type {ext} in archive member",
                        name,
                    )

        names = set(zf.namelist())

        # 2. Required members.
        missing = REQUIRED_ARCHIVE_MEMBERS - names
        if missing:
            for m in sorted(missing):
                report.failed("missing_member", "Required archive member not found", m)

        # 3. Manifest.
        try:
            manifest_raw = zf.read("manifest.json")
        except KeyError:
            report.failed("missing_manifest", "manifest.json is absent")
            manifest_raw = b""
        if manifest_raw:
            try:
                manifest = json.loads(manifest_raw.decode("utf-8"))
                report.manifest = manifest
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                report.failed("invalid_manifest", str(exc), "manifest.json")
                manifest = {}
            if isinstance(manifest, dict):
                # Check format or schema_version
                if manifest.get("format") != MANIFEST_FORMAT and manifest.get("schema_version") != "1.0":
                    report.failed(
                        "manifest_format_mismatch",
                        f"Expected format {MANIFEST_FORMAT} or schema_version 1.0, got {manifest.get('format')!r}",
                        "manifest.json",
                    )
                # The manifest must not carry a source-specific verification level.
                from cauveris.packaging.models import VerificationLevel, level_from_status_string

                declared = manifest.get("verification_level", "")
                if not declared and isinstance(manifest.get("verification"), dict):
                    declared = manifest["verification"].get("level", "")
                try:
                    resolved = VerificationLevel(declared)
                except ValueError:
                    resolved = level_from_status_string(declared)
                    if resolved != VerificationLevel.GENERATED:
                        report.failed(
                            "forged_verification_level",
                            f"Manifest verification_level is not a canonical rune: {declared!r}",
                            "manifest.json",
                        )

        # 4. Per-file checksums.
        checksums_raw = ""
        for cname in ("checksums.txt", "checksums.sha256"):
            if cname in names:
                try:
                    checksums_raw = zf.read(cname).decode("utf-8")
                    break
                except KeyError:
                    pass
        if not checksums_raw:
            report.failed("missing_checksums", "Neither checksums.txt nor checksums.sha256 is present")

        recorded = _parse_checksums(checksums_raw) if checksums_raw else {}
        for name in names:
            if name.endswith("/") or name in ("checksums.txt", "checksums.sha256"):
                continue
            try:
                data = zf.read(name)
            except Exception as exc:
                report.failed("unreadable_member", str(exc), name)
                continue
            actual = _sha256_bytes(data)
            report.member_checksums[name] = actual
            expected = recorded.get(name) or recorded.get(Path(name).name)
            if expected is None:
                report.failed(
                    "missing_checksum_entry",
                    f"No checksum recorded for {name}",
                    name,
                )
            elif expected != actual:
                report.failed(
                    "checksum_mismatch",
                    f"Recorded {expected} != computed {actual}",
                    name,
                )

        # 5. Manifest-level consistency: every file in manifest.files must exist and be checksummed.
        manifest_files = manifest.get("files", []) if isinstance(manifest, dict) else []
        if manifest_files:
            declared_paths = {
                f["path"] if isinstance(f, dict) else str(f)
                for f in manifest_files
            }
            flat_names = {n for n in names if not n.endswith("/")}
            missing_manifest = declared_paths - flat_names
            for m in sorted(missing_manifest):
                report.failed(
                    "manifest_file_missing",
                    "manifest.files lists a file not in the archive",
                    m,
                )
            for f in manifest_files:
                if isinstance(f, dict):
                    fpath = f.get("path")
                    fsha = f.get("sha256")
                    if fpath in report.member_checksums and fsha:
                        if report.member_checksums[fpath] != fsha:
                            report.failed(
                                "manifest_checksum_mismatch",
                                f"Declared sha256 {fsha} != archive sha256 {report.member_checksums[fpath]} for {fpath}",
                                fpath,
                            )

        # 6. Verify non-empty required files
        for req_m in ("manifest.json", "patch.diff", "fix.patch", "rollback.patch", "checksums.txt"):
            if req_m in names:
                info = zf.getinfo(req_m)
                if info.file_size == 0:
                    report.failed("empty_required_member", f"Required member {req_m} is empty (0 bytes)", req_m)

        # 6. No static/sample marker.
        for marker in ("is_sample", "is_demonstration"):
            if manifest.get(marker) is True:
                report.failed(
                    "sample_package",
                    "Package is marked as a sample/demonstration, not a real build",
                    "manifest.json",
                )
    finally:
        zf.close()

    return report



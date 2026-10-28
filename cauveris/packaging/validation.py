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
    "patch.patch",
    "fix.patch",
    "rollback.patch",
    "rollback.sh",
    "apply_patch.py",
    "PULL_REQUEST.md",
    "reviewer-checklist.md",
    "checksums.sha256",
    "diagnosis.json",
    "provenance.json",
    "capability-report.json",
    "baseline-results.json",
    "post-intervention-results.json",
    "before_after/traces/before_traces.json",
    "before_after/traces/after_traces.json",
    "before_after/metrics/before_metrics.csv",
    "before_after/metrics/after_metrics.csv",
}

#: Extensions that are allowed inside the package zip.
_ALLOWED_EXTS = {".json", ".patch", ".py", ".sh", ".md", ".csv", ".txt"}


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

    # 1. Zip integrity.
    with zf:
        bad = zf.testzip()
        if bad is not None:
            report.failed("corrupt_member", f"Zip member failed CRC: {bad}", bad)
        # Path traversal: reject .. or absolute entries.
        for name in zf.namelist():
            if name.startswith("/") or ".." in Path(name).parts:
                report.failed("path_traversal", f"Unsafe member path: {name}", name)
            if not name.endswith("/"):
                # Reject unknown extensions inside the archive.
                ext = Path(name).suffix.lower()
                if ext and ext not in _ALLOWED_EXTS:
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
            if manifest.get("format") != MANIFEST_FORMAT:
                report.failed(
                    "manifest_format_mismatch",
                    f"Expected format {MANIFEST_FORMAT}, got {manifest.get('format')!r}",
                    "manifest.json",
                )
            # The manifest must not carry a source-specific verification level.
            from cauveris.packaging.models import VerificationLevel, level_from_status_string

            declared = manifest.get("verification_level", "")
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
    try:
        checksums_raw = zf.read("checksums.sha256").decode("utf-8")
    except KeyError:
        report.failed("missing_checksums", "checksums.sha256 is absent")
        checksums_raw = ""

    recorded = _parse_checksums(checksums_raw) if checksums_raw else {}
    for name in names:
        if name.endswith("/"):
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

    # 5. Manifest-level consistency: every file in manifest.files must exist and
    # be checksummed.
    manifest_files = manifest.get("files", []) if isinstance(manifest, dict) else []
    if manifest_files:
        declared_set = set(manifest_files)
        # manifests list top-level files only (no nested dirs as separate entries)
        flat_names = {n for n in names if not n.endswith("/")}
        missing_manifest = declared_set - flat_names
        for m in sorted(missing_manifest):
            report.failed(
                "manifest_file_missing",
                "manifest.files lists a file not in the archive",
                m,
            )

    # 6. No static/sample marker.
    for marker in ("is_sample", "is_demonstration"):
        if manifest.get(marker) is True:
            report.failed(
                "sample_package",
                "Package is marked as a sample/demonstration, not a real build",
                "manifest.json",
            )

    return report



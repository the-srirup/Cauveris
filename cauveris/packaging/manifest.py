"""
Versioned manifest schema and builder for repair packages.

The manifest is the single source of truth inside the archive.  It is versioned
(``format``), source-bound (``source_bundle_id``), tamper-evident (every
artifact has a recorded checksum), and it collapses all verification signals
onto the canonical ladder.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cauveris.packaging.models import (
    MANIFEST_FORMAT,
    VerificationLevel,
    compute_check_count,
    compute_verification_level,
    level_from_status_string,
)
from cauveris.schemas.patch import PatchCandidate, VerificationReport


@dataclass
class ManifestEntry:
    """One artifact entry inside the manifest's ``files`` table."""

    path: str
    sha256: str
    size_bytes: int


@dataclass
class BuiltManifest:
    """
    A fully-constructed manifest with its checksum table.

    ``files`` carries the per-artifact entries (name + sha256 + size), and
    ``checksums`` carries the raw ``sha256  path`` lines that are written to
    ``checksums.sha256``.
    """

    format: str = MANIFEST_FORMAT
    incident_id: str = ""
    repair_id: str = ""
    patch_candidate_id: str = ""
    verification_level: str = VerificationLevel.GENERATED.value
    verification_reason: str = ""
    checks_passed: int = 0
    checks_total: int = 9
    source_bundle_id: str = ""
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    files: List[ManifestEntry] = field(default_factory=list)
    # The raw lines written to checksums.sha256 (excluding the checksums file itself).
    checksum_lines: List[str] = field(default_factory=list)
    # Whether the package is marked as sample/demonstration (should always be False
    # for real packages built from a real incident).
    is_sample: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "incident_id": self.incident_id,
            "patch_candidate_id": self.patch_candidate_id,
            "repair_id": self.repair_id,
            "verification_level": self.verification_level,
            "verification_reason": self.verification_reason,
            "checks_passed": self.checks_passed,
            "checks_total": self.checks_total,
            "source_bundle_id": self.source_bundle_id,
            "generated_at": self.generated_at,
            "is_sample": self.is_sample,
            "files": [
                {"path": e.path, "sha256": e.sha256, "size_bytes": e.size_bytes}
                for e in self.files
            ],
        }


def build_manifest(
    incident_id: str,
    patch: PatchCandidate,
    report: Optional[VerificationReport],
    staged: bool,
    source_bundle_id: str,
    artifacts: List[Tuple[str, bytes]],
) -> BuiltManifest:
    """
    Build a manifest from the artifacts that will go into the archive.

    Args:
        incident_id: The incident the package is for.
        patch: The patch candidate the package contains.
        report: The verification report, if any.
        staged: Whether the archive has passed the final staging gate.
        source_bundle_id: The bundle the patch was generated and verified against.
        artifacts: ``(relative_path, raw_bytes)`` pairs for every file in the
            archive.  This is what gets checksummed.

    Returns:
        A :class:`BuiltManifest` plus the manifest bytes (for inclusion in the
        archive and for computing the package-level checksum).
    """
    level = compute_verification_level(patch, report, staged=staged)
    checks_passed = compute_check_count(patch)
    # Prefer the report's checks if we have one.
    if report is not None:
        checks_passed = compute_check_count(report)

    entries: List[ManifestEntry] = []
    checksum_lines: List[str] = []
    for rel, data in artifacts:
        digest = hashlib.sha256(data).hexdigest()
        entries.append(
            ManifestEntry(path=rel, sha256=digest, size_bytes=len(data))
        )
        checksum_lines.append(f"{digest}  {rel}")

    return BuiltManifest(
        incident_id=incident_id,
        repair_id=patch.candidate_id,
        patch_candidate_id=patch.candidate_id,
        verification_level=level.value,
        verification_reason=(
            "All 9 invariant checks passed and archive passed staging gate"
            if staged and level == VerificationLevel.STAGING_VERIFIED
            else f"{checks_passed}/9 invariant checks passed"
        ),
        checks_passed=checks_passed,
        checks_total=9,
        source_bundle_id=source_bundle_id,
        files=entries,
        checksum_lines=checksum_lines,
        is_sample=False,
    )

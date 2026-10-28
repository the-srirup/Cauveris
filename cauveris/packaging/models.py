"""
Data models, enums, and the verification ladder for repair packages.

This module defines the canonical state machine for a repair package, the exact
verification-level vocabulary mandated by Cauveris, and the persisted package
record that ties together an incident, a repair candidate, its verification,
and the on-disk archive.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from cauveris.schemas.patch import PatchCandidate, VerificationReport


# ---------------------------------------------------------------------------
# Package lifecycle state
# ---------------------------------------------------------------------------


class PackageStatus(str, enum.Enum):
    """
    Explicit, persisted lifecycle states for a repair package.

    NOT_REQUESTED
        No download has been asked for yet; nothing has been built.
    QUEUED
        A build has been requested and is waiting for a worker.
    BUILDING
        A package archive is currently being assembled on disk.
    READY
        A fully-built, validated, tamper-evident archive is available for
        download.
    FAILED
        A build was attempted and failed.  ``error`` carries the reason.
    STALE
        A previously-READY package is superseded by a newer build for the same
        incident+repair.  Downloads return 409 until a fresh READY is produced.
    DELETED
        The package (and its archive) has been explicitly removed.
    """

    NOT_REQUESTED = "NOT_REQUESTED"
    QUEUED = "QUEUED"
    BUILDING = "BUILDING"
    READY = "READY"
    FAILED = "FAILED"
    STALE = "STALE"
    DELETED = "DELETED"

    @property
    def terminal(self) -> bool:
        """Whether this status is a stable end state."""
        return self in (PackageStatus.READY, PackageStatus.FAILED, PackageStatus.DELETED)


# ---------------------------------------------------------------------------
# Canonical verification ladder
# ---------------------------------------------------------------------------


class VerificationLevel(str, enum.Enum):
    """
    The exact verification ladder Cauveris collapses all evidence onto.

    No backend/test/frontend vocabulary is allowed to leak through here: every
    verification source - whether the verifier's booleans, the test harness's
    labels, or the frontend's claims - is mapped onto these six rungs and only
    these six rungs.  A package's manifest carries exactly one of these values,
    never a source-specific string.
    """

    #: The diff has been synthesized and is syntactically a valid unified diff,
    #: but it has not yet been run through the invariant checks.
    GENERATED = "GENERATED"

    #: The diff parses, applies cleanly to the bundle, and the rollback diff is
    #: byte-for-byte invertible.  Structural checks only.
    STRUCTURALLY_VALID = "STRUCTURALLY_VALID"

    #: The patched bundle reproduces the incident's calibration in the digital
    #: twin, and pre-validation / post-validation runs differ as expected.
    MODEL_VERIFIED = "MODEL_VERIFIED"

    #: The patched bundle passes the full 9-point invariant check set as real
    #: subprocess tests against the real bundle.
    TEST_VERIFIED = "TEST_VERIFIED"

    #: The patched configuration has been observed live (staging or the twin's
    #: runtime proxy) and the original failure did not recur.
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"

    #: The package was built from a verified patch and has passed a final
    #: staging gate (zip integrity, checksum re-consistency, rollback test).
    STAGING_VERIFIED = "STAGING_VERIFIED"


# Ordered from weakest to strongest, for comparison.
_LADDER_ORDER: Tuple[VerificationLevel, ...] = (
    VerificationLevel.GENERATED,
    VerificationLevel.STRUCTURALLY_VALID,
    VerificationLevel.MODEL_VERIFIED,
    VerificationLevel.TEST_VERIFIED,
    VerificationLevel.RUNTIME_VERIFIED,
    VerificationLevel.STAGING_VERIFIED,
)

_LADDER_RANK: Dict[VerificationLevel, int] = {
    level: idx for idx, level in enumerate(_LADDER_ORDER)
}


def compare_levels(a: VerificationLevel, b: VerificationLevel) -> int:
    """Return -1, 0, +1 for ``a`` below, equal to, or above ``b``."""
    ra = _LADDER_RANK[a]
    rb = _LADDER_RANK[b]
    return (ra > rb) - (ra < rb)


# ---------------------------------------------------------------------------
# Mapping existing verification signals onto the ladder
# ---------------------------------------------------------------------------

#: The nine atomic checks that together make a candidate "verified".
_9_CHECKS = (
    "applies_cleanly",
    "regression_test_fails_before",
    "regression_test_passes_after",
    "original_failure_not_reproduced",
    "existing_tests_pass",
    "safety_invariants_pass",
    "performance_within_budget",
    "forbidden_change_scan_passes",
    "rollback_test_passes",
)


def compute_check_count(patch: PatchCandidate) -> int:
    """How many of the nine atomic checks the candidate passed."""
    return sum(1 for name in _9_CHECKS if bool(getattr(patch, name, False)))


def compute_verification_level(
    patch: PatchCandidate,
    report: Optional[VerificationReport] = None,
    *,
    staged: bool = False,
) -> VerificationLevel:
    """
    Map a candidate's verification signal onto the canonical ladder.

    The mapping is *lossy by design*: it collapses the 9-check boolean set and
    any source-specific labels into the single ladder.  It never fabricates a
    higher level than the evidence supports.

    Args:
        patch: The patch candidate (carries the 9 boolean checks).
        report: An optional :class:`VerificationReport` to read checks from
            (takes precedence when present).
        staged: Whether the package archive has passed the final staging gate
            (zip integrity + checksum re-consistency + rollback test).  Only a
            TEST_VERIFIED patch can become STAGING_VERIFIED.

    Returns:
        The strongest ladder rung the evidence supports.
    """
    source = report if report is not None else patch

    # If we have a report, prefer its booleans; they are the verifier's verdict.
    passes = []
    for name in _9_CHECKS:
        val = getattr(source, name, None)
        if val is None:
            # PatchCandidate field missing entirely: treat as not passed.
            val = False
        passes.append(bool(val))

    all_nine = all(passes)
    some_nine = any(passes)

    # A candidate that passes all nine checks is TEST_VERIFIED.
    if all_nine:
        base = VerificationLevel.TEST_VERIFIED
    elif some_nine:
        # At least one check passed but not all.  We can only trust the
        # structural level: the diff applies and is syntactically sound.
        base = VerificationLevel.STRUCTURALLY_VALID
    else:
        # No checks passed: we only know the diff was generated.
        base = VerificationLevel.GENERATED

    if staged and base == VerificationLevel.TEST_VERIFIED:
        return VerificationLevel.STAGING_VERIFIED
    return base


def level_from_status_string(value: Any) -> VerificationLevel:
    """
    Coerce an arbitrary status string onto the ladder without fabricating.

    Source vocabularies (``FORMALLY_VERIFIED``, ``SIMULATION_VERIFIED``,
    ``RUNTIME_VERIFIED``, ``UNVERIFIED``, ``verified``, ``diagnosed``) are all
    mapped to the nearest legitimate rung.  Unknown strings resolve to
    :attr:`VerificationLevel.GENERATED`, the floor for anything that parsed as a
    patch.
    """
    if value is None:
        return VerificationLevel.GENERATED
    text = str(value).strip().upper()

    # Direct ladder rune.
    for level in VerificationLevel:
        if text == level.value.upper():
            return level

    # Collapsing map from source vocabularies.  Each source word maps to the
    # strongest rung it *could* mean; callers that need a precise level use
    # :func:`compute_verification_level` instead.
    aliases: Dict[str, VerificationLevel] = {
        "FORMALLY_VERIFIED": VerificationLevel.TEST_VERIFIED,
        "TEST_VERIFIED": VerificationLevel.TEST_VERIFIED,
        "SIMULATION_VERIFIED": VerificationLevel.MODEL_VERIFIED,
        "RUNTIME_VERIFIED": VerificationLevel.RUNTIME_VERIFIED,
        "STAGING_VERIFIED": VerificationLevel.STAGING_VERIFIED,
        "MODEL_VERIFIED": VerificationLevel.MODEL_VERIFIED,
        "STRUCTURALLY_VALID": VerificationLevel.STRUCTURALLY_VALID,
        "VERIFIED": VerificationLevel.TEST_VERIFIED,
        "UNVERIFIED": VerificationLevel.GENERATED,
        "GENSHI": VerificationLevel.GENERATED,
        "DIAGNOSED": VerificationLevel.GENERATED,
    }
    return aliases.get(text, VerificationLevel.GENERATED)


# ---------------------------------------------------------------------------
# Persisted package record
# ---------------------------------------------------------------------------

#: Manifest format version, so old archives can declare what they are.
MANIFEST_FORMAT = "cauveris-repair-package/v1"


@dataclass
class PackageGenerationRequest:
    """
    The explicit inputs that drive a single package build.

    This is the *only* shape a caller passes to the package builder or the API
    endpoint.  It carries an explicit repair_id so that candidate selection is
    never implicit, and it never carries an arbitrary output directory: output
    always lands under the canonical package store.
    """

    incident_id: str
    repair_id: str
    user_id: str
    org_id: str


@dataclass
class RepairPackageRecord:
    """
    The canonical persisted record of one repair package.

    One record per (incident_id, repair_id, build_number).  The record is the
    source of truth for package state and is what the store persists as JSON.
    """

    incident_id: str
    repair_id: str
    build_number: int
    status: PackageStatus = PackageStatus.NOT_REQUESTED
    package_id: str = ""
    zip_path: Optional[str] = None
    checksum_sha256: str = ""
    size_bytes: int = 0
    manifest: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ready_at: Optional[str] = None
    built_by_user_id: str = ""
    built_by_org_id: str = ""
    error: Optional[str] = None
    version: int = 1  # schema version for forward compatibility
    # The source patch candidate, serialized for provenance and re-verification.
    candidate_snapshot: Dict[str, Any] = field(default_factory=dict)
    # The nine atomic check results that drove the verification level.
    checks_snapshot: Dict[str, bool] = field(default_factory=dict)
    # The canonical verification level the package carries.
    verification_level: str = VerificationLevel.GENERATED.value
    # A short reason for the level, for auditor readability.
    verification_reason: str = ""
    # Cross-reference: which bundle the patch was generated against.
    source_bundle_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepairPackageRecord":
        kwargs: Dict[str, Any] = {}
        for f in cls.__dataclass_fields__:
            if f in data:
                raw = data[f]
                if f == "status" and isinstance(raw, str):
                    try:
                        raw = PackageStatus(raw)
                    except ValueError:
                        raw = PackageStatus.FAILED
                kwargs[f] = raw
        return cls(**kwargs)

    @property
    def is_downloadable(self) -> bool:
        """Whether the package is in a state that permits download."""
        return self.status == PackageStatus.READY and bool(self.zip_path) and bool(self.checksum_sha256)


# ---------------------------------------------------------------------------
# Package errors
# ---------------------------------------------------------------------------


class PackageError(Exception):
    """Raised when a package cannot be produced or served."""

    def __init__(self, error_code: str, detail: str = ""):
        self.error_code = error_code
        self.detail = detail
        super().__init__(f"{error_code}: {detail}")


#: Canonical error codes returned by the packaging API.
PACKAGE_ERRORS: Dict[str, str] = {
    "incident_not_found": "The incident id does not refer to a known incident",
    "access_denied": "The authenticated principal may not access this incident",
    "repair_candidate_not_found": "The requested repair_id was not found for this incident",
    "unverified_repair_candidate": "The requested repair candidate did not pass verification",
    "repair_refused": "This incident's capability report refuses a speculative repair",
    "package_building": "A repair package is currently being built for this incident",
    "package_failed": "A repair package was requested but its build failed",
    "package_not_ready": "No repair package is available for this incident",
    "package_stale": "A newer repair package exists for this incident",
    "internal_error": "An unexpected error occurred while preparing the package",
}

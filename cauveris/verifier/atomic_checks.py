"""
Atomic Verification Checks & Hierarchical Verification Level Engine.

Guarantees:
1. Every verification level (UNVERIFIED, MODEL_VERIFIED, STAGING_VERIFIED, RUNTIME_VERIFIED)
   is strictly calculated from atomic check records.
2. Required skipped checks are NEVER treated as passed.
3. Simulation alone CANNOT grant STAGING_VERIFIED or RUNTIME_VERIFIED.
4. Summary references exact candidate, experiment, invariant set, and run IDs.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class VerificationLevel(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    MODEL_VERIFIED = "MODEL_VERIFIED"
    STAGING_VERIFIED = "STAGING_VERIFIED"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"


class CheckStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


LEVEL_RANK: Dict[VerificationLevel, int] = {
    VerificationLevel.UNVERIFIED: 0,
    VerificationLevel.MODEL_VERIFIED: 1,
    VerificationLevel.STAGING_VERIFIED: 2,
    VerificationLevel.RUNTIME_VERIFIED: 3,
}


class AtomicCheckRecord(BaseModel):
    """An atomic, auditable verification assertion."""
    check_id: str
    name: str
    target_level: VerificationLevel
    required: bool = True
    status: CheckStatus = CheckStatus.SKIPPED
    expected: str = ""
    actual: str = ""
    duration_ms: float = 0.0
    evidence_locator: Optional[str] = None
    evidence_ref: Optional[str] = None
    error_detail: Optional[str] = None
    failure_reason: Optional[str] = None


class VerificationSummary(BaseModel):
    """Canonical verification result calculated strictly from atomic checks."""
    summary_id: str
    candidate_id: str
    experiment_id: str
    invariant_set_id: str
    baseline_run_id: str
    intervention_run_id: str
    achieved_level: VerificationLevel = VerificationLevel.UNVERIFIED
    overall_status: str = "FAILED"
    checks: List[AtomicCheckRecord] = Field(default_factory=list)
    checks_passed_count: int = 0
    checks_failed_count: int = 0
    checks_skipped_count: int = 0
    rejection_reasons: List[str] = Field(default_factory=list)
    verified: bool = False
    limitations: List[str] = Field(default_factory=list)


def evaluate_verification_level(
    candidate_id: str,
    experiment_id: str,
    invariant_set_id: str,
    baseline_run_id: str,
    intervention_run_id: str,
    checks: List[AtomicCheckRecord],
    is_live_runtime_execution: bool = False,
    is_staging_workspace_execution: bool = False,
) -> VerificationSummary:
    """
    Computes achieved verification level strictly from atomic checks.
    Skipped required checks are not passed.
    Simulation alone cannot grant STAGING_VERIFIED or RUNTIME_VERIFIED.
    """
    rejection_reasons: List[str] = []
    limitations: List[str] = []

    if not checks:
        rejection_reasons.append("No verification checks were executed; verification cannot be granted without evidence.")

    passed = [c for c in checks if c.status == CheckStatus.PASSED]
    failed = [c for c in checks if c.status == CheckStatus.FAILED]
    skipped = [c for c in checks if c.status == CheckStatus.SKIPPED]

    # Collect failure and skipped reasons
    for c in failed:
        if c.required:
            msg = f"Check '{c.name}' FAILED: expected '{c.expected}', got '{c.actual}'"
            if c.failure_reason or c.error_detail:
                msg += f" ({c.failure_reason or c.error_detail})"
            rejection_reasons.append(msg)

    for c in skipped:
        if c.required:
            rejection_reasons.append(f"Required check '{c.name}' was SKIPPED (skipped checks cannot grant verification)")

    has_failed_required = any(c.status == CheckStatus.FAILED and c.required for c in checks)
    has_failed_optional = any(c.status == CheckStatus.FAILED and not c.required for c in checks)
    has_skipped_required = any(c.status == CheckStatus.SKIPPED and c.required for c in checks)

    if has_failed_required or has_skipped_required or not checks:
        overall_status = "FAILED"
    elif has_failed_optional:
        overall_status = "PARTIAL"
    elif all(c.status == CheckStatus.PASSED for c in checks if c.required):
        overall_status = "PASSED"
    else:
        overall_status = "FAILED"

    # Level 1: MODEL_VERIFIED requirements
    model_checks = [c for c in checks if c.target_level == VerificationLevel.MODEL_VERIFIED and c.required]
    model_passed = len(model_checks) > 0 and all(c.status == CheckStatus.PASSED for c in model_checks)

    # Level 2: STAGING_VERIFIED requirements (Requires physical workspace build & testing)
    staging_checks = [c for c in checks if c.target_level == VerificationLevel.STAGING_VERIFIED and c.required]
    staging_passed = (
        model_passed
        and is_staging_workspace_execution
        and len(staging_checks) > 0
        and all(c.status == CheckStatus.PASSED for c in staging_checks)
    )

    # Level 3: RUNTIME_VERIFIED requirements (Requires physical live runtime execution telemetry)
    runtime_checks = [c for c in checks if c.target_level == VerificationLevel.RUNTIME_VERIFIED and c.required]
    runtime_passed = (
        staging_passed
        and is_live_runtime_execution
        and len(runtime_checks) > 0
        and all(c.status == CheckStatus.PASSED for c in runtime_checks)
    )

    if not is_staging_workspace_execution:
        limitations.append("Simulation only: STAGING_VERIFIED and RUNTIME_VERIFIED cannot be granted without real workspace build.")
    if not is_live_runtime_execution:
        limitations.append("No active runtime deployment: RUNTIME_VERIFIED cannot be granted without production telemetry.")

    if runtime_passed:
        achieved = VerificationLevel.RUNTIME_VERIFIED
    elif staging_passed:
        achieved = VerificationLevel.STAGING_VERIFIED
    elif model_passed:
        achieved = VerificationLevel.MODEL_VERIFIED
    else:
        achieved = VerificationLevel.UNVERIFIED

    summary_id = f"vsum_{candidate_id}_{baseline_run_id[:8]}"
    verified = (
        achieved != VerificationLevel.UNVERIFIED
        and overall_status in ("PASSED", "PARTIAL")
        and not has_failed_required
        and not has_skipped_required
        and len(rejection_reasons) == 0
    )

    return VerificationSummary(
        summary_id=summary_id,
        candidate_id=candidate_id,
        experiment_id=experiment_id,
        invariant_set_id=invariant_set_id,
        baseline_run_id=baseline_run_id,
        intervention_run_id=intervention_run_id,
        achieved_level=achieved,
        overall_status=overall_status,
        checks=checks,
        checks_passed_count=len(passed),
        checks_failed_count=len(failed),
        checks_skipped_count=len(skipped),
        rejection_reasons=rejection_reasons,
        verified=verified,
        limitations=limitations,
    )

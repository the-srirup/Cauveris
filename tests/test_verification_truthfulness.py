"""
Tests for Verification Truthfulness: strictly progressive canonical levels,
derivation from atomic check records, prohibited false success patterns,
and prevention of skipped steps.
"""

from cauveris.verifier.atomic_checks import (
    AtomicCheckRecord,
    CheckStatus,
    VerificationLevel,
    evaluate_verification_level,
)


def test_four_strictly_canonical_verification_levels():
    """Prove exactly 4 canonical verification levels exist in progressive hierarchy."""
    expected = {"UNVERIFIED", "MODEL_VERIFIED", "STAGING_VERIFIED", "RUNTIME_VERIFIED"}
    actual = {lvl.value for lvl in VerificationLevel}
    assert actual == expected
    assert len(VerificationLevel) == 4


def test_empty_checks_cannot_grant_verification():
    """Prove claiming verification without running checks is strictly rejected."""
    summary = evaluate_verification_level(
        candidate_id="cand-empty",
        experiment_id="exp-empty",
        invariant_set_id="inv-empty",
        baseline_run_id="base-empty",
        intervention_run_id="int-empty",
        checks=[],
    )
    assert summary.verified is False
    assert summary.achieved_level == VerificationLevel.UNVERIFIED
    assert summary.overall_status == "FAILED"
    assert len(summary.rejection_reasons) > 0


def test_required_failed_check_strictly_blocks_verification():
    """Prove verified=True cannot be granted when any required check fails."""
    checks = [
        AtomicCheckRecord(
            check_id="CHK-1",
            name="Model invariant check",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-2",
            name="Safety invariant check",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.FAILED,
            expected="PRESERVED",
            actual="VIOLATED",
            failure_reason="Safety stopping distance exceeded limit",
        ),
    ]

    summary = evaluate_verification_level(
        candidate_id="cand-fail",
        experiment_id="exp-fail",
        invariant_set_id="inv-fail",
        baseline_run_id="base-fail",
        intervention_run_id="int-fail",
        checks=checks,
    )
    assert summary.verified is False
    assert summary.achieved_level == VerificationLevel.UNVERIFIED
    assert summary.overall_status == "FAILED"
    assert any("Safety stopping distance exceeded limit" in r for r in summary.rejection_reasons)


def test_skipped_required_check_cannot_be_treated_as_passed():
    """Prove skipped required checks prevent verification."""
    checks = [
        AtomicCheckRecord(
            check_id="CHK-1",
            name="Model invariant check",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-2",
            name="Staging test check",
            target_level=VerificationLevel.STAGING_VERIFIED,
            required=True,
            status=CheckStatus.SKIPPED,
        ),
    ]

    summary = evaluate_verification_level(
        candidate_id="cand-skip",
        experiment_id="exp-skip",
        invariant_set_id="inv-skip",
        baseline_run_id="base-skip",
        intervention_run_id="int-skip",
        checks=checks,
        is_staging_workspace_execution=True,
    )
    assert summary.verified is False
    assert summary.overall_status == "FAILED"
    assert summary.achieved_level != VerificationLevel.STAGING_VERIFIED


def test_simulation_alone_cannot_grant_staging_or_runtime_levels():
    """Prove simulation alone CANNOT achieve STAGING_VERIFIED or RUNTIME_VERIFIED."""
    checks = [
        AtomicCheckRecord(
            check_id="CHK-M1",
            name="Model twin check",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-S1",
            name="Workspace build check",
            target_level=VerificationLevel.STAGING_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-R1",
            name="Live runtime telemetry check",
            target_level=VerificationLevel.RUNTIME_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
    ]

    # Without staging execution
    sim_only_summary = evaluate_verification_level(
        candidate_id="cand-sim",
        experiment_id="exp-sim",
        invariant_set_id="inv-sim",
        baseline_run_id="base-sim",
        intervention_run_id="int-sim",
        checks=checks,
        is_staging_workspace_execution=False,
        is_live_runtime_execution=False,
    )
    assert sim_only_summary.achieved_level == VerificationLevel.MODEL_VERIFIED
    assert sim_only_summary.verified is True
    assert any("Simulation only" in lim for lim in sim_only_summary.limitations)

    # With staging execution but without live runtime
    staging_summary = evaluate_verification_level(
        candidate_id="cand-staging",
        experiment_id="exp-staging",
        invariant_set_id="inv-staging",
        baseline_run_id="base-staging",
        intervention_run_id="int-staging",
        checks=checks,
        is_staging_workspace_execution=True,
        is_live_runtime_execution=False,
    )
    assert staging_summary.achieved_level == VerificationLevel.STAGING_VERIFIED
    assert staging_summary.verified is True
    assert any("No active runtime deployment" in lim for lim in staging_summary.limitations)

    # With both staging and live runtime
    runtime_summary = evaluate_verification_level(
        candidate_id="cand-runtime",
        experiment_id="exp-runtime",
        invariant_set_id="inv-runtime",
        baseline_run_id="base-runtime",
        intervention_run_id="int-runtime",
        checks=checks,
        is_staging_workspace_execution=True,
        is_live_runtime_execution=True,
    )
    assert runtime_summary.achieved_level == VerificationLevel.RUNTIME_VERIFIED
    assert runtime_summary.verified is True
    assert runtime_summary.overall_status == "PASSED"


def test_optional_check_failure_yields_partial_status():
    """Prove failure of optional check results in PARTIAL status without failing verification."""
    checks = [
        AtomicCheckRecord(
            check_id="CHK-REQ-1",
            name="Required invariant",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-OPT-1",
            name="Optional profiling benchmark",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=False,
            status=CheckStatus.FAILED,
            expected="< 10ms",
            actual="12ms",
        ),
    ]

    summary = evaluate_verification_level(
        candidate_id="cand-opt",
        experiment_id="exp-opt",
        invariant_set_id="inv-opt",
        baseline_run_id="base-opt",
        intervention_run_id="int-opt",
        checks=checks,
    )
    assert summary.overall_status == "PARTIAL"
    assert summary.verified is True
    assert summary.achieved_level == VerificationLevel.MODEL_VERIFIED

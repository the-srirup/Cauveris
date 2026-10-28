from cauveris.verifier.atomic_checks import (
    AtomicCheckRecord,
    CheckStatus,
    VerificationLevel,
    evaluate_verification_level,
)


def test_skipped_required_check_blocks_verification():
    checks = [
        AtomicCheckRecord(
            check_id="CHK-01",
            name="Invariant consistency",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-02",
            name="Baseline failure reproduction",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.SKIPPED,  # SKIPPED required check!
        ),
    ]

    summary = evaluate_verification_level(
        candidate_id="patch-01",
        experiment_id="exp-01",
        invariant_set_id="invset-01",
        baseline_run_id="base-01",
        intervention_run_id="interv-01",
        checks=checks,
    )

    assert summary.achieved_level == VerificationLevel.UNVERIFIED
    assert summary.verified is False
    assert any("SKIPPED" in r for r in summary.rejection_reasons)
    assert summary.checks_skipped_count == 1


def test_simulation_alone_cannot_grant_staging_or_runtime():
    # All checks marked passed, but is_staging_workspace_execution=False
    checks = [
        AtomicCheckRecord(
            check_id="CHK-01",
            name="Model simulation gate",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-02",
            name="Workspace compilation",
            target_level=VerificationLevel.STAGING_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-03",
            name="Production telemetry match",
            target_level=VerificationLevel.RUNTIME_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
    ]

    summary = evaluate_verification_level(
        candidate_id="patch-01",
        experiment_id="exp-01",
        invariant_set_id="invset-01",
        baseline_run_id="base-01",
        intervention_run_id="interv-01",
        checks=checks,
        is_staging_workspace_execution=False,  # Simulation only!
        is_live_runtime_execution=False,
    )

    # Must be capped at MODEL_VERIFIED
    assert summary.achieved_level == VerificationLevel.MODEL_VERIFIED
    assert any("Simulation only" in lim for lim in summary.limitations)


def test_staging_workspace_execution_grants_staging_verified():
    checks = [
        AtomicCheckRecord(
            check_id="CHK-01",
            name="Model simulation gate",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
        AtomicCheckRecord(
            check_id="CHK-02",
            name="Workspace compilation & test suite",
            target_level=VerificationLevel.STAGING_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        ),
    ]

    summary = evaluate_verification_level(
        candidate_id="patch-01",
        experiment_id="exp-01",
        invariant_set_id="invset-01",
        baseline_run_id="base-01",
        intervention_run_id="interv-01",
        checks=checks,
        is_staging_workspace_execution=True,
        is_live_runtime_execution=False,
    )

    assert summary.achieved_level == VerificationLevel.STAGING_VERIFIED
    assert summary.verified is True
    assert len(summary.rejection_reasons) == 0

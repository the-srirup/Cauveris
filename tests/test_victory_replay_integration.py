import pytest
from fastapi.testclient import TestClient
from cauveris.api.main import app, incidents, pipeline_contexts
from cauveris.schemas.incident import Incident
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.state_machine.orchestrator import PipelineContext
from cauveris.verifier.atomic_checks import VerificationLevel


@pytest.mark.asyncio
async def test_victory_replay_scientific_consistency(test_user_admin):
    client = TestClient(app)
    incident_id = "test-sci-victory-001"

    incident = Incident(
        id=incident_id,
        title="Test Scientific Incident",
        description="Test incident for victory replay scientific verification",
    )
    # Associate owner with admin org/user
    incident._owner_user_id = test_user_admin["user"].id
    incident._owner_org_id = test_user_admin["org"].id
    incidents[incident_id] = incident

    # Set up mock pipeline context for this incident
    exp = Experiment(
        experiment_id="exp-batch-001",
        hypothesis_id="hyp-batching-delay",
        branch_name="intervention-reduce-batch",
        intervention="batching_window_ms = 0",
        conclusion="Failure eliminated in twin",
        reproduction_rate=0.0,
        failure_oracle={"freshness_budget_ms": 120.0},
    )

    patch = PatchCandidate(
        candidate_id="patch-batch-001",
        title="Reduce Dynamic Batching Window",
        unified_diff="--- a/config.py\n+++ b/config.py\n@@ -1 +1 @@\n-batching_window_ms = 50\n+batching_window_ms = 0\n",
        score=0.98,
        verified=True,
        applied_cleanly=True,
        regression_test_passes_after=True,
        original_failure_not_reproduced=True,
        existing_tests_pass=True,
        safety_invariants_pass=True,
        performance_within_budget=True,
        rollback_test_passes=True,
        verification_level=VerificationLevel.MODEL_VERIFIED,
    )

    vr = VerificationReport(
        patch_candidate_id="patch-batch-001",
        verified=True,
        applies_cleanly=True,
        regression_test_fails_before=True,
        regression_test_passes_after=True,
        original_failure_not_reproduced=True,
        existing_tests_pass=True,
        safety_invariants_pass=True,
        performance_within_budget=True,
        forbidden_change_scan_passes=True,
        rollback_test_passes=True,
        message="Patch verified against digital twin model",
        verification_level=VerificationLevel.MODEL_VERIFIED,
    )

    ctx = PipelineContext(
        incident=incident,
        experiments=[exp],
        patch_candidates=[patch],
        verification_reports=[vr],
    )
    pipeline_contexts[incident_id] = ctx

    response = client.get(
        f"/api/v1/incidents/{incident_id}/victory-replay",
        headers=test_user_admin["headers"],
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["available"] is True
    assert "verification_level" in data
    assert data["verification_level"] in ("MODEL_VERIFIED", "STAGING_VERIFIED", "RUNTIME_VERIFIED")
    assert "verification_summary" in data
    assert "canonical_invariants" in data
    assert len(data["canonical_invariants"]) > 0

    # Verify invariant unit and authority are preserved
    inv_ids = {inv["invariant_id"]: inv for inv in data["canonical_invariants"]}
    assert "perception_freshness" in inv_ids
    assert inv_ids["perception_freshness"]["unit"] == "ms"
    assert inv_ids["perception_freshness"]["authority"].lower() == "deployment_config"

    # Verify multi-dimensional outcomes
    assert "before_outcome" in data
    assert "after_outcome" in data
    assert "mission_outcome" in data["before_outcome"]
    assert "freshness_outcome" in data["before_outcome"]
    assert "physical_safety_outcome" in data["before_outcome"]
    # Physical safety without 3D geometry must be NOT_PROVEN
    assert data["after_outcome"]["physical_safety_outcome"] == "NOT_PROVEN"

    # Verify causal latency decomposition
    assert "latency_decomposition" in data
    decomp = data["latency_decomposition"]
    assert "min_achievable_latency_ms" in decomp
    assert decomp["min_achievable_latency_ms"] > 0
    assert "selected_strategy" in decomp
    assert "root_cause_component" in decomp

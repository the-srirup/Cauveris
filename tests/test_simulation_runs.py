import pytest
from cauveris.simulation.runs import BaselineRun, InterventionRun, compare_runs


def test_baseline_rejects_intervention_fields():
    with pytest.raises(ValueError, match="BaselineRun cannot contain post-repair intervention fields"):
        BaselineRun(
            baseline_run_id="base_01",
            incident_id="INC-01",
            hypothesis_id="hyp_01",
            mechanism_id="control_deadline_missed",
            model_id="twin_v2",
            invariant_set_id="invset_A",
            model_input_set_id="inputs_A",
            named_reproduced_failure="Perception staleness 240ms > 120ms budget",
            failures_cleared=True,  # Forbidden in baseline!
        )


def test_comparison_rejects_mismatched_invariant_set():
    base = BaselineRun(
        baseline_run_id="base_01",
        incident_id="INC-01",
        hypothesis_id="hyp_01",
        mechanism_id="control_deadline_missed",
        model_id="twin_v2",
        invariant_set_id="invset_A",
        model_input_set_id="inputs_A",
        named_reproduced_failure="Perception staleness 240ms > 120ms budget",
        failed_invariants=["perception_freshness"],
        baseline_outputs={"avg_latency_ms": 240.0, "stale_rate": 0.8},
    )

    interv = InterventionRun(
        intervention_run_id="interv_01",
        incident_id="INC-01",
        candidate_id="patch_01",
        baseline_run_id="base_01",
        hypothesis_id="hyp_01",
        mechanism_id="control_deadline_missed",
        model_id="twin_v2",
        invariant_set_id="invset_B",  # MISMATCH!
        model_input_set_id="inputs_B",
        outputs={"avg_latency_ms": 75.0, "stale_rate": 0.0},
        invariant_results={"perception_freshness": True},
    )

    with pytest.raises(ValueError, match="Invariant set mismatch"):
        compare_runs(base, interv, "patch_01")


def test_valid_comparison_computes_delta_and_conclusion():
    base = BaselineRun(
        baseline_run_id="base_01",
        incident_id="INC-01",
        hypothesis_id="hyp_01",
        mechanism_id="control_deadline_missed",
        model_id="twin_v2",
        invariant_set_id="invset_A",
        model_input_set_id="inputs_A",
        named_reproduced_failure="Perception staleness 240ms > 120ms budget",
        failed_invariants=["perception_freshness"],
        baseline_outputs={"avg_latency_ms": 240.0, "stale_rate": 0.8},
    )

    interv = InterventionRun(
        intervention_run_id="interv_01",
        incident_id="INC-01",
        candidate_id="patch_01",
        baseline_run_id="base_01",
        hypothesis_id="hyp_01",
        mechanism_id="control_deadline_missed",
        model_id="twin_v2",
        invariant_set_id="invset_A",  # MATCH
        model_input_set_id="inputs_A",
        outputs={"avg_latency_ms": 75.0, "stale_rate": 0.0},
        invariant_results={"perception_freshness": True},
    )

    cmp = compare_runs(base, interv, "patch_01")
    assert cmp.same_invariant_set_validation is True
    assert cmp.delta["avg_latency_ms"] == -165.0
    assert cmp.delta["stale_rate"] == -0.8
    assert "SUCCESS_REPAIRED" in cmp.conclusion

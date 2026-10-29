"""
Tests for Canonical Calculation Provenance across parameters, latency decomposition,
digital twin simulation runs, and comparative evaluations.
"""

import pytest
from cauveris.analysis.provenance import (
    ProvenanceClass,
    create_provenance_record,
    normalize_provenance_string,
)
from cauveris.analysis.model_inputs import (
    ModelInputBuilder,
    ModelInputKind,
)
from cauveris.analysis.latency_decomposition import (
    LatencyComponent,
    decompose_and_evaluate_latency,
)
from cauveris.simulation.runs import (
    BaselineRun,
    InterventionRun,
    compare_runs,
)


def test_eight_canonical_provenance_classes():
    """Prove all 8 canonical provenance classes are strictly defined and distinct."""
    expected = {
        "OBSERVED",
        "DECLARED",
        "DERIVED",
        "CALIBRATED",
        "INFERRED",
        "SIMULATED",
        "EXPLICIT_DEFAULT",
        "UNAVAILABLE",
    }
    actual = {cls.value for cls in ProvenanceClass}
    assert actual == expected
    assert len(ProvenanceClass) == 8


def test_normalize_provenance_string():
    """Prove prefix normalization resolves to canonical classes."""
    cases = [
        ("declared:config/worker.yaml", ProvenanceClass.DECLARED, "config/worker.yaml"),
        ("observed:telemetry/heap.csv", ProvenanceClass.OBSERVED, "telemetry/heap.csv"),
        ("measured:telemetry/latency.csv", ProvenanceClass.OBSERVED, "telemetry/latency.csv"),
        ("metric:cpu_load", ProvenanceClass.OBSERVED, "cpu_load"),
        ("derived:rate_hz", ProvenanceClass.DERIVED, "rate_hz"),
        ("calibrated:mle_fit", ProvenanceClass.CALIBRATED, "mle_fit"),
        ("inferred:oom_pressure", ProvenanceClass.INFERRED, "oom_pressure"),
        ("simulated:twin_run_01", ProvenanceClass.SIMULATED, "twin_run_01"),
        ("default:industry_baseline", ProvenanceClass.EXPLICIT_DEFAULT, "industry_baseline"),
        ("unavailable:telemetry_missing", ProvenanceClass.UNAVAILABLE, "telemetry_missing"),
        ("UNAVAILABLE", ProvenanceClass.UNAVAILABLE, None),
    ]
    for raw_str, expected_cls, expected_ref in cases:
        p_cls, p_ref = normalize_provenance_string(raw_str)
        assert p_cls == expected_cls
        assert p_ref == expected_ref


def test_provenance_record_display_value_and_no_silent_zeros():
    """Prove missing values guarantee display_value == 'UNAVAILABLE' without silent zeros."""
    rec_missing = create_provenance_record(
        parameter_id="resource_demand_mb",
        value=None,
        unit="MB",
        provenance=ProvenanceClass.UNAVAILABLE,
        calculation_rationale="Memory trace was absent from uploaded bundle",
    )
    assert rec_missing.value is None
    assert rec_missing.display_value == "UNAVAILABLE"
    assert rec_missing.provenance == ProvenanceClass.UNAVAILABLE
    p_dict = rec_missing.to_provenance_dict()
    assert p_dict["display_value"] == "UNAVAILABLE"
    assert p_dict["is_evidence_backed"] is False

    rec_present = create_provenance_record(
        parameter_id="batching_window_ms",
        value=200.0,
        unit="ms",
        provenance=ProvenanceClass.DECLARED,
        source_artifact="config/worker.yaml",
        source_locator="batching.window_ms",
        calculation_rationale="Parsed directly from config key",
    )
    assert rec_present.value == 200.0
    assert rec_present.display_value == "200 ms"
    assert rec_present.provenance == ProvenanceClass.DECLARED
    assert rec_present.to_provenance_dict()["is_evidence_backed"] is True


def test_untracked_parameter_rejected_by_validation():
    """Prove untracked parameters not in parameter policies are strictly rejected."""
    builder = ModelInputBuilder("INC-UNTRACKED")
    with pytest.raises(ValueError, match="Untracked parameter 'non_existent_magic_param'"):
        builder.add_evidence_input(
            parameter_id="non_existent_magic_param",
            value=42.0,
            unit="items",
            kind=ModelInputKind.OBSERVED,
            source_artifact_id="art-1",
            source_locator="magic.key",
        )

    with pytest.raises(ValueError, match="Untracked parameter 'non_existent_magic_param'"):
        builder.mark_unavailable("non_existent_magic_param", "Missing")


def test_model_inputs_provenance_tracking():
    """Prove model inputs track provenance, source artifact, extraction rule, and rationale."""
    builder = ModelInputBuilder("INC-PROV-01")
    builder.add_evidence_input(
        parameter_id="batching_window_ms",
        value=150.0,
        unit="ms",
        kind=ModelInputKind.DECLARED,
        source_artifact_id="art-worker-cfg",
        source_locator="config/worker.yaml#batching_window_ms",
        extraction_rule="yaml_scalar_lookup",
        calculation_rationale="Extracted from worker.yaml batching section",
    )
    builder.mark_unavailable("resource_demand_mb", "Memory telemetry was corrupted")
    builder.fill_unspecified_with_policy_defaults()

    input_set = builder.build()
    declared = input_set.inputs["batching_window_ms"]
    assert declared.kind == ModelInputKind.DECLARED
    assert declared.value == 150.0
    assert declared.display_value == "150 ms"
    assert declared.source_artifact_id == "art-worker-cfg"
    assert declared.source_locator == "config/worker.yaml#batching_window_ms"
    assert declared.extraction_rule == "yaml_scalar_lookup"
    assert declared.calculation_rationale == "Extracted from worker.yaml batching section"
    assert declared.evidence_backed is True

    unavail = input_set.inputs["resource_demand_mb"]
    assert unavail.kind == ModelInputKind.UNAVAILABLE
    assert unavail.value is None
    assert unavail.display_value == "UNAVAILABLE"
    assert unavail.confidence == 0.0
    assert unavail.evidence_backed is False

    default_param = input_set.inputs["arrival_rate_hz"]
    assert default_param.kind == ModelInputKind.EXPLICIT_DEFAULT
    assert default_param.evidence_backed is False
    assert default_param.default_reason is not None


def test_latency_decomposition_provenance():
    """Prove latency decomposition components carry valid provenance and rationales."""
    prov_map = {
        "queue_wait": "observed:telemetry/queue.csv",
        "batching_wait": "declared:config/inference.yaml",
        "compute_time": "observed:telemetry/gpu_trace.csv",
        "scheduling_overhead": "inferred:os_jitter",
    }
    decomp = decompose_and_evaluate_latency(
        queue_wait_ms=30.0,
        batching_wait_ms=100.0,
        request_transport_ms=10.0,
        dependency_wait_ms=5.0,
        compute_time_ms=25.0,
        response_transport_ms=8.0,
        scheduling_overhead_ms=2.0,
        active_timeout_ms=50.0,
        control_deadline_ms=80.0,
        provenance_map=prov_map,
    )
    assert decomp.queue_wait.provenance == ProvenanceClass.OBSERVED
    assert decomp.queue_wait.display_value == "30 ms"
    assert decomp.queue_wait.calculation_rationale is not None

    assert decomp.batching_wait.provenance == ProvenanceClass.DECLARED
    assert decomp.batching_wait.display_value == "100 ms"

    assert decomp.scheduling_overhead.provenance == ProvenanceClass.INFERRED

    # Verify component with UNAVAILABLE
    unavail_comp = LatencyComponent(
        name="missing_metric",
        value=None,
        unit="ms",
        provenance=ProvenanceClass.UNAVAILABLE,
        calculation_rationale="No telemetry available for missing metric",
    )
    assert unavail_comp.display_value == "UNAVAILABLE"


def test_simulation_runs_provenance_and_comparison():
    """Prove baseline, intervention, and comparison records track metric provenance."""
    baseline = BaselineRun(
        baseline_run_id="base-run-001",
        incident_id="INC-CALC-01",
        hypothesis_id="hypo-1",
        mechanism_id="resource_exhaustion",
        model_id="twin_perception",
        model_version="2.0",
        invariant_set_id="inv-set-1",
        model_input_set_id="inp-set-1",
        named_reproduced_failure="resource_exhaustion",
        failed_invariants=["memory_ceiling_under_90_percent"],
    )
    baseline.record_output_metric(
        name="peak_memory_mb",
        value=1150.0,
        unit="MB",
        provenance=ProvenanceClass.SIMULATED,
        rationale="Simulated memory leak over 1000 request cycles",
    )
    baseline.record_output_metric(
        name="gpu_utilization_pct",
        value=None,
        unit="%",
        provenance=ProvenanceClass.UNAVAILABLE,
        rationale="GPU profiler data absent in incident bundle",
    )

    assert baseline.baseline_outputs["peak_memory_mb"] == 1150.0
    assert baseline.baseline_outputs["gpu_utilization_pct"] == "UNAVAILABLE"
    assert baseline.metric_provenance["peak_memory_mb"].provenance == ProvenanceClass.SIMULATED
    assert baseline.metric_provenance["gpu_utilization_pct"].provenance == ProvenanceClass.UNAVAILABLE
    assert baseline.metric_provenance["gpu_utilization_pct"].display_value == "UNAVAILABLE"

    intervention = InterventionRun(
        intervention_run_id="int-run-001",
        incident_id="INC-CALC-01",
        candidate_id="cand-patch-01",
        baseline_run_id="base-run-001",
        hypothesis_id="hypo-1",
        mechanism_id="resource_exhaustion",
        model_id="twin_perception",
        model_version="2.0",
        invariant_set_id="inv-set-1",
        model_input_set_id="inp-set-1",
        outputs={},
        invariant_results={"memory_ceiling_under_90_percent": True},
    )
    intervention.record_output_metric(
        name="peak_memory_mb",
        value=480.0,
        unit="MB",
        provenance=ProvenanceClass.SIMULATED,
        rationale="Simulated memory after applying worker queue drain patch",
    )

    assert intervention.metric_provenance["peak_memory_mb"].provenance == ProvenanceClass.SIMULATED

    comparison = compare_runs(baseline, intervention, candidate_id="cand-patch-01")
    assert comparison.valid_comparison is True
    assert comparison.delta["peak_memory_mb"] == -670.0
    assert "peak_memory_mb" in comparison.metric_provenance
    assert comparison.metric_provenance["peak_memory_mb"].provenance == ProvenanceClass.SIMULATED

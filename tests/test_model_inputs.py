import pytest
from cauveris.analysis.model_inputs import (
    ModelInputBuilder,
    ModelInputKind,
    SensitivityLevel,
)
from cauveris.analysis.sensitivity import run_bounded_sensitivity_analysis


def test_model_input_builder_provenance():
    builder = ModelInputBuilder("INC-TRACE-01")
    builder.add_evidence_input(
        parameter_id="batching_window_ms",
        value=200.0,
        unit="ms",
        kind=ModelInputKind.OBSERVED,
        source_artifact_id="art-config",
        source_locator="robot.toml#batching_window_ms",
    )
    builder.fill_unspecified_with_policy_defaults()
    input_set = builder.build()

    # Evidence-backed parameter
    batch_inp = input_set.inputs["batching_window_ms"]
    assert batch_inp.kind == ModelInputKind.OBSERVED
    assert batch_inp.evidence_backed is True
    assert batch_inp.value == 200.0

    # Default parameter must NEVER be OBSERVED
    arr_inp = input_set.inputs["arrival_rate_hz"]
    assert arr_inp.kind == ModelInputKind.EXPLICIT_DEFAULT
    assert arr_inp.evidence_backed is False
    assert arr_inp.default_reason is not None

    # Hashing reproducibility
    builder2 = ModelInputBuilder("INC-TRACE-01")
    builder2.add_evidence_input(
        parameter_id="batching_window_ms",
        value=200.0,
        unit="ms",
        kind=ModelInputKind.OBSERVED,
        source_artifact_id="art-config",
        source_locator="robot.toml#batching_window_ms",
    )
    builder2.fill_unspecified_with_policy_defaults()
    input_set2 = builder2.build()

    assert input_set.input_hash == input_set2.input_hash


def test_unavailable_critical_input_blocks_verification():
    builder = ModelInputBuilder("INC-TRACE-02")
    builder.mark_unavailable("resource_demand_mb", "Memory trace corrupted")
    input_set = builder.build()

    assert input_set.has_unavailable_critical is True
    assert input_set.verification_blocked is True
    assert input_set.inputs["resource_demand_mb"].kind == ModelInputKind.UNAVAILABLE


def test_sensitivity_analysis_blocks_on_critical_reversal():
    builder = ModelInputBuilder("INC-TRACE-03")
    builder.fill_unspecified_with_policy_defaults()
    input_set = builder.build()

    # Suppose a proposed repair only works if arrival_rate_hz <= 15 Hz.
    # At arrival_rate_hz > 15 Hz, the queue overflows and repair fails.
    def mock_evaluator(overrides):
        rate = overrides.get("arrival_rate_hz", 10.0)
        repaired = rate <= 15.0
        metric = rate * 10.0
        return repaired, metric

    reports = run_bounded_sensitivity_analysis(
        input_set,
        mock_evaluator,
        target_param_ids=["arrival_rate_hz"],
    )

    assert "arrival_rate_hz" in reports
    rep = reports["arrival_rate_hz"]
    assert rep.sensitivity == SensitivityLevel.CRITICAL
    assert rep.outcome_reversal_detected is True
    assert rep.blocks_model_verification is True
    assert rep.confidence_penalty > 0.0

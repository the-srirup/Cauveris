"""
Regression tests for the evidence-derived analysis layer.

The analysis layer is the foundation every downstream stage reads from, so
these tests check the properties that matter rather than exact numbers:

* latency observations are separated by pipeline stage instead of pooled;
* the model only fits parameters the evidence does not already pin down;
* the deployment correlation reports the deployment as *preceding* the onset;
* contradictions inside a bundle are reported rather than averaged away;
* counterfactuals move in the direction the physics says they should.
"""

from pathlib import Path

import pytest

from cauveris.analysis.model import TwinParameters, simulate_pipeline
from cauveris.analysis.system_model import (
    PipelineStage,
    ParameterRole,
    build_system_model,
    classify_parameter,
)

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "golden_incident" / "incident-CAU-0001"


@pytest.fixture(scope="module")
def model():
    return build_system_model("CAU-0001", BUNDLE)


# ---------------------------------------------------------------------------
# Parameter classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("dynamic_batching.max_batch_size", 8, ParameterRole.BATCH_SIZE),
        ("dynamic_batching.batching_window_ms", 200, ParameterRole.BATCH_WINDOW),
        ("batching_window_ms", 200, ParameterRole.BATCH_WINDOW),
        ("safety.detection_freshness_budget_ms", 120, ParameterRole.SAFETY_BUDGET),
        ("perception.required_detection_frequency_hz", 10, ParameterRole.CONTROL_RATE),
        ("qos.queue_depth", 5, ParameterRole.QUEUE_DEPTH),
        ("server.worker_count", 2, ParameterRole.WORKER_COUNT),
        ("safety.control_loop_deadline_ms", 100, ParameterRole.TIMEOUT),
    ],
)
def test_classify_parameter_by_name(key, value, expected):
    assert classify_parameter(key, value) == expected


def test_classify_max_size_uses_value_type():
    """``max_size`` is ambiguous; the value disambiguates it."""
    assert classify_parameter("cache.max_size", "512Mi") == ParameterRole.MEMORY
    assert classify_parameter("cache.max_size", 16) != ParameterRole.MEMORY


# ---------------------------------------------------------------------------
# Evidence collection
# ---------------------------------------------------------------------------


def test_latency_samples_are_staged(model):
    """Observations from different stages must not be pooled together."""
    stages = {s["stage"] for s in model.latency_samples}
    assert PipelineStage.AGE in stages
    assert PipelineStage.SERVER_REQUEST in stages
    assert PipelineStage.TRANSPORT in stages
    assert PipelineStage.QUEUE_WAIT in stages


def test_control_loop_span_is_not_a_latency(model):
    """
    The control-loop span's duration is the loop period, not a latency.

    Treating it as one is what produced a meaningless pooled mean age.
    """
    control = [s for s in model.latency_samples if s["stage"] == PipelineStage.CONTROL_PERIOD]
    assert control, "the robot_control_loop span should be classified as a control period"
    for sample in control:
        assert sample["value"] not in [155.0]


def test_transport_comes_only_from_the_link(model):
    transport = [s for s in model.latency_samples if s["stage"] == PipelineStage.TRANSPORT]
    assert transport
    # The inference server's own latency must not be counted as transport.
    assert all(sample["value"] < 100 for sample in transport)
    assert 10 <= model.transport_distribution.mean <= 20


def test_budget_is_read_from_configuration(model):
    assert model.budget.freshness_budget_ms == 120.0
    assert model.budget.control_deadline_ms == 100.0
    assert model.budget.required_rate_hz == 10.0
    assert model.budget.emergency_stop_on_stale is True


def test_config_delta_is_classified_by_role(model):
    deltas = {d.key: d for d in model.config_deltas}
    assert deltas
    window_delta = deltas["batching_window_ms"]
    assert window_delta.role == ParameterRole.BATCH_WINDOW
    assert window_delta.direction == "increased"
    assert window_delta.ratio == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def test_declared_parameters_are_not_fitted(model):
    """
    The optimiser may only move parameters the evidence does not pin down.

    Batch window, batch size, worker count, subscriber depth and the
    control-loop rate are all declared by the incident's configuration.
    """
    assert model.calibration is not None
    params = model.calibration.params
    assert params.batching_window_ms == model.base_parameters.batching_window_ms
    assert params.max_batch_size == model.base_parameters.max_batch_size
    assert params.server_workers == model.base_parameters.server_workers
    assert params.qos_queue_depth == model.base_parameters.qos_queue_depth
    assert params.consumer_rate_hz == model.budget.required_rate_hz


def test_calibration_reproduces_the_batch_size(model):
    """The observed batch of 4 frames is the quantity that selects the regime."""
    assert model.calibration is not None
    fitted = model.calibration.fitted["mean_batch_size"]
    assert fitted == pytest.approx(4.0, abs=1.0)


def test_calibration_reproduces_the_service_time(model):
    """Queue wait plus service equals the traced request latency of 155 ms."""
    assert model.calibration is not None
    assert model.calibration.fitted["mean_service_ms"] == pytest.approx(40.0, abs=6.0)


def test_calibration_horizon_is_long_enough_to_be_meaningful(model):
    """A sub-second calibration window would rest on a handful of frames."""
    assert model.simulation_horizon_s >= 10.0
    assert model.calibration is not None
    assert model.calibration.fitted["mean_age_ms"] > 0


# ---------------------------------------------------------------------------
# Deployment correlation
# ---------------------------------------------------------------------------


def test_deployment_is_reported_as_preceding_the_onset(model):
    """v42 rolled out 2.5 h before the incident, and must be reported so."""
    assert model.anomaly_onset_correlated_deployment is not None
    assert model.anomaly_onset_correlated_deployment.deployment_id == "v42"
    text = " ".join(model.notes).lower()
    assert "preceded the anomaly onset" in text
    assert "after deployment" not in text


# ---------------------------------------------------------------------------
# Consistency reporting
# ---------------------------------------------------------------------------


def test_contradictory_evidence_is_reported(model):
    """
    The golden bundle's batch size and queue-depth series disagree.

    The contradiction must be visible, because a model that hides it would
    quietly explain neither observation.
    """
    ids = {f["id"] for f in model.consistency_findings}
    assert "arrival-rate-disagreement" in ids
    finding = next(f for f in model.consistency_findings if f["id"] == "arrival-rate-disagreement")
    assert finding["severity"] in ("critical", "warning")
    assert finding["implication"]


def test_contradictory_backlog_is_not_fitted_against(model):
    """The model may not be fitted to two incompatible observations at once."""
    assert model.calibration is not None
    assert "mean_backlog" not in model.calibration.targets


# ---------------------------------------------------------------------------
# Counterfactual direction
# ---------------------------------------------------------------------------


def test_shortening_the_window_reduces_latency_in_a_window_limited_regime(model):
    """
    In a window-limited regime a shorter batching window must reduce latency.

    The golden bundle's batch of 4 frames against a maximum of 8 puts it in
    that regime, which is the regime the counterfactual depends on.
    """
    base = model.predict({})
    shorter = model.predict({"batching_window_ms": 100.0})

    assert base.window_limited_epochs > base.size_limited_epochs
    assert shorter.mean_age_ms < base.mean_age_ms
    assert shorter.mean_request_latency_ms < base.mean_request_latency_ms


def test_counterfactual_uses_the_calibration_horizon(model):
    """A prediction must be comparable with the calibration, not 0.3 s of it."""
    base = model.predict({})
    assert base.consumed > 30


# ---------------------------------------------------------------------------
# The simulation itself
# ---------------------------------------------------------------------------


def test_simulation_is_deterministic_for_a_seed():
    params = TwinParameters(arrival_rate_hz=25.0, batching_window_ms=150.0)
    first = simulate_pipeline(params, duration_s=2.0, seed=7)
    second = simulate_pipeline(params, duration_s=2.0, seed=7)
    assert first.mean_age_ms == pytest.approx(second.mean_age_ms)
    assert first.frames == second.frames


def test_service_time_grows_with_batch_size():
    """A larger batch must cost the server more time."""
    small = TwinParameters(arrival_rate_hz=200.0, batching_window_ms=50.0, max_batch_size=2)
    large = TwinParameters(arrival_rate_hz=200.0, batching_window_ms=50.0, max_batch_size=16)
    small_out = simulate_pipeline(small, duration_s=2.0, seed=3)
    large_out = simulate_pipeline(large, duration_s=2.0, seed=3)
    assert large_out.mean_batch_size > small_out.mean_batch_size
    assert large_out.mean_service_ms > small_out.mean_service_ms


def test_overload_grows_the_backlog():
    """An arrival rate above the server's capacity must accumulate a queue."""
    params = TwinParameters(
        arrival_rate_hz=200.0,
        batching_window_ms=100.0,
        max_batch_size=4,
        service_base_ms=30.0,
        service_per_item_ms=10.0,
    )
    outcome = simulate_pipeline(params, duration_s=3.0, seed=11)
    assert outcome.mean_backlog > 1.0
    assert outcome.max_backlog > outcome.mean_backlog

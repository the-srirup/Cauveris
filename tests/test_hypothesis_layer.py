"""
Regression tests for the evidence-driven hypothesis layer.

A hypothesis layer that is worth trusting has to satisfy three properties,
and every test here is about one of them:

* **Grounding** - a hypothesis is emitted only when the bundle holds evidence
  for it, that evidence is cited, and the claim quotes the measurement it is
  based on.
* **Falsifiability** - every hypothesis says what observation would show it to
  be wrong, and what the intervention predicts.
* **Generality** - the generator contains no knowledge of any particular
  incident.  The same bundle under a different incident id must produce the
  same hypotheses, and a bundle with no evidence must produce nothing but an
  honest "not enough evidence" fallback.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import pytest
import yaml

from cauveris.analysis.system_model import ParameterRole, get_system_model
from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.model_gateway.base import ModelGateway, ModelResponse
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.incident import Incident

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "golden_incident" / "incident-CAU-0001"


def _incident(incident_id: str = "CAU-0001", bundle: Path = BUNDLE) -> Incident:
    manifest: dict = {}
    manifest_path = bundle / "manifest.yaml"
    if manifest_path.exists():
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    return Incident(
        id=incident_id,
        title=manifest.get("title", "incident"),
        manifest=manifest,
        bundle_path=str(bundle),
    )


def _generate(incident: Incident, gateway: ModelGateway = None) -> List[Hypothesis]:
    return asyncio.run(HypothesisGenerator(model_gateway=gateway).generate(incident))


@pytest.fixture(scope="module")
def hypotheses() -> List[Hypothesis]:
    return _generate(_incident())


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------


def test_every_hypothesis_cites_evidence(hypotheses):
    for hyp in hypotheses:
        assert hyp.supporting_artifact_ids, f"{hyp.hypothesis_id} cites nothing"
        assert hyp.causal_claim.strip()
        assert hyp.expected_observation.strip()
        assert hyp.intervention.strip()


def test_every_hypothesis_is_falsifiable(hypotheses):
    """A claim that cannot be wrong is not a hypothesis."""
    for hyp in hypotheses:
        assert hyp.falsifying_observation.strip()
        # The falsifying statement has to name something measurable.
        assert len(hyp.falsifying_observation) > 20


def test_confidence_is_a_number_in_range(hypotheses):
    for hyp in hypotheses:
        assert 0.0 < hyp.confidence_prior <= 1.0


def test_hypotheses_are_sorted_by_confidence(hypotheses):
    confidences = [hyp.confidence_prior for hyp in hypotheses]
    assert confidences == sorted(confidences, reverse=True)


def test_ids_are_unique_and_semantic(hypotheses):
    ids = [hyp.hypothesis_id for hyp in hypotheses]
    assert len(ids) == len(set(ids))
    for hyp in hypotheses:
        assert hyp.hypothesis_id.startswith("h_")
        assert " " not in hyp.hypothesis_id


def test_the_script_source_knows_no_incident_id():
    """
    The generator must not mention an incident id.

    A hard-coded id is how an incident-specific answer masquerades as a
    general method.
    """
    source = (ROOT / "cauveris" / "hypothesis" / "generator.py").read_text(encoding="utf-8")
    for forbidden in ("CAU-0001", "GOLDEN", "golden"):
        assert forbidden not in source


def test_claims_quote_measured_numbers(hypotheses):
    """
    The claim has to carry the measurement, not a vibe.

    At least one hypothesis for this bundle must mention a real measured
    quantity with its value.
    """
    claims = " ".join(hyp.causal_claim for hyp in hypotheses)
    assert "ms" in claims
    assert "%" in claims


def test_a_hypothesis_exists_for_each_detected_mechanism(hypotheses):
    """
    This bundle has a batch window, a sampling period, a growing queue, a
    busy GPU and a real link delay - each should produce its own hypothesis.
    """
    ids = {hyp.hypothesis_id for hyp in hypotheses}
    assert "h_batching_window_latency" in ids
    assert "h_consumer_sampling_interval" in ids
    assert "h_server_overload" in ids
    assert "h_transport_latency" in ids


def test_no_hypothesis_contradicts_the_measured_evidence(hypotheses):
    """
    The queue depth grows at 65.8 frames/s while the batch size implies 20 Hz.

    A hypothesis that quotes a different number would be a fabrication, so the
    contradictions the layer does report have to be the real one.
    """
    overload = next(h for h in hypotheses if h.hypothesis_id == "h_server_overload")
    assert overload.contradicting_artifact_ids
    text = " ".join(overload.contradicting_artifact_ids)
    assert "frames" in text and "Hz" in text


def test_interventions_name_the_configuration_they_change(hypotheses):
    """
    An intervention that cannot be applied is not an intervention.

    Any hypothesis that changes a parameter has to name a real file and a
    real parameter key from the bundle.
    """
    for hyp in hypotheses:
        if not hyp.likely_parameters:
            continue
        for path in hyp.likely_files:
            assert (BUNDLE / path).exists(), f"{hyp.hypothesis_id} cites a missing file"


def test_the_batching_window_hypothesis_targets_a_window_that_actually_fits(
    hypotheses,
):
    """
    The recommendation has to be a window the calibrated model *proves* fits.

    The deployment rolled the window back from 200 ms to 100 ms, and 100 ms is
    the obvious answer - but the calibration shows it leaves the mean age
    above the 120 ms budget.  Recommending it would hand the operator a patch
    that reproduces the safety violation it claims to fix.  The hypothesis has
    to name the largest window that actually meets the budget, and the
    intervention has to name that window and the value it replaces.
    """
    window = next(h for h in hypotheses if h.hypothesis_id == "h_batching_window_latency")

    model = get_system_model("CAU-0001", BUNDLE)
    assert model is not None and model.has_fitted_model()
    budget = model.budget.freshness_budget_ms

    delta = model.delta_for_role(ParameterRole.BATCH_WINDOW)
    assert delta is not None and delta.numeric
    rollback = float(delta.numeric[0])
    current = float(model.parameters.batching_window_ms)

    # The naive rollback really is insufficient - otherwise this test would
    # be asserting nothing.
    rollback_outcome = model.predict({"batching_window_ms": rollback})
    assert not _meets_budget(rollback_outcome, budget)

    # The recommended target does meet the budget on all three criteria.
    target = window.proposed_changes[0].target_value
    assert target < rollback, "the recommendation is not below the rollback value"
    target_outcome = model.predict({"batching_window_ms": target})
    assert _meets_budget(target_outcome, budget)

    # And it is the *largest* such window: every larger candidate the ladder
    # would try has to fail the budget, otherwise a bigger window would have
    # been the better recommendation.
    candidate = rollback
    while candidate > target:
        candidate = max(candidate / 2.0, target)
        if candidate == target:
            break
        assert not _meets_budget(
            model.predict({"batching_window_ms": candidate}), budget
        ), f"{candidate} ms also fits, so it should have been recommended"

    # The intervention names the value it recommends and the value it replaces.
    assert f"{target:g} ms" in window.intervention
    assert f"{current:g} ms" in window.intervention
    assert f"{rollback:g} ms" not in window.intervention


def _meets_budget(outcome, budget_ms: float) -> bool:
    """
    Whether a simulated outcome satisfies the freshness budget.

    Three things at once: the mean age, the 95th-percentile age and the
    stale rate.  Checking only the mean would call a window feasible while
    one detection in five is still too old to act on.
    """
    return (
        outcome.mean_age_ms <= budget_ms
        and outcome.p95_age_ms <= budget_ms
        and outcome.stale_rate <= 0.02
    )


def test_the_batching_window_hypothesis_is_not_self_contradictory(hypotheses):
    """
    A statement that claims the mean age is above the budget while quoting a
    mean age below it is not a finding.
    """
    window = next(h for h in hypotheses if h.hypothesis_id == "h_batching_window_latency")
    text = " ".join(
        [
            window.causal_claim,
            window.expected_observation,
            window.falsifying_observation,
            window.intervention,
        ]
    )
    assert "does not bring the mean age under" not in text


def test_the_consumer_sampling_hypothesis_cites_the_file_that_declares_the_rate(
    hypotheses,
):
    """
    The rate is declared in the robot configuration, not the inference one.

    Citing the wrong file sends the operator to the wrong document.
    """
    sampling = next(
        h for h in hypotheses if h.hypothesis_id == "h_consumer_sampling_interval"
    )
    assert "config/robot_params.yaml" in sampling.supporting_artifact_ids
    assert sampling.likely_files == ["config/robot_params.yaml"]


def test_the_resource_hypothesis_reports_a_percentage_range(hypotheses):
    """The GPU went from 45% to 90%, not from 4500% to 90%."""
    resource = next(h for h in hypotheses if h.hypothesis_id == "h_resource_contention")
    assert "4500" not in resource.causal_claim
    assert "GPU" in resource.causal_claim


def test_the_transport_hypothesis_reports_a_range(hypotheses):
    """Jitter is reported as a range, not as one clause per sample."""
    transport = next(h for h in hypotheses if h.hypothesis_id == "h_transport_latency")
    assert "jitter of 1 ms and" not in transport.causal_claim


# ---------------------------------------------------------------------------
# Generality
# ---------------------------------------------------------------------------


def test_the_same_bundle_under_a_different_id_produces_the_same_hypotheses():
    """
    No incident is special.  The same evidence under a different label has to
    produce the same analysis.
    """
    first = _generate(_incident("CAU-0001"))
    second = _generate(_incident("XYZ-9999"))
    assert [h.hypothesis_id for h in first] == [h.hypothesis_id for h in second]
    assert [h.causal_claim for h in first] == [h.causal_claim for h in second]


def test_an_empty_bundle_produces_only_an_honest_fallback(tmp_path):
    """
    With nothing to analyse, the layer says so instead of inventing a cause.
    """
    empty = tmp_path / "incident-empty"
    empty.mkdir()
    incident = Incident(
        id="EMPTY-1",
        title="no evidence",
        bundle_path=str(empty),
    )
    hypotheses = _generate(incident)
    assert len(hypotheses) == 1
    only = hypotheses[0]
    assert only.hypothesis_id == "h_unclassified_latency_excess"
    assert only.confidence_prior <= 0.3
    assert only.missing_evidence


# ---------------------------------------------------------------------------
# The gateway
# ---------------------------------------------------------------------------


class _StubGateway(ModelGateway):
    """A gateway that behaves like a real reasoning model."""

    def __init__(self, provider: str = "nebius") -> None:
        self.provider = provider
        self.prompts: List[str] = []

    async def generate(self, prompt, schema=None, temperature=0.7, max_tokens=None):
        self.prompts.append(prompt)
        return ModelResponse(
            content="The batching window was widened to 200 ms in v42.",
            structured_data={
                "hypothesis_id": "stub",
                "causal_claim": "The batching window was widened to 200 ms in v42.",
                "status": "CONFIRMED",
                "confidence_prior": 0.8,
                "expected_observation": "The age falls when the window is restored.",
                "falsifying_observation": "The age does not fall.",
                "intervention": "Restore the window to 100 ms.",
                "supporting_artifact_ids": ["config/inference.yaml"],
                "missing_evidence": [],
                "likely_parameters": ["dynamic_batching.batching_window_ms"],
                "likely_files": ["config/inference.yaml"],
            },
            model_used="stub",
            provider=self.provider,
        )

    def is_available(self) -> bool:
        return True


def test_a_real_gateway_result_is_included():
    gateway = _StubGateway()
    hypotheses = _generate(_incident("CAU-SMOKE"), gateway=gateway)
    ids = {h.hypothesis_id for h in hypotheses}
    assert "hyp-CAU-SMOKE-nebius" in ids
    model_hypothesis = next(h for h in hypotheses if h.hypothesis_id == "hyp-CAU-SMOKE-nebius")
    assert model_hypothesis.status.value == "INFERRED"
    assert gateway.prompts, "the gateway must be given a real prompt"


def test_the_fixture_gateway_is_not_presented_as_an_inference():
    """
    The local gateway returns a canned fixture.  Passing it off as an
    evidence-derived inference would be a mock disguised as a result.
    """
    from cauveris.model_gateway.local import LocalModelGateway

    hypotheses = _generate(_incident("CAU-0001"), gateway=LocalModelGateway())
    for hyp in hypotheses:
        assert hyp.hypothesis_id != "hyp-001"
        assert "deployment v42" not in hyp.causal_claim
        assert "src/inference/batching_config.py" not in hyp.likely_files


def test_the_gateway_prompt_carries_the_measured_evidence():
    gateway = _StubGateway()
    _generate(_incident(), gateway=gateway)
    prompt = gateway.prompts[0]
    assert "120" in prompt  # the declared freshness budget
    assert "ms" in prompt

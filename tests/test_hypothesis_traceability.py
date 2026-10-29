"""
Tests for Complete Hypothesis Traceability across generation, schemas,
model assistance, evidence grounding, and API endpoints.
"""

import pytest
from cauveris.schemas.base import StatusLabel
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.incident import Incident
from cauveris.hypothesis.generator import HypothesisGenerator


def test_hypothesis_schema_traceability_fields():
    """Prove hypothesis captures all 6 required traceability fields."""
    hyp = Hypothesis(
        hypothesis_id="h_test_trace_01",
        incident_id="INC-TRACE-001",
        causal_claim="Batching timeout is too high causing pipeline backpressure",
        status=StatusLabel.INFERRED,
        supporting_evidence_ids=["config/worker.yaml", "telemetry/heap.csv"],
        contradicting_evidence_ids=[],
        confidence_prior=0.82,
        confidence_rationale="Derived from config timeout 200ms vs observed frame arrival 100ms",
        provider_execution_id="exec-nebius-nvidia-001",
        expected_observation="Backpressure drops when batching window is reduced",
        falsifying_observation="Backpressure persists despite reducing batching window",
        falsification_criteria="Backpressure persists despite reducing batching window",
        intervention="Reduce batching window from 200ms to 50ms",
    )

    assert hyp.causal_claim == "Batching timeout is too high causing pipeline backpressure"
    assert hyp.supporting_evidence_ids == ["config/worker.yaml", "telemetry/heap.csv"]
    assert hyp.supporting_artifact_ids == ["config/worker.yaml", "telemetry/heap.csv"]
    assert hyp.contradicting_evidence_ids == []
    assert hyp.confidence == 0.82
    assert hyp.confidence_rationale == "Derived from config timeout 200ms vs observed frame arrival 100ms"
    assert hyp.provider_execution_id == "exec-nebius-nvidia-001"
    assert hyp.falsification_criteria == "Backpressure persists despite reducing batching window"
    assert hyp.speculative is False


def test_ungrounded_hypothesis_marked_speculative():
    """Prove hypotheses without supporting evidence are automatically marked speculative."""
    hyp = Hypothesis(
        hypothesis_id="h_speculative_01",
        incident_id="INC-TRACE-002",
        causal_claim="Speculative cause without evidence backing",
        status=StatusLabel.INFERRED,
        supporting_artifact_ids=[],
        expected_observation="Some effect",
        falsifying_observation="No effect",
        intervention="Do something",
    )

    assert hyp.speculative is True
    assert hyp.supporting_evidence_ids == []


def test_field_reconciliation():
    """Prove bidirectional reconciliation between legacy and canonical fields."""
    hyp1 = Hypothesis(
        hypothesis_id="h_rec_01",
        causal_claim="Reconciled from artifact IDs",
        supporting_artifact_ids=["art-1", "art-2"],
        contradicting_artifact_ids=["art-contra"],
        falsifying_observation="Observed failure",
        expected_observation="Normal behavior",
        intervention="Fix parameter",
    )
    assert hyp1.supporting_evidence_ids == ["art-1", "art-2"]
    assert hyp1.contradicting_evidence_ids == ["art-contra"]
    assert hyp1.falsification_criteria == "Observed failure"
    assert hyp1.speculative is False

    hyp2 = Hypothesis(
        hypothesis_id="h_rec_02",
        causal_claim="Reconciled from evidence IDs",
        supporting_evidence_ids=["ev-1"],
        contradicting_evidence_ids=["ev-contra"],
        falsification_criteria="Criteria condition",
        expected_observation="Normal behavior",
        intervention="Fix parameter",
    )
    assert hyp2.supporting_artifact_ids == ["ev-1"]
    assert hyp2.contradicting_artifact_ids == ["ev-contra"]
    assert hyp2.falsifying_observation == "Criteria condition"


@pytest.mark.asyncio
async def test_hypothesis_generator_traceability(tmp_path):
    """Prove generator populates incident_id, evidence IDs, and derivation rationales."""
    # Create minimal incident bundle
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    config_dir = bundle_dir / "config"
    config_dir.mkdir()
    (config_dir / "worker.yaml").write_text("batching_window_ms: 200\n", encoding="utf-8")
    (bundle_dir / "manifest.yaml").write_text("incident_id: INC-GEN-TRACE\n", encoding="utf-8")

    incident = Incident(
        id="INC-GEN-TRACE",
        title="Batching Latency Incident",
        bundle_path=str(bundle_dir),
    )

    hg = HypothesisGenerator()
    hyps = await hg.generate(incident)

    assert len(hyps) > 0
    for h in hyps:
        assert h.incident_id == "INC-GEN-TRACE"
        assert h.falsification_criteria != ""
        assert h.confidence_rationale is not None
        assert isinstance(h.supporting_evidence_ids, list)
        assert isinstance(h.contradicting_evidence_ids, list)

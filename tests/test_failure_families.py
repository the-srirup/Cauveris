"""
The pipeline must be able to work on an incident it has never seen before.

These tests cover the generalisation axis that makes that true: an incident
whose request was *lost* - killed for exceeding its memory ceiling, cancelled
for exceeding a deadline, abandoned on a contended lock - rather than merely
slow.

The rules the tests hold the project to:

* the parameter registry, the twin and the intervention mapper must agree on
  what exists, so a knob cannot be simulated but not patchable;
* a bundle that names a mechanism in its logs must produce that mechanism in
  the model;
* the twin must reproduce the failure on the baseline and clear it after the
  proposed change;
* a hypothesis for such an incident must carry a *structured* proposal, or
  the patch forge has nothing to write.

Nothing here refers to the golden incident.  The bundles are built from
scratch, which is the point: they are incidents the project has not seen.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import yaml

from cauveris.analysis.failure_evidence import extract_failure_evidence
from cauveris.analysis.model import (
    FAILURE_MECHANISMS,
    SimulationOutcome,
    TwinParameters,
    simulate_pipeline,
)
from cauveris.analysis.parameter_registry import (
    PATCHABLE_PARAMETERS,
    PARAMETER_REGISTRY,
    SIMULATABLE_PARAMETERS,
    FailureMechanism,
)
from cauveris.analysis.system_model import build_system_model
from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.simulation.mapping import TWIN_PARAMETERS
from cauveris.schemas.incident import Incident

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "golden_incident" / "incident-CAU-0001"


# ---------------------------------------------------------------------------
# Bundle construction
# ---------------------------------------------------------------------------


def _write_bundle(
    root: Path,
    *,
    config: Dict[str, Any],
    logs: List[str],
    metrics: Optional[str] = None,
) -> Path:
    """Write a minimal incident bundle."""
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "config" / "service.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    (root / "logs" / "service.log").write_text("\n".join(logs) + "\n", encoding="utf-8")
    (root / "manifest.yaml").write_text(
        yaml.safe_dump({"incident_id": root.name, "title": "synthetic incident"}),
        encoding="utf-8",
    )
    if metrics:
        (root / "metrics").mkdir(parents=True, exist_ok=True)
        (root / "metrics" / "memory.csv").write_text(metrics, encoding="utf-8")
    return root


_BASE_CONFIG: Dict[str, Any] = {
    "dynamic_batching": {"batching_window_ms": 100, "max_batch_size": 8},
    "qos": {"queue_depth": 5},
    "server": {"worker_count": 2},
    "safety": {"detection_freshness_budget_ms": 400},
}


def _memory_bundle(root: Path) -> Path:
    config = dict(_BASE_CONFIG)
    config["resources"] = {"memory_limit_mb": 512}
    return _write_bundle(
        root,
        config=config,
        logs=[
            "2026-09-20T10:29:58Z WARN service: request served in 42 ms",
            "2026-09-20T10:29:59Z ERROR service: container killed: OOMKilled, "
            "memory limit exceeded (used 1400 MB of 512 MiB)",
            "2026-09-20T10:29:59Z ERROR service: request served in 41 ms",
        ],
        metrics=(
            "timestamp,memory_used_mb,memory_total_mb,memory_utilization_percent\n"
            "2026-09-20T10:29:58Z,1100,8192,13\n"
            "2026-09-20T10:29:59Z,1400,8192,17\n"
        ),
    )


def _timeout_bundle(root: Path) -> Path:
    config = dict(_BASE_CONFIG)
    config["server"] = {"worker_count": 2, "request_timeout_ms": 120}
    return _write_bundle(
        root,
        config=config,
        logs=[
            "2026-09-20T10:29:58Z WARN service: request served in 42 ms",
            "2026-09-20T10:29:59Z ERROR service: upstream request timed out after "
            "500 ms (deadline 120 ms), work discarded",
        ],
    )


def _lock_bundle(root: Path) -> Path:
    config = dict(_BASE_CONFIG)
    config["locks"] = {"lock_timeout_ms": 200}
    # The caller allows 700 ms for the whole call, and the control loop
    # tolerates a 700 ms old frame.  The lock is held for 480 ms, so the
    # acquire deadline - not the hold - is what has to change.
    config["server"] = {"worker_count": 2, "request_timeout_ms": 700}
    config["safety"] = {"detection_freshness_budget_ms": 700}
    return _write_bundle(
        root,
        config=config,
        logs=[
            "2026-09-20T10:29:58Z WARN service: request served in 42 ms",
            "2026-09-20T10:29:59Z ERROR service: lock wait timeout - acquire timed "
            "out after 200 ms, lock held for 480 ms",
        ],
    )


def _database_bundle(root: Path) -> Path:
    config = dict(_BASE_CONFIG)
    config["database"] = {"max_connections": 10, "connection_timeout_ms": 5000}
    return _write_bundle(
        root,
        config=config,
        logs=[
            "2026-09-20T10:29:58Z INFO pgpool: connection granted to client 9",
            "2026-09-20T10:29:59Z ERROR pgpool: connection pool exhausted: "
            "active connections 35 exceeded pool capacity 10 (remaining: 0)",
        ],
    )


def _incident(bundle: Path) -> Incident:
    return Incident(
        id=bundle.name,
        title="synthetic incident",
        manifest={},
        bundle_path=str(bundle),
    )


def _hypotheses(bundle: Path) -> List[Any]:
    return asyncio.run(HypothesisGenerator().generate(_incident(bundle)))


def _by_id(hypotheses: List[Any], hypothesis_id: str) -> Any:
    for hypothesis in hypotheses:
        if hypothesis.hypothesis_id == hypothesis_id:
            return hypothesis
    return None


# ---------------------------------------------------------------------------
# The registry, the twin and the mapper must agree
# ---------------------------------------------------------------------------


def test_every_registered_parameter_is_a_twin_parameter():
    """A parameter the registry knows must be one the twin can simulate."""
    fields = set(TwinParameters().as_dict())
    missing = sorted(set(PARAMETER_REGISTRY) - fields)
    assert not missing, f"registered but not simulated: {missing}"


def test_patchable_parameters_are_simulatable():
    """A parameter a patch may change must be one the twin accepts."""
    assert set(PATCHABLE_PARAMETERS) <= set(SIMULATABLE_PARAMETERS)


def test_the_intervention_mapper_accepts_exactly_the_patchable_parameters():
    """
    The mapper must not accept a measured quantity.

    ``resource_demand_mb`` is the working set the incident needed.  If an
    intervention could set it, a patch could "fix" an out-of-memory kill by
    rewriting the measurement of the working set.
    """
    assert set(TWIN_PARAMETERS) == set(PATCHABLE_PARAMETERS)
    assert "resource_demand_mb" not in TWIN_PARAMETERS
    assert "lock_hold_ms" not in TWIN_PARAMETERS


def test_the_failure_mechanisms_are_the_ones_the_model_counts():
    assert set(FAILURE_MECHANISMS) == set(FailureMechanism.ALL)


def test_a_lock_deadline_is_not_read_as_a_request_deadline():
    """
    ``lock_timeout_ms`` contains ``timeout_ms`` as a substring.

    The needle matcher resolves both keys, so the more specific one has to
    be selected deliberately - otherwise a lock deadline is given the
    remediation for a request deadline.
    """
    from cauveris.analysis.parameters import match_parameter

    assert match_parameter("locks.lock_timeout_ms") == "lock_timeout_ms"
    assert match_parameter("server.request_timeout_ms") == "request_timeout_ms"


# ---------------------------------------------------------------------------
# Reading the mechanism out of an unfamiliar bundle
# ---------------------------------------------------------------------------


def test_a_memory_incident_names_the_memory_mechanism(tmp_path):
    bundle = _memory_bundle(tmp_path / "incident-CAU-9001")
    evidence = extract_failure_evidence(bundle.root and __import__(
        "cauveris.analysis.evidence", fromlist=["EvidenceBundle"]
    ).EvidenceBundle.load(bundle))
    assert evidence is not None
    assert evidence.mechanism == FailureMechanism.RESOURCE_EXHAUSTION
    assert evidence.parameters["resource_limit_mb"] == 512
    # The measured working set, not the machine's total memory.
    assert evidence.parameters["resource_demand_mb"] == 1400


def test_a_timeout_incident_names_the_timeout_mechanism(tmp_path):
    from cauveris.analysis.evidence import EvidenceBundle

    bundle = _timeout_bundle(tmp_path / "incident-CAU-9002")
    evidence = extract_failure_evidence(EvidenceBundle.load(bundle))
    assert evidence is not None
    assert evidence.mechanism == FailureMechanism.DEPENDENCY_TIMEOUT
    assert evidence.parameters["request_timeout_ms"] == 120
    # The call was still in flight at 500 ms, so the model's latency has to
    # be able to reach that.
    assert evidence.observations["observed_failure_latency_ms"] == 500


def test_a_lock_incident_names_the_lock_mechanism(tmp_path):
    from cauveris.analysis.evidence import EvidenceBundle

    bundle = _lock_bundle(tmp_path / "incident-CAU-9003")
    evidence = extract_failure_evidence(EvidenceBundle.load(bundle))
    assert evidence is not None
    assert evidence.mechanism == FailureMechanism.LOCK_CONTENTION
    assert evidence.parameters["lock_timeout_ms"] == 200
    assert evidence.parameters["lock_hold_ms"] == 480


def test_a_database_incident_names_the_connection_pool_mechanism(tmp_path):
    from cauveris.analysis.evidence import EvidenceBundle

    bundle = _database_bundle(tmp_path / "incident-CAU-9005")
    evidence = extract_failure_evidence(EvidenceBundle.load(bundle))
    assert evidence is not None
    assert evidence.mechanism == FailureMechanism.CONNECTION_POOL_EXHAUSTION
    assert evidence.parameters["db_pool_size"] == 10
    assert evidence.parameters["db_demand_connections"] == 35


def test_a_latency_incident_names_no_mechanism(tmp_path):
    """
    A bundle in which nothing was lost is a latency incident.

    Reporting a failure mechanism that the evidence does not support would
    send an operator after the wrong knob.
    """
    from cauveris.analysis.evidence import EvidenceBundle

    bundle = _write_bundle(
        tmp_path / "incident-CAU-9004",
        config=_BASE_CONFIG,
        logs=[
            "2026-09-20T10:29:58Z WARN service: detection age 340 ms exceeds the "
            "120 ms budget; request served in 300 ms",
        ],
    )
    assert extract_failure_evidence(EvidenceBundle.load(bundle)) is None


# ---------------------------------------------------------------------------
# The twin reproduces the failure and the fix clears it
# ---------------------------------------------------------------------------


def _simulate(params: TwinParameters) -> SimulationOutcome:
    return simulate_pipeline(params, duration_s=20.0, warmup_s=20.0, seed=7)


def test_the_twin_reproduces_a_memory_kill_and_a_larger_envelope_clears_it():
    params = TwinParameters(
        batching_window_ms=100,
        max_batch_size=8,
        server_workers=2,
        resource_limit_mb=512,
        resource_demand_mb=1400,
    )
    baseline = _simulate(params)
    assert baseline.failure_reasons.get(FailureMechanism.RESOURCE_EXHAUSTION, 0) > 0

    fixed = TwinParameters(**{**params.as_dict(), "resource_limit_mb": 2048})
    after = _simulate(fixed)
    assert after.failure_reasons.get(FailureMechanism.RESOURCE_EXHAUSTION, 0) == 0


def test_the_twin_reproduces_a_deadline_miss_and_a_shorter_window_clears_it():
    params = TwinParameters(
        batching_window_ms=400,
        max_batch_size=8,
        server_workers=1,
        service_base_ms=20,
        service_per_item_ms=5,
        request_timeout_ms=100,
    )
    baseline = _simulate(params)
    assert baseline.failure_reasons.get(FailureMechanism.DEPENDENCY_TIMEOUT, 0) > 0

    fixed = TwinParameters(**{**params.as_dict(), "batching_window_ms": 20})
    after = _simulate(fixed)
    assert after.failure_reasons.get(FailureMechanism.DEPENDENCY_TIMEOUT, 0) == 0


def test_the_twin_reproduces_a_lock_abandonment_and_a_longer_deadline_clears_it():
    params = TwinParameters(
        batching_window_ms=20,
        max_batch_size=4,
        server_workers=2,
        lock_contention_prob=0.5,
        lock_hold_ms=480,
        lock_timeout_ms=200,
    )
    baseline = _simulate(params)
    assert baseline.failure_reasons.get(FailureMechanism.LOCK_CONTENTION, 0) > 0

    fixed = TwinParameters(**{**params.as_dict(), "lock_timeout_ms": 600})
    after = _simulate(fixed)
    assert after.failure_reasons.get(FailureMechanism.LOCK_CONTENTION, 0) == 0


def test_the_twin_reproduces_a_connection_pool_exhaustion_and_a_larger_pool_clears_it():
    params = TwinParameters(
        batching_window_ms=20,
        max_batch_size=4,
        server_workers=2,
        db_pool_size=10.0,
        db_demand_connections=35.0,
        db_connection_timeout_ms=5000.0,
    )
    baseline = _simulate(params)
    assert baseline.failure_reasons.get(FailureMechanism.CONNECTION_POOL_EXHAUSTION, 0) > 0

    fixed = TwinParameters(**{**params.as_dict(), "db_pool_size": 50.0})
    after = _simulate(fixed)
    assert after.failure_reasons.get(FailureMechanism.CONNECTION_POOL_EXHAUSTION, 0) == 0


def test_a_failure_is_not_reported_as_latency():
    """A killed request produced no result; it must not be counted as slow."""
    params = TwinParameters(
        batching_window_ms=20,
        max_batch_size=4,
        resource_limit_mb=512,
        resource_demand_mb=1400,
    )
    outcome = _simulate(params)
    assert outcome.failed_requests > 0
    assert outcome.failure_rate > 0.0
    assert outcome.resource_pressure > 1.0


# ---------------------------------------------------------------------------
# The model carries the mechanism into the twin
# ---------------------------------------------------------------------------


def test_the_system_model_seeds_the_envelope_from_the_configuration(tmp_path):
    bundle = _memory_bundle(tmp_path / "incident-CAU-9011")
    model = build_system_model("CAU-9011", bundle)
    assert model is not None
    assert model.failure_evidence is not None
    assert model.failure_evidence.mechanism == FailureMechanism.RESOURCE_EXHAUSTION
    assert model.parameters.resource_limit_mb == 512
    assert model.parameters.resource_demand_mb >= 512


def test_the_calibration_does_not_drop_the_mechanism(tmp_path):
    """
    The calibration rebuilds the parameter set.

    When it named every field explicitly, a parameter added later was
    silently dropped, and the twin could not see the failure it was meant
    to reproduce.
    """
    bundle = _memory_bundle(tmp_path / "incident-CAU-9012")
    model = build_system_model("CAU-9012", bundle)
    assert model is not None
    assert model.calibration is not None
    assert model.calibration.params.resource_limit_mb == 512
    assert model.calibration.params.resource_demand_mb > 0


# ---------------------------------------------------------------------------
# The hypothesis must carry a proposal the pipeline can act on
# ---------------------------------------------------------------------------


def test_a_memory_incident_produces_a_patchable_proposal(tmp_path):
    bundle = _memory_bundle(tmp_path / "incident-CAU-9021")
    hypothesis = _by_id(_hypotheses(bundle), "h_memory_exhaustion")
    assert hypothesis is not None, "the memory incident produced no hypothesis"
    assert hypothesis.proposed_changes, "the hypothesis proposes no change"
    change = hypothesis.proposed_changes[0]
    assert change.parameter == "resource_limit_mb"
    assert change.target_value is not None
    assert change.target_value > 512
    assert change.config_key == "resources.memory_limit_mb"
    assert change.file == "config/service.yaml"


def test_a_timeout_incident_produces_a_patchable_proposal(tmp_path):
    bundle = _timeout_bundle(tmp_path / "incident-CAU-9022")
    hypothesis = _by_id(_hypotheses(bundle), "h_dependency_timeout")
    assert hypothesis is not None
    assert hypothesis.proposed_changes
    parameters = {change.parameter for change in hypothesis.proposed_changes}
    # The request has to come back inside the deadline it already has:
    # raising the deadline is not a fix.
    assert "request_timeout_ms" not in parameters
    assert parameters & {"batching_window_ms", "server_workers"}


def test_a_lock_incident_produces_a_patchable_proposal(tmp_path):
    bundle = _lock_bundle(tmp_path / "incident-CAU-9023")
    hypothesis = _by_id(_hypotheses(bundle), "h_lock_contention")
    assert hypothesis is not None
    assert hypothesis.proposed_changes
    change = hypothesis.proposed_changes[0]
    assert change.parameter == "lock_timeout_ms"
    assert change.target_value is not None
    assert change.target_value >= 480


def test_a_database_incident_produces_a_patchable_proposal(tmp_path):
    bundle = _database_bundle(tmp_path / "incident-CAU-9025")
    hypothesis = _by_id(_hypotheses(bundle), "h_connection_pool_exhaustion")
    assert hypothesis is not None
    assert hypothesis.proposed_changes
    change = hypothesis.proposed_changes[0]
    assert change.parameter == "db_pool_size"
    assert change.target_value is not None
    assert change.target_value >= 35


def test_every_proposed_change_names_a_parameter_the_registry_knows(tmp_path):
    for builder in (_memory_bundle, _timeout_bundle, _lock_bundle, _database_bundle):
        bundle = builder(tmp_path / f"incident-{builder.__name__}")
        for hypothesis in _hypotheses(bundle):
            for change in hypothesis.proposed_changes:
                assert change.parameter in PARAMETER_REGISTRY
                assert change.parameter in TWIN_PARAMETERS
                assert change.target_value is not None


# ---------------------------------------------------------------------------
# The whole chain: evidence -> proposal -> intervention -> twin
# ---------------------------------------------------------------------------


def _plan_for(hypothesis: Any) -> Any:
    from cauveris.simulation.mapping import map_hypothesis_to_intervention

    return map_hypothesis_to_intervention(
        hypothesis_id=hypothesis.hypothesis_id,
        intervention=hypothesis.intervention,
        likely_parameters=list(hypothesis.likely_parameters or []),
        causal_claim=hypothesis.causal_claim,
        proposed_changes=[change.as_dict() for change in hypothesis.proposed_changes],
    )


def _apply(params: TwinParameters, overrides: Dict[str, float]) -> TwinParameters:
    return TwinParameters(**{**params.as_dict(), **overrides})


@pytest.mark.parametrize(
    "builder,mechanism,hypothesis_id",
    [
        (_memory_bundle, FailureMechanism.RESOURCE_EXHAUSTION, "h_memory_exhaustion"),
        (_timeout_bundle, FailureMechanism.DEPENDENCY_TIMEOUT, "h_dependency_timeout"),
        (_lock_bundle, FailureMechanism.LOCK_CONTENTION, "h_lock_contention"),
        (_database_bundle, FailureMechanism.CONNECTION_POOL_EXHAUSTION, "h_connection_pool_exhaustion"),
    ],
)
def test_the_proposed_change_clears_the_failure_in_the_twin(
    tmp_path, builder, mechanism, hypothesis_id
):
    """
    The chain the whole project rests on.

    Evidence names a mechanism, the model reproduces it, the hypothesis
    proposes a change, the change becomes an intervention, and the
    intervention clears the failure in the twin.  A break anywhere in that
    chain is a show rather than a tool, so it is tested end to end.
    """
    bundle = builder(tmp_path / f"incident-{hypothesis_id}")
    model = build_system_model("CAU-" + hypothesis_id, bundle)
    assert model is not None

    hypothesis = _by_id(_hypotheses(bundle), hypothesis_id)
    assert hypothesis is not None, "no hypothesis was produced for the incident"

    plan = _plan_for(hypothesis)
    assert plan.parameter_overrides, "the hypothesis produced no intervention"

    baseline = simulate_pipeline(
        model.parameters, duration_s=20.0, warmup_s=20.0, seed=7
    )
    assert (
        baseline.failure_reasons.get(mechanism, 0) > 0
    ), f"the model does not reproduce the {mechanism} failure"

    patched = simulate_pipeline(
        _apply(model.parameters, plan.parameter_overrides),
        duration_s=20.0,
        warmup_s=20.0,
        seed=7,
    )
    assert (
        patched.failure_reasons.get(mechanism, 0) == 0
    ), (
        f"the intervention did not clear the {mechanism} failure: "
        f"{patched.failure_reasons}"
    )


def test_the_golden_latency_incident_still_produces_its_hypotheses():
    """The generalisation must not cost the incident the project already has."""
    hypotheses = _hypotheses(GOLDEN)
    assert _by_id(hypotheses, "h_batching_window_latency") is not None

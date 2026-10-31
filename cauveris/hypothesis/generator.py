"""
Hypothesis generator: turns an incident bundle into falsifiable root-cause
hypotheses.

Every hypothesis is derived from the incident's own evidence through the
analysis layer's :class:`SystemModel`.  Nothing in this module knows about a
particular incident id.  An incident whose clocks are in sync does not get a
clock-skew hypothesis; one whose link is fast does not get a network
hypothesis; one whose GPU never left 40% utilisation does not get a
contention hypothesis.  A hypothesis is emitted only when the bundle holds
evidence for it, each one states the measurement that would falsify it, and
the confidence is computed from that evidence rather than asserted.

The generator therefore works on an incident it has never seen: the rules
below read the *roles* the configuration plays (batch window, queue depth,
freshness budget, ...) and the measured stages of the data path, never the
names of particular files or incidents.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


from cauveris.analysis import (
    ParameterRole,
    SimulationOutcome,
    SystemModel,
    arrival_rate_evidence,
    flatten_config,
    get_system_model,
)
from cauveris.analysis.failure_evidence import (
    LOCK_NEEDLES,
    MEMORY_NEEDLES,
    TIMEOUT_NEEDLES,
    DB_POOL_NEEDLES,
    FailureEvidence,
    classify_log_records,
    extract_all_mechanisms,
)
from cauveris.analysis.parameter_registry import FailureMechanism
from cauveris.analysis.parameters import find_parameter_in_tree, parse_config_file
from cauveris.analysis.system_model import classify_parameter
from cauveris.config import get_settings
from cauveris.model_gateway import create_model_gateway
from cauveris.model_gateway.base import ModelGateway, ModelResponse
from cauveris.model_gateway.enums import ModelAssistanceStatus, ModelTaskType
from cauveris.schemas.base import StatusLabel
from cauveris.schemas.hypothesis import Hypothesis, ProposedChange
from cauveris.schemas.incident import Incident

logger = logging.getLogger(__name__)

#: A stage of the data path only becomes a candidate cause when it accounts
#: for at least this fraction of the declared safety budget.
_MATERIAL_BUDGET_SHARE = 0.05

#: The batching window only matters when the timer, not the batch size,
#: closes the epoch.  Below this share of the age, the wait is noise.
_MIN_WAIT_SHARE = 0.15

#: Artefact categories, matched the way the evidence loader matches them: by
#: the kind of artefact, not by its file name.
_ARTEFACT_HINTS: Dict[str, Tuple[str, ...]] = {
    "traces": ("trace", "otel", "span"),
    "logs": ("log", "event", "journal"),
    "metrics": ("metric", "telemetry", "gpu", "network", "perf", "resource"),
    "recordings": ("recording", "mcap", "bag", "rosbag"),
    "notes": ("observation", "note", "readme", "report", "postmortem"),
}

def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _numeric(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Markers that leaked chain-of-thought preambles start with when a model
# emits its reasoning inline instead of structured fields.
_COT_MARKERS = (
    "here's a thinking process",
    "here is a thinking process",
    "thinking process:",
    "chain-of-thought:",
    "chain of thought:",
    "step-by-step reasoning:",
    "let me think through this",
)


def _strip_cot_preamble(text: str) -> str:
    """Remove a leaked chain-of-thought preamble from model-emitted text.

    Some providers prepend reasoning like "Here's a thinking process: ..."
    to fields that should hold only the conclusion. Keep the conclusion,
    drop the reasoning trace.
    """
    if not text:
        return text
    cleaned = text.strip()
    low = cleaned.lower()
    for marker in _COT_MARKERS:
        idx = low.find(marker)
        if idx != -1 and idx <= 60:
            rest = cleaned[idx + len(marker):].lstrip(":- \t\n")
            if rest:
                cleaned = rest
            break
    # Even without a marker, drop leading bullet/numbered reasoning lines
    # when a plain declarative line follows.
    lines = cleaned.splitlines()
    if len(lines) > 1 and all(
        ln.strip().lower().startswith(("1.", "2.", "3.", "-", "*", "step ")) for ln in lines[:2]
    ):
        cleaned = lines[-1].strip()
    return " ".join(cleaned.split())[:500]


@dataclass
class _Evidence:
    """Everything a rule needs in order to decide whether a hypothesis holds."""

    incident: Incident
    bundle_path: Optional[Path]
    model: Optional[SystemModel]
    categories: Dict[str, List[str]] = field(default_factory=dict)
    _predictions: Dict[str, SimulationOutcome] = field(default_factory=dict)

    # ---------------------------------------------------------------- helpers

    def artefacts(self, category: str) -> List[str]:
        """Real artefact paths of a category, for use as evidence citations."""
        return list(self.categories.get(category, ()))

    def predict(self, **overrides: Any) -> Optional[SimulationOutcome]:
        """Re-simulate the incident under modified configuration (memoised)."""
        if self.model is None:
            return None
        key = json.dumps(overrides, sort_keys=True, default=str)
        cached = self._predictions.get(key)
        if cached is None:
            cached = self.model.predict(overrides)
            self._predictions[key] = cached
        return cached

    def config_entries(self) -> List[Tuple[str, str, Any]]:
        """Every (file, dotted key, value) the bundle's configuration declares."""
        entries: List[Tuple[str, str, Any]] = []
        if self.bundle_path is None:
            return entries
        for rel in self.categories.get("config", ()):
            path = self.bundle_path / rel
            data = parse_config_file(path)
            if data is None:
                continue
            for key, value in flatten_config(data).items():
                entries.append((rel, key, value))
        return entries

    def config_match(self, needles: Sequence[str]) -> Optional[Tuple[str, str, Any]]:
        """The first declared configuration entry whose key matches a needle."""
        lowered = [n.lower() for n in needles]
        for rel, key, value in self.config_entries():
            if any(needle in key.lower() for needle in lowered):
                return rel, key, value
        return None


class HypothesisGenerator:
    """Generates root-cause hypotheses from incident evidence."""

    def __init__(self, model_gateway: Optional[ModelGateway] = None):
        self.settings = get_settings()
        self.last_assistance_status: ModelAssistanceStatus = (
            ModelAssistanceStatus.MODEL_ASSISTANCE_NOT_REQUIRED
        )
        if model_gateway is None:
            # In production, this will use NebiusModelGateway if NEBIUS_API_KEY is set
            # For testing, pass force_local=True to use LocalModelGateway
            self.model_gateway = create_model_gateway()
        else:
            self.model_gateway = model_gateway

    # ------------------------------------------------------------------ API

    async def generate(self, incident: Incident) -> List[Hypothesis]:
        """
        Generate hypotheses for the incident based on evidence analysis.

        Args:
            incident: Incident with normalized timeline and evidence

        Returns:
            List of Hypothesis objects, most confident first
        """
        logger.info(f"Generating hypotheses for incident {incident.id}")
        evidence = self._collect_evidence(incident)

        hypotheses: List[Hypothesis] = []

        # Evidence-derived hypotheses.  Each rule decides for itself whether
        # the bundle supports it; a rule that finds no support returns None.
        #
        # The rules below all explain a *latency* incident: the request
        # arrived, and it was too old to act on.  When the logs name a
        # concrete mechanism - a killed process, a cancelled request, an
        # abandoned acquire - the requests were **lost** instead, and a
        # latency knob cannot recover them.  Offering one anyway would put a
        # patch in front of the operator that cannot fix the incident they
        # reported, so the latency rules stand down and the mechanism's own
        # hypothesis is the one that is investigated.  The freshness budget
        # is still asserted by the verifier, so a patch that trades a lost
        # request for a stale one still fails.
        mechanism = self._incident_mechanism(evidence)
        if mechanism is None:
            for rule in (
                self._rule_batching_window,
                self._rule_arrival_rate,
                self._rule_consumer_sampling,
                self._rule_subscriber_buffer,
                self._rule_transport,
                self._rule_resource_contention,
                self._rule_clock_skew,
            ):
                try:
                    hypothesis = rule(evidence)
                except Exception as exc:  # a broken rule must not kill the rest
                    logger.warning(f"Hypothesis rule {rule.__name__} failed: {exc}")
                    continue
                if hypothesis is not None:
                    hypotheses.append(hypothesis)
        else:
            logger.info(
                f"The logs name the {mechanism} mechanism, so the request was lost "
                "rather than late; the latency rules are not offered for this incident."
            )

        # Domain-agnostic failure patterns recovered from the logs.
        hypotheses.extend(self._rule_log_patterns(evidence))

        # A model gateway may contribute a hypothesis the rules did not reach.
        gateway_hypothesis = await self._gateway_hypothesis(incident, evidence)
        if gateway_hypothesis is not None:
            hypotheses.append(gateway_hypothesis)

        if not hypotheses:
            logger.warning("Could not generate specific hypotheses, using fallback")
            hypotheses.append(self._fallback_hypothesis(incident))

        # Every hypothesis carries the bundle it was derived from.  Without it
        # the later stages have to guess which incident they are working on,
        # and the guess is usually the one whose files happen to be lying
        # around - which is how a synthetic incident ends up being simulated
        # against the demo bundle.
        bundle_path = evidence.bundle_path
        for hypothesis in hypotheses:
            hypothesis.incident_id = incident.id
            if not hypothesis.supporting_evidence_ids and hypothesis.supporting_artifact_ids:
                hypothesis.supporting_evidence_ids = list(hypothesis.supporting_artifact_ids)
            if not hypothesis.falsification_criteria:
                hypothesis.falsification_criteria = hypothesis.falsifying_observation or "Counterfactual test does not reproduce failure"
            if not hypothesis.confidence_rationale:
                count = len(hypothesis.supporting_evidence_ids)
                hypothesis.confidence_rationale = (
                    f"Evidence-grounded derivation across {count} artifact(s) with prior {hypothesis.confidence_prior:.2f}"
                    if count > 0
                    else "Speculative proposal without direct evidence citations"
                )
            hypothesis.speculative = bool(not hypothesis.supporting_evidence_ids)

            if bundle_path is not None:
                try:
                    hypothesis.bundle_path = str(bundle_path)
                except Exception:  # a frozen hypothesis is not fatal
                    logger.debug("Could not record the bundle path on a hypothesis")

        hypotheses.sort(key=lambda h: h.confidence_prior, reverse=True)
        logger.info(
            f"Generated {len(hypotheses)} hypotheses for incident {incident.id}: "
            f"{[h.hypothesis_id for h in hypotheses]}"
        )
        return hypotheses

    # ------------------------------------------------------------- evidence

    def _incident_mechanism(self, ev: _Evidence) -> Optional[str]:
        """
        The failure mechanism the incident's own logs name, if any.

        The reading comes from the analysis layer, so the hypothesis layer and
        the model that reproduces the incident cannot disagree about what
        happened.  ``None`` means the incident named no mechanism at all, which
        is the case for a latency incident: the data arrived, and it was too
        old to act on.
        """
        model = ev.model
        if model is None:
            return None
        evidence = getattr(model, "failure_evidence", None)
        if evidence is None:
            return None
        mechanism = getattr(evidence, "mechanism", None)
        return str(mechanism) if mechanism else None

    def _collect_evidence(self, ev_incident: Incident) -> _Evidence:
        """Locate the bundle, build the system model, index the artefacts."""
        bundle_path = self._locate_bundle_path(ev_incident)
        model = self._load_system_model(ev_incident, bundle_path)
        categories = self._categorise_artefacts(bundle_path)
        return _Evidence(
            incident=ev_incident,
            bundle_path=bundle_path,
            model=model,
            categories=categories,
        )

    def _locate_bundle_path(self, incident: Incident) -> Optional[Path]:
        """
        Locate the bundle directory for an incident.

        The search is by incident id, never by a hard-coded bundle: an
        incident uploaded as ``CAU-1234`` is looked for in the evidence store,
        next to the working directory, and in any ``incident-*`` directory that
        ends with its id.
        """
        candidates: List[Path] = []
        if getattr(incident, "bundle_path", None):
            candidates.append(Path(incident.bundle_path))
        if incident.manifest and incident.manifest.get("bundle_path"):
            candidates.append(Path(incident.manifest["bundle_path"]))

        incident_id = str(incident.id or "").strip()
        candidates.append(Path(self.settings.evidence_store_path) / incident_id)
        candidates.append(Path(f"./packages/incident-{incident_id}"))
        candidates.append(Path(f"./packages/{incident_id}"))
        candidates.append(Path(f"./packages/demo/{incident_id}"))
        candidates.append(Path(f"./incident-{incident_id}"))

        # Any bundle directory named after the incident, however its parent
        # directory is called: ``incident-<id>`` in the working directory or
        # one or two levels below it (e.g. inside packages/ or root).
        if incident_id:
            try:
                candidates.extend(sorted(Path(".").glob(f"incident-{incident_id}")))
                candidates.extend(sorted(Path(".").glob(f"*/incident-{incident_id}")))
                candidates.extend(sorted(Path("packages").glob(f"*/incident-{incident_id}")))
            except OSError:
                pass

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate

        # Last resort: any directory whose name ends with the incident id.
        if incident_id:
            for root in (Path("."), Path(self.settings.evidence_store_path)):
                if not root.is_dir():
                    continue
                try:
                    children = sorted(root.glob(f"**/*{incident_id}"))
                except OSError:
                    continue
                for child in children:
                    if child.is_dir() and child.name.endswith(incident_id):
                        return child
        return None

    def _load_system_model(
        self, incident: Incident, bundle_path: Optional[Path]
    ) -> Optional[SystemModel]:
        """Build (or reuse) the evidence-derived system model for the bundle."""
        if bundle_path is None:
            return None
        return get_system_model(
            str(incident.id),
            bundle_path,
            timeline_events=list(getattr(incident, "timeline_events", []) or []),
            manifest=dict(incident.manifest or {}),
        )

    def _categorise_artefacts(self, bundle_path: Optional[Path]) -> Dict[str, List[str]]:
        """Group the bundle's files by the kind of artefact they are."""
        categories: Dict[str, List[str]] = {name: [] for name in _ARTEFACT_HINTS}
        categories["config"] = []
        categories["deployments"] = []
        categories["sources"] = []
        categories["other"] = []
        if bundle_path is None:
            return categories

        for path in sorted(bundle_path.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(bundle_path).as_posix()
            lowered = rel.lower()
            if lowered.startswith("source/"):
                categories["sources"].append(rel)
                continue
            if "deploy" in lowered:
                categories["deployments"].append(rel)
                continue
            if path.suffix.lower() in (".yaml", ".yml", ".json") and (
                "config" in lowered or "param" in lowered or "setting" in lowered
            ):
                categories["config"].append(rel)
                continue
            for category, hints in _ARTEFACT_HINTS.items():
                if any(hint in lowered for hint in hints):
                    categories[category].append(rel)
                    break
            else:
                categories["other"].append(rel)
        return categories

    # ----------------------------------------------------------------- rules

    def _rule_batching_window(self, ev: _Evidence) -> Optional[Hypothesis]:
        """
        The batching window set the epoch duration, and the wait blew the budget.

        This rule only fires in the *window-limited* regime: when the batch
        fills before the timer fires, the window is not what the latency is
        waiting on, and shortening it cannot help.
        """
        model = ev.model
        if model is None or not model.has_fitted_model():
            return None
        # The window has to be declared by the bundle and the budget has to be
        # declared too: without both, "the window is too long" is a statement
        # about defaults, not about this incident.
        if not model.declares("batching_window_ms") or not model.declares_budget():
            return None

        params = model.parameters
        budget = model.budget.freshness_budget_ms
        baseline = ev.predict()
        if baseline is None:
            return None

        age = baseline.mean_age_ms
        wait = baseline.mean_epoch_wait_ms
        if age <= 0 or wait <= 0:
            return None
        if baseline.size_limited_fraction >= 0.5:
            # The batch filled before the timer: the window is a bystander.
            return None

        wait_share = wait / age
        if wait_share < _MIN_WAIT_SHARE:
            return None

        delta = model.delta_for_role(ParameterRole.BATCH_WINDOW)
        current = params.batching_window_ms
        target, target_outcome, feasible = self._largest_feasible_window(
            ev, current, delta
        )

        config_match = ev.config_match(
            ("batch_window", "batching_window", "batch_timeout", "batching_delay")
        )
        config_file = config_match[0] if config_match else ""
        config_key = config_match[1] if config_match else "batching_window_ms"
        parameter = config_key.split(".")[-1]

        artefacts: List[str] = []
        artefacts += ev.artefacts("traces")[:1]
        artefacts += ev.artefacts("metrics")[:1]
        artefacts += ev.artefacts("logs")[:1]
        if config_file:
            artefacts.append(config_file)
        if delta and delta.file and delta.file not in artefacts:
            artefacts.append(delta.file)
        deployment = model.anomaly_onset_correlated_deployment
        if deployment is not None:
            artefacts += ev.artefacts("deployments")[:1]

        contradicting: List[str] = []
        missing = [
            "Per-batch size and wait-time telemetry at the inference server",
            "An arrival-rate measurement independent of the queue-depth counter",
        ]
        if delta is not None and delta.deployment_id:
            contradicting.append(
                "the deployment record shows the window change as an intentional revision"
            )

        gap_text = self._deployment_gap_text(model)
        claim = (
            f"The dynamic batching window of {current:.0f} ms set the epoch duration: "
            f"{wait_share * 100:.0f}% of the modelled detection age ({wait:.1f} ms of "
            f"{age:.1f} ms) was spent waiting for the batch to close, and the modelled age "
            f"is {'above' if age > budget else 'within'} the {budget:.0f} ms freshness budget."
        )
        if delta is not None and delta.numeric:
            old, new = delta.numeric
            claim += (
                f" The window was changed from {old:.0f} ms to {new:.0f} ms"
                + (f", {gap_text}" if gap_text else "")
                + "."
            )
        elif deployment is not None:
            claim += (
                f" The most recent rollout before the onset was {deployment.deployment_id}"
                f"{gap_text}."
            )

        if feasible:
            expected = (
                f"With the window at {target:.0f} ms the model predicts a mean age of "
                f"{target_outcome.mean_age_ms:.1f} ms (from {age:.1f} ms), a 95th-percentile age "
                f"of {target_outcome.p95_age_ms:.1f} ms and a stale rate of "
                f"{target_outcome.stale_rate * 100:.1f}% (from {baseline.stale_rate * 100:.1f}%), "
                f"which meets the {budget:.0f} ms budget on all three."
            )
            falsifying = (
                f"The stale rate does not fall when the window is reduced to {target:.0f} ms, or "
                f"the 95th-percentile age stays above {budget:.0f} ms"
            )
            intervention = (
                f"Reduce {parameter} to {target:.0f} ms in "
                f"{config_file or 'the inference configuration'} (was {current:.0f} ms)"
            )
        else:
            expected = (
                f"Reducing the window removes most of the wait but does not make the pipeline "
                f"compliant on its own: at {target:.0f} ms the model predicts a mean age of "
                f"{target_outcome.mean_age_ms:.1f} ms (from {age:.1f} ms), a 95th-percentile age "
                f"of {target_outcome.p95_age_ms:.1f} ms and a stale rate of "
                f"{target_outcome.stale_rate * 100:.1f}% (from "
                f"{baseline.stale_rate * 100:.1f}%), against a {budget:.0f} ms budget."
            )
            falsifying = (
                f"Some window below {target:.0f} ms brings the 95th-percentile age and the stale "
                f"rate inside the {budget:.0f} ms budget, in which case the window is the only "
                f"thing that needs to change"
            )
            intervention = (
                f"Reduce {parameter} to {target:.0f} ms in "
                f"{config_file or 'the inference configuration'} (was {current:.0f} ms); this "
                f"removes the wait but is not sufficient on its own, because the pipeline still "
                f"cannot meet the {budget:.0f} ms budget at that window"
            )

        deployment_support = 0.0
        if delta is not None and deployment is not None:
            deployment_support = 1.0 if delta.deployment_id == deployment.deployment_id else 0.5
        elif delta is not None:
            deployment_support = 0.5

        pressure = _clamp(age / budget) if budget > 0 else 0.0
        strength = _clamp(wait_share / 0.5)
        confidence = _clamp(
            0.15 + 0.55 * strength + 0.20 * pressure + 0.10 * deployment_support
        )
        confidence *= self._contradiction_discount(model)

        return Hypothesis(
            hypothesis_id="h_batching_window_latency",
            causal_claim=claim,
            status=StatusLabel.INFERRED,
            supporting_artifact_ids=artefacts,
            contradicting_artifact_ids=contradicting,
            missing_evidence=missing,
            confidence_prior=round(confidence, 3),
            expected_observation=expected,
            falsifying_observation=falsifying,
            intervention=intervention,
            estimated_trials=3,
            estimated_cost=0.6,
            likely_files=[config_file] if config_file else [],
            likely_parameters=[config_key],
            safety_constraints=[
                f"Keep the perception update rate at or above {model.budget.required_rate_hz:g} Hz",
                "Do not relax the freshness budget to hide the excess",
            ],
            proposed_changes=[
                ProposedChange(
                    parameter="batching_window_ms",
                    current_value=round(current, 3),
                    target_value=round(target, 3),
                    file=config_file or None,
                    config_key=config_key or None,
                    rationale=(
                        f"The wait for the batch to close is {wait_share * 100:.0f}% of the "
                        f"modelled detection age, so shortening the window removes it"
                    ),
                    sufficient_on_its_own=feasible,
                )
            ],
        )

    def _rule_arrival_rate(self, ev: _Evidence) -> Optional[Hypothesis]:
        """
        Frames arrived faster than the server could retire them.

        The queue-depth slope is a lower bound on the arrival rate, and the
        fitted service time gives the rate the server can absorb; when the
        first exceeds the second the backlog must grow.
        """
        model = ev.model
        if model is None or not model.has_fitted_model():
            return None

        evidence = arrival_rate_evidence(model)
        growth = evidence.get("from_backlog")
        observed_batch = evidence.get("observed_batch")
        implied_from_batch = evidence.get("from_batch")
        contradiction = self._contradiction_ratio(model)

        baseline = ev.predict()
        if baseline is None:
            return None

        params = model.parameters
        service_ms = params.service_base_ms + params.service_per_item_ms
        capacity_per_worker_hz = 1000.0 / service_ms if service_ms > 0 else 0.0
        workers = max(1, int(params.server_workers))
        capacity_hz = capacity_per_worker_hz * workers

        overloaded = bool(growth and growth > 1.0)
        saturated = baseline.server_utilisation >= 0.9
        if not (overloaded or saturated):
            return None

        artefacts = ev.artefacts("metrics")[:1] + ev.artefacts("logs")[:1]
        if not artefacts:
            return None

        contradicting: List[str] = []
        missing = [
            "Server-side request-rate telemetry",
            "Mean service time per frame at the server",
        ]
        if contradiction and observed_batch and implied_from_batch:
            contradicting.append(
                f"the recorded batch of {observed_batch:.0f} frames implies only "
                f"{implied_from_batch:.1f} Hz of arrivals, {contradiction:.1f}x fewer than "
                f"the queue growth requires"
            )

        if growth:
            claim = (
                f"Frames arrived faster than the inference server could retire them: the queue "
                f"depth grew at {growth:.1f} frames/s while the fitted service time of "
                f"{service_ms:.1f} ms per frame lets {workers} worker(s) retire at most "
                f"{capacity_hz:.1f} frames/s."
            )
            expected = (
                f"The queue-depth series keeps rising at about {growth:.1f} frames/s and the "
                f"modelled server utilisation stays above 1.0, so the request latency grows "
                f"with the backlog rather than with the frame count."
            )
            falsifying = (
                "The queue depth is flat or falling under the same arrival rate, in which case "
                "the growth was a transient and the server kept up"
            )
        else:
            claim = (
                f"The inference server was saturated: the modelled utilisation was "
                f"{baseline.server_utilisation:.2f} with a fitted service time of "
                f"{service_ms:.1f} ms per frame and {params.server_workers} worker(s)."
            )
            expected = (
                f"The server's utilisation stays at or above {baseline.server_utilisation:.2f} "
                f"while the request latency rises with the backlog."
            )
            falsifying = (
                "The server's utilisation stays below 0.9 with a request latency that still "
                "tracks the backlog"
            )

        strength = 1.0 if growth else 0.6
        if contradiction:
            # One of the two arrival-rate observations has to be wrong, so the
            # cause is honestly less certain than the arithmetic suggests.
            strength *= 0.5
        pressure = (
            _clamp(baseline.mean_age_ms / model.budget.freshness_budget_ms)
            if model.budget.freshness_budget_ms
            else 0.0
        )
        confidence = _clamp(0.15 + 0.55 * strength + 0.20 * pressure)
        confidence *= self._contradiction_discount(model)

        capacity_match = ev.config_match(
            ("worker_count", "num_workers", "pool_size", "max_concurrent", "concurrency")
        )
        if capacity_match:
            intervention = (
                f"Raise the inference capacity declared by {capacity_match[1]} "
                f"({capacity_match[2]}) so that the retired rate exceeds the arrival rate"
            )
            likely_files = [capacity_match[0]]
            likely_parameters = [capacity_match[1]]
        else:
            intervention = (
                f"Add inference capacity: {workers} worker(s) at {service_ms:.1f} ms per frame "
                f"retire at most {capacity_hz:.1f} frames/s, and no capacity knob is declared in "
                f"the bundle's configuration, so the deployment has to change"
            )
            likely_files = []
            likely_parameters = []

        # How many workers the server needs to retire the arriving frames.
        # A quarter of headroom is kept, because a server sized exactly at
        # its arrival rate has no margin for jitter in the service time.
        demanded_hz = growth if growth else capacity_hz * max(baseline.server_utilisation, 0.01)
        needed_workers = max(
            workers + 1,
            int(math.ceil(demanded_hz * 1.25 / capacity_per_worker_hz)) if capacity_per_worker_hz else workers,
        )

        return Hypothesis(
            hypothesis_id="h_server_overload",
            causal_claim=claim,
            status=StatusLabel.INFERRED,
            supporting_artifact_ids=artefacts,
            contradicting_artifact_ids=contradicting,
            missing_evidence=missing,
            confidence_prior=round(confidence, 3),
            expected_observation=expected,
            falsifying_observation=falsifying,
            intervention=intervention,
            estimated_trials=3,
            estimated_cost=2.5,
            likely_files=likely_files,
            likely_parameters=likely_parameters,
            safety_constraints=[
                "Keep the freshness budget enforced while capacity is added",
                "Do not drop frames silently to make the queue look shorter",
            ],
            proposed_changes=[
                ProposedChange(
                    parameter="server_workers",
                    current_value=float(workers),
                    target_value=float(needed_workers),
                    file=capacity_match[0] if capacity_match else None,
                    config_key=capacity_match[1] if capacity_match else None,
                    rationale=(
                        f"{workers} worker(s) retire at most {capacity_hz:.1f} frames/s while "
                        f"{demanded_hz:.1f} frames/s arrive, so the backlog can only grow"
                    ),
                    sufficient_on_its_own=False,
                )
            ],
        )

    def _rule_consumer_sampling(self, ev: _Evidence) -> Optional[Hypothesis]:
        """
        The consumer's own update period puts a floor under the data's age.

        A control loop that samples the perception topic every 100 ms acts on
        data that is, on average, 50 ms old before any inference or transport
        delay has been added.  When the safety budget is only a little above
        that floor, the budget is unreachable no matter how fast the server is.
        """
        model = ev.model
        if model is None or not model.has_fitted_model():
            return None
        # The rate has to be declared: a 10 Hz default is the modeller's
        # assumption, not the robot's requirement.
        if not model.declares("consumer_rate_hz") or not model.declares_budget():
            return None

        rate = model.budget.required_rate_hz
        if not rate or rate <= 0:
            return None
        period_ms = 1000.0 / rate
        baseline = ev.predict()
        if baseline is None:
            return None

        budget = model.budget.freshness_budget_ms
        floor_share = (period_ms / 2.0) / budget if budget > 0 else 0.0
        if floor_share < 0.10:
            return None

        rate_match = ev.config_match(
            ("frequency_hz", "control_hz", "publish_rate", "rate_hz")
        )
        config_file = rate_match[0] if rate_match else ""
        config_key = rate_match[1] if rate_match else ""

        # Cite the file that actually declares the rate, not merely the first
        # configuration file in the bundle.
        artefacts: List[str] = []
        if config_file:
            artefacts.append(config_file)
        for rel in ev.artefacts("config"):
            if rel not in artefacts:
                artefacts.append(rel)
                break
        artefacts += ev.artefacts("traces")[:1]

        sampling = baseline.mean_sampling_delay_ms
        claim = (
            f"The consumer samples perception at {rate:g} Hz, so a detection is on average "
            f"{period_ms / 2.0:.0f} ms old (and up to {period_ms:.0f} ms old) before any "
            f"inference or transport delay is added. That floor is {floor_share * 100:.0f}% of "
            f"the {budget:.0f} ms freshness budget on its own."
        )
        if sampling > 0:
            claim += (
                f" The model attributes {sampling:.1f} ms of the mean age to that sampling "
                f"delay."
            )
        expected = (
            "The age of a frame when it is consumed exceeds the server-side request latency "
            f"plus the transport latency by roughly {sampling:.1f} ms, which matches the "
            f"{period_ms:.0f} ms control period"
        )
        falsifying = (
            "The age excess over the request and transport path stays below 5 ms, in which case "
            "the control loop is triggered by the data rather than by a timer and the period is "
            "not a contributor"
        )

        needed = max(rate * 2.0, rate + 1.0)
        intervention = (
            f"Raise the perception update rate to {needed:.0f} Hz in "
            f"{config_file or 'the robot configuration'}"
            + (f" ({config_key})" if config_key else "")
            + f", or trigger the control loop on the arrival of a new detection instead of on a "
            f"{period_ms:.0f} ms timer"
        )

        strength = _clamp(floor_share / 0.4)
        pressure = _clamp(baseline.mean_age_ms / budget) if budget > 0 else 0.0
        confidence = _clamp(0.15 + 0.55 * strength + 0.20 * pressure)
        confidence *= self._contradiction_discount(model)

        return Hypothesis(
            hypothesis_id="h_consumer_sampling_interval",
            causal_claim=claim,
            status=StatusLabel.INFERRED,
            supporting_artifact_ids=artefacts,
            contradicting_artifact_ids=[],
            missing_evidence=[
                "Timestamps of the frame the control loop actually consumed",
                "The control loop's trigger source (timer versus subscription)",
            ],
            confidence_prior=round(confidence, 3),
            expected_observation=expected,
            falsifying_observation=falsifying,
            intervention=intervention,
            estimated_trials=2,
            estimated_cost=1.0,
            likely_files=[config_file] if config_file else [],
            likely_parameters=[config_key] if config_key else [],
            safety_constraints=[
                "Keep the control loop's own deadline enforced",
                "Do not raise the update rate beyond what the actuator can accept",
            ],
            proposed_changes=[
                ProposedChange(
                    parameter="consumer_rate_hz",
                    current_value=round(rate, 3),
                    target_value=round(needed, 3),
                    file=config_file or None,
                    config_key=config_key or None,
                    rationale=(
                        f"A {rate:g} Hz consumer acts on data that is on average "
                        f"{period_ms / 2.0:.0f} ms old before anything else is added"
                    ),
                    sufficient_on_its_own=False,
                )
            ],
        )

    def _rule_subscriber_buffer(self, ev: _Evidence) -> Optional[Hypothesis]:
        """
        The subscriber's queue can hold frames old enough to matter.

        With a KEEP_ALL history the consumer may act on the oldest frame the
        buffer holds, which is as old as ``depth / rate``.  With KEEP_LAST the
        overflow drops frames instead, which costs throughput rather than
        adding age - a distinction the hypothesis has to make explicitly.
        """
        model = ev.model
        if model is None or model.calibration is None:
            return None

        depth = None
        depth_source = ""
        for rel, key, value in ev.config_entries():
            if classify_parameter(key, value) == ParameterRole.QUEUE_DEPTH:
                number = _numeric(value)
                if number is not None and number > 0:
                    depth = int(number)
                    depth_source = f"{rel}:{key}"
                    break
        if depth is None or depth <= 1:
            return None

        rate = model.budget.required_rate_hz or 10.0
        residency = depth * (1000.0 / rate)
        budget = model.budget.freshness_budget_ms
        if budget <= 0 or residency < 0.05 * budget:
            return None

        keep_all = self._source_declares(ev, ("keep_all", "keepall", "keep-all"))
        artefacts = ev.artefacts("sources")[:2] + ev.artefacts("config")[:1]
        claim = (
            f"The subscriber's queue holds {depth} frames, so the oldest frame it can hold is "
            f"about {residency:.0f} ms old at {rate:g} Hz"
            + (
                " and the history policy keeps every frame, so the consumer may act on one of them"
                if keep_all
                else "; the history policy keeps only the newest, so an overflow drops frames "
                "rather than delivering stale ones"
            )
        )
        expected = (
            f"The consumer's effective age exceeds the delivery age by up to {residency:.0f} ms "
            "when the producer is faster than the consumer"
            if keep_all
            else f"The producer overruns the {rate:g} Hz consumer and the buffer overflows, "
            "dropping frames instead of ageing them"
        )
        falsifying = (
            "The measured age excess over the delivery age stays below 5 ms, in which case the "
            "buffer is never more than one frame deep in practice"
        )
        intervention = (
            "Set the QoS history to KEEP_LAST with a depth of 1 in "
            f"{depth_source.split(':')[0] if depth_source else 'the detection client'}"
        )

        strength = _clamp(residency / (0.25 * budget))
        if not keep_all:
            strength *= 0.6
        confidence = _clamp(0.15 + 0.55 * strength)

        return Hypothesis(
            hypothesis_id="h_subscriber_buffer_staleness",
            causal_claim=claim,
            status=StatusLabel.INFERRED,
            supporting_artifact_ids=artefacts,
            contradicting_artifact_ids=[],
            missing_evidence=["The DDS history policy actually in force at runtime"],
            confidence_prior=round(confidence, 3),
            expected_observation=expected,
            falsifying_observation=falsifying,
            intervention=intervention,
            estimated_trials=2,
            estimated_cost=1.0,
            likely_files=[depth_source.split(":")[0]] if depth_source else [],
            likely_parameters=[depth_source.split(":")[1]] if depth_source else [],
            safety_constraints=[
                "Do not disable delivery of obstacle detections",
                "Keep the consumer non-blocking when the queue is empty",
            ],
            proposed_changes=[
                ProposedChange(
                    parameter="qos_queue_depth",
                    current_value=float(depth),
                    target_value=1.0,
                    file=depth_source.split(":")[0] if depth_source else None,
                    config_key=depth_source.split(":")[1] if depth_source else None,
                    rationale=(
                        f"A {depth}-frame buffer can hold frames up to {residency:.0f} ms old at "
                        f"{rate:g} Hz; a depth of 1 with KEEP_LAST hands over only the newest frame"
                    ),
                    sufficient_on_its_own=True,
                )
            ],
        )

    def _rule_transport(self, ev: _Evidence) -> Optional[Hypothesis]:
        """The link between server and robot added a measurable delay."""
        model = ev.model
        if model is None:
            return None

        transport = model.transport_distribution
        if not transport.count:
            return None
        if not model.declares_budget():
            return None
        budget = model.budget.freshness_budget_ms
        mean = transport.p50
        if budget <= 0 or mean < _MATERIAL_BUDGET_SHARE * budget:
            return None

        baseline = ev.predict()
        symptoms = self._network_symptoms(ev)
        artefacts = ev.artefacts("metrics")[:2] + ev.artefacts("traces")[:1]

        claim = (
            f"The link between the inference host and the robot added {mean:.1f} ms on average "
            "to every detection"
            + (f" with a p95 of {transport.p95:.1f} ms" if transport.count >= 5 else "")
            + f", which is {mean / budget * 100:.0f}% of the {budget:.0f} ms freshness budget"
        )
        if symptoms:
            claim += f" ({symptoms})"
        expected = (
            "The age of each detection exceeds the server-side request latency by roughly the "
            f"measured link latency ({mean:.1f} ms), and the excess tracks the network metric "
            "series sample by sample"
        )
        falsifying = (
            f"The age excess over the server-side request latency stays below 5 ms while the "
            f"network series still shows {mean:.1f} ms, in which case the delay is not on the "
            "link between these two hosts"
        )
        intervention = (
            f"Cut the link latency below {max(1.0, 0.05 * budget):.0f} ms - below 5% of the "
            f"{budget:.0f} ms budget, so the link stops being a material contributor - by "
            f"co-locating the inference workload with the robot or shortening the network path"
        )

        strength = _clamp((mean / budget) / 0.3)
        pressure = (
            _clamp(baseline.mean_age_ms / budget) if baseline and budget > 0 else 0.0
        )
        confidence = _clamp(0.15 + 0.55 * strength + 0.20 * pressure)
        confidence *= self._contradiction_discount(model)

        return Hypothesis(
            hypothesis_id="h_transport_latency",
            causal_claim=claim,
            status=StatusLabel.INFERRED,
            supporting_artifact_ids=artefacts,
            contradicting_artifact_ids=[],
            missing_evidence=["Per-hop latency breakdown between the inference host and the robot"],
            confidence_prior=round(confidence, 3),
            expected_observation=expected,
            falsifying_observation=falsifying,
            intervention=intervention,
            estimated_trials=3,
            estimated_cost=1.8,
            likely_files=[],
            likely_parameters=[],
            safety_constraints=[
                "Keep packet loss at zero on the safety channel",
                "Do not trade latency for reliability on obstacle detections",
            ],
            proposed_changes=[
                ProposedChange(
                    parameter="transport_mean_ms",
                    current_value=round(mean, 3),
                    target_value=round(max(1.0, 0.05 * budget), 3),
                    rationale=(
                        f"The link adds {mean:.1f} ms to every detection, which is "
                        f"{mean / budget * 100:.0f}% of the {budget:.0f} ms budget"
                    ),
                    sufficient_on_its_own=False,
                )
            ],
        )

    def _rule_resource_contention(self, ev: _Evidence) -> Optional[Hypothesis]:
        """A shared resource was close enough to saturation to matter."""
        model = ev.model
        if model is None:
            return None

        series = model.resource_series
        if not series:
            return None

        # Compute-utilisation series only.  Memory and temperature are not
        # compute utilisation: a busy memory subsystem has a different
        # mechanism (allocation stalls, swap) and a different intervention.
        candidates = []
        for label, dist in series.items():
            key = label.split(":", 1)[-1].lower()
            if not any(token in key for token in ("util", "utilization", "utilisation")):
                continue
            if "memory" in key or "swap" in key or "temp" in key:
                continue
            if not dist.count:
                continue
            # Some series report a fraction (0.9) and others a percentage
            # (90).  The scale is decided once, from the peak, and then
            # applied to every point of the distribution.
            scale = 100.0 if dist.maximum > 1.5 else 1.0
            peak = dist.maximum / scale
            floor = dist.minimum / scale
            candidates.append((label, dist, peak, floor))
        if not candidates:
            return None

        label, dist, peak, floor = max(candidates, key=lambda item: item[2])
        if peak < 0.7:
            return None

        budget = model.budget.freshness_budget_ms
        baseline = ev.predict()
        artefacts = ev.artefacts("metrics")[:2]
        device = self._device_name(label)

        claim = (
            f"The {device} utilisation rose to {peak * 100:.0f}% "
            f"(from {floor * 100:.0f}%) during the incident window"
        )
        if peak < 0.999:
            claim += (
                "; it never reached saturation, so the resource is more likely a consequence of "
                "the backlog than the origin of the latency"
            )
        expected = (
            "The resource's utilisation tracks the latency of the requests it serves, and the "
            "request latency falls when the offered load falls"
        )
        falsifying = (
            "The resource stays below 60% utilisation while the request latency still rises, in "
            "which case the resource is not what is limiting the server"
        )
        intervention = (
            f"Cap the batch size that reaches the {device} and give the safety-critical topic a "
            f"dedicated worker so that a busy {device} cannot delay the control path"
        )

        strength = _clamp((peak - 0.7) / 0.3)
        if peak < 0.999:
            strength *= 0.6
        pressure = (
            _clamp(baseline.mean_age_ms / budget) if baseline and budget > 0 else 0.0
        )
        confidence = _clamp(0.15 + 0.55 * strength + 0.20 * pressure)
        confidence *= self._contradiction_discount(model)

        return Hypothesis(
            hypothesis_id="h_resource_contention",
            causal_claim=claim,
            status=StatusLabel.INFERRED,
            supporting_artifact_ids=artefacts,
            contradicting_artifact_ids=[],
            missing_evidence=[
                "Per-kernel execution time and clock/power telemetry for the device",
                "The offered load (requests per second) at the same instant",
            ],
            confidence_prior=round(confidence, 3),
            expected_observation=expected,
            falsifying_observation=falsifying,
            intervention=intervention,
            estimated_trials=3,
            estimated_cost=1.8,
            likely_files=[],
            likely_parameters=[],
            safety_constraints=[
                "Do not exceed the device's power budget",
                "Keep the inference service available for safety-critical detections",
            ],
        )

    def _rule_clock_skew(self, ev: _Evidence) -> Optional[Hypothesis]:
        """The clocks of the two hosts were far enough apart to matter."""
        model = ev.model
        if model is None:
            return None

        skew = model.clock_skew_ms
        budget = model.budget.freshness_budget_ms
        if skew <= 0:
            return None
        if skew < max(1.0, _MATERIAL_BUDGET_SHARE * budget):
            # A sub-millisecond residual is normal for a synchronised pair of
            # hosts and cannot explain a budget that is exceeded by tens of
            # milliseconds.
            return None

        artefacts = ev.artefacts("logs")[:2]
        claim = (
            f"The inference host and the robot disagree about the time by {skew:.2f} ms, which "
            f"is {skew / budget * 100:.0f}% of the {budget:.0f} ms freshness budget, so a "
            "detection's age is misjudged across the boundary"
        )
        expected = (
            "The age computed on the robot differs from the age computed on the server by about "
            f"{skew:.2f} ms, and the difference tracks the recorded offset rather than the load"
        )
        falsifying = (
            "The age computed on both sides agrees within 1 ms for the same request, in which "
            "case the recorded offset is not affecting the measurements"
        )
        intervention = (
            "Re-synchronise both hosts against the same time source and enforce a "
            f"{max(2.0, skew * 2):.0f} ms skew tolerance between them"
        )

        strength = _clamp((skew / budget) / 0.2) if budget > 0 else 0.0
        confidence = _clamp(0.15 + 0.55 * strength)

        return Hypothesis(
            hypothesis_id="h_clock_skew",
            causal_claim=claim,
            status=StatusLabel.INFERRED,
            supporting_artifact_ids=artefacts,
            contradicting_artifact_ids=[],
            missing_evidence=["NTP peer offsets from both hosts at the moment of the incident"],
            confidence_prior=round(confidence, 3),
            expected_observation=expected,
            falsifying_observation=falsifying,
            intervention=intervention,
            estimated_trials=2,
            estimated_cost=0.8,
            likely_files=[],
            likely_parameters=[],
            safety_constraints=[
                "Keep time synchronisation tighter than 10 ms",
                "Never disable timestamp verification",
            ],
        )

    def _rule_log_patterns(self, ev: _Evidence) -> List[Hypothesis]:
        """
        Domain-agnostic failure patterns recovered from the bundle's logs.

        These fire on the log text itself, so they work for incidents whose
        configuration and metrics say nothing about the failure.  The
        patterns are shared with the analysis layer's mechanism reader, so
        the hypothesis that names a mechanism and the model that reproduces
        it cannot drift apart.

        Every hypothesis produced here carries a **structured proposal** - the
        knob to turn and the value to turn it to.  Without one the
        experiment mapper has nothing to apply, the twin simulates an
        unchanged system, and the patch forge returns no patch: the
        incident is diagnosed and then left unfixed.
        """
        model = ev.model
        if model is None:
            return []

        patterns = (
            (
                "h_memory_exhaustion",
                FailureMechanism.RESOURCE_EXHAUSTION,
                MEMORY_NEEDLES,
                "Process memory consumption exceeded its quota, so the process was killed and the "
                "requests it was serving were dropped",
                "Memory usage approaches 100% of the limit immediately before the process dies",
                "Peak memory usage stays below 60% of the limit across the incident window",
                ["memory_limit_mb", "max_heap_size"],
            ),
            (
                "h_dependency_timeout",
                FailureMechanism.DEPENDENCY_TIMEOUT,
                TIMEOUT_NEEDLES,
                "An upstream dependency did not answer inside the client's deadline, so the "
                "request was cancelled and the work was discarded",
                "The downstream call duration rises past the configured timeout and the "
                "cancellation propagates to the caller",
                "Round-trip latency to the dependency stays well inside the configured timeout",
                ["timeout_ms", "connect_timeout", "max_attempts"],
            ),
            (
                "h_lock_contention",
                FailureMechanism.LOCK_CONTENTION,
                LOCK_NEEDLES,
                "Concurrent workers deadlocked on a shared resource, so the requests behind them "
                "stopped being served",
                "The worker pool reaches its maximum size without completing tasks, and the "
                "completion rate collapses",
                "Active worker threads turn over normally and the lock turnaround time stays flat",
                ["lock_timeout_ms", "max_workers"],
            ),
            (
                "h_connection_pool_exhaustion",
                FailureMechanism.CONNECTION_POOL_EXHAUSTION,
                DB_POOL_NEEDLES,
                "Database connection pool capacity was exhausted by concurrent client demand, "
                "causing query and transaction timeouts",
                "Active database connections reach 100% of the pool limit and checkout timeouts appear in logs",
                "Active connection count remains comfortably below the configured pool limit",
                ["db_pool_size", "max_connections", "pool_size"],
            ),
        )

        hypotheses: List[Hypothesis] = []
        logs = model.bundle.logs
        if not logs:
            return hypotheses

        mechanisms = extract_all_mechanisms(model.bundle)
        # The records are grouped by the *analysis layer's* classification, not
        # by a second, private needle match.  A record that mentions a lock is
        # a lock record even when it also says "timeout": re-matching the raw
        # text here would invent a dependency timeout the incident never had,
        # and the pipeline would then spend a patch and a verification run on a
        # failure that did not occur.
        buckets = classify_log_records(model.bundle)

        for (
            hypothesis_id,
            mechanism,
            needles,
            claim,
            expected,
            falsifying,
            parameters,
        ) in patterns:
            matches = buckets.get(mechanism, [])
            if not matches:
                continue

            sources = sorted({record.source for record in matches})
            level = min(
                (record.level for record in matches),
                key=lambda value: {"CRITICAL": 0, "ERROR": 1, "WARN": 2}.get(value, 3),
                default="INFO",
            )
            count = len(matches)
            confidence = _clamp(
                0.35 + 0.10 * min(count, 5) + (0.15 if level in ("CRITICAL", "ERROR") else 0.0)
            )

            family_evidence = mechanisms.get(mechanism)
            changes = self._propose_for_mechanism(
                ev, mechanism, family_evidence
            )

            hypotheses.append(
                Hypothesis(
                    hypothesis_id=hypothesis_id,
                    causal_claim=(
                        f"{claim} ({count} matching log record(s) across {len(sources)} file(s))"
                    ),
                    status=StatusLabel.INFERRED,
                    supporting_artifact_ids=sources,
                    contradicting_artifact_ids=[],
                    missing_evidence=[
                        "A resource or thread dump covering the incident window",
                        "The rate at which the affected call failed",
                    ],
                    confidence_prior=round(confidence, 3),
                    expected_observation=expected,
                    falsifying_observation=falsifying,
                    intervention=self._intervention_text(mechanism, changes),
                    estimated_trials=3,
                    estimated_cost=1.2,
                    likely_files=sources,
                    likely_parameters=parameters,
                    safety_constraints=self._safety_constraints(mechanism, changes),
                    proposed_changes=changes,
                )
            )
        return hypotheses

    # ------------------------------------------------- mechanism remediation

    def _propose_for_mechanism(
        self,
        ev: _Evidence,
        mechanism: str,
        evidence: Optional[FailureEvidence],
    ) -> List[ProposedChange]:
        """
        The configuration change that would clear a mechanism.

        Each family's remediation is derived from the numbers the evidence
        supports, so the proposal is a value rather than an adjective:

        * a **resource exhaustion** is cleared by giving the workload an
          envelope its measured working set fits inside;
        * a **dependency timeout** is cleared by bringing the request
          latency inside the deadline the client set - by shortening the
          wait for the batch, and by serving requests in parallel rather
          than one behind another;
        * a **lock contention** is cleared by giving the caller enough
          patience for the hold time the logs record, bounded by the safety
          budget so the wait can never become a staleness incident.

        The deadline itself is deliberately *not* raised for a timeout: a
        longer deadline does not make a dependency faster, it only makes
        the failure take longer to notice.
        """
        model = ev.model
        if model is None or evidence is None:
            return []

        if mechanism == FailureMechanism.RESOURCE_EXHAUSTION:
            return self._propose_memory(ev, evidence)
        if mechanism == FailureMechanism.DEPENDENCY_TIMEOUT:
            return self._propose_timeout(ev, evidence)
        if mechanism == FailureMechanism.LOCK_CONTENTION:
            return self._propose_lock(ev, evidence)
        if mechanism == FailureMechanism.CONNECTION_POOL_EXHAUSTION:
            return self._propose_connection_pool(ev, evidence)
        return []

    def _declared_in_bundle(
        self, ev: _Evidence, parameter: str
    ) -> Optional[Tuple[str, str, Any]]:
        """Where the bundle declares a parameter: ``(file, key, value)``."""
        root = ev.bundle_path
        if root is None:
            return None
        try:
            found = find_parameter_in_tree(Path(root), parameter)
        except Exception as exc:  # a bundle that cannot be searched is not fatal
            logger.debug("Could not search the bundle for %s: %s", parameter, exc)
            return None
        if found is None:
            return None
        return found

    def _propose_memory(
        self, ev: _Evidence, evidence: FailureEvidence
    ) -> List[ProposedChange]:
        """Give the workload an envelope its measured working set fits inside."""
        limit = evidence.parameters.get("resource_limit_mb", 0.0)
        demand = evidence.parameters.get("resource_demand_mb", 0.0)
        if limit <= 0:
            return []

        headroom_ratio = 1.20
        max_worker_mb: Optional[float] = None
        allocation_step = 128.0
        found_policy = False

        for _rel, key, val in ev.config_entries():
            k = key.lower()
            if "minimum_memory_headroom_ratio" in k or "headroom_ratio" in k:
                n = _numeric(val)
                if n is not None and n > 1.0:
                    headroom_ratio = n
                    found_policy = True
            elif "maximum_worker_memory_mb" in k or "max_memory_mb" in k:
                n = _numeric(val)
                if n is not None and n > 0:
                    max_worker_mb = n
                    found_policy = True
            elif "allocation_step_mb" in k or "step_mb" in k:
                n = _numeric(val)
                if n is not None and n > 0:
                    allocation_step = n
                    found_policy = True

        if found_policy:
            required = max(demand, limit) * headroom_ratio
            if allocation_step > 0:
                target = float(int(math.ceil(required / allocation_step)) * allocation_step)
            else:
                target = float(int(math.ceil(required)))
            if max_worker_mb and target > max_worker_mb:
                target = float(max_worker_mb)
        else:
            # Half again over the larger of the two numbers: enough headroom for
            # the workload to breathe, and not so much that the change is a
            # blank cheque.
            required = max(demand, limit) * 1.5
            target = float(int(math.ceil(required)))

        if target <= limit:
            return []

        declared = self._declared_in_bundle(ev, "resource_limit_mb")
        changes = [
            ProposedChange(
                parameter="resource_limit_mb",
                current_value=round(limit, 3),
                target_value=target,
                file=declared[0] if declared else None,
                config_key=declared[1] if declared else None,
                rationale=(
                    f"The workload needed {demand:.0f} MiB against a {limit:.0f} MiB "
                    f"ceiling, so it was killed. An envelope of {target:.0f} MiB leaves "
                    "the measured working set inside the limit with headroom."
                ),
                sufficient_on_its_own=True,
            )
        ]

        # The envelope is not the only way to stop the kill: a smaller batch
        # holds less of the workload in memory at once.  It is proposed as a
        # second, non-sufficient change only when no specific repair policy is declared.
        if not found_policy:
            batch = ev.model.base_parameters.max_batch_size if ev.model else 0
            if batch and batch > 1:
                declared_batch = self._declared_in_bundle(ev, "max_batch_size")
                changes.append(
                    ProposedChange(
                        parameter="max_batch_size",
                        current_value=float(batch),
                        target_value=float(max(1, batch // 2)),
                        file=declared_batch[0] if declared_batch else None,
                        config_key=declared_batch[1] if declared_batch else None,
                        rationale=(
                            "Halving the batch halves the frames held in memory at once, "
                            "which reduces the working set the envelope has to accommodate."
                        ),
                        sufficient_on_its_own=False,
                    )
                )
        return changes

    def _propose_timeout(
        self, ev: _Evidence, evidence: FailureEvidence
    ) -> List[ProposedChange]:
        """
        Bring the request latency inside the deadline the client set.

        Three knobs shorten a request, and each is used only when it is the
        one that is actually too long:

        * ``max_batch_size`` - the service cost of a batch grows with the
          number of items in it, so a batch the server is allowed to fill
          completely is a batch that is served slowly;
        * ``batching_window_ms`` - the request waits for its batch to close
          before the service even starts;
        * ``server_workers`` - requests that queue behind a busy worker wait
          for the one in front.

        The arithmetic uses the *worst case* the twin simulates, not the
        average: a deadline that is met on average is still a deadline that
        is missed.

        The deadline itself is never raised.  A longer deadline does not make
        a dependency faster; it only makes the failure take longer to notice.
        """
        model = ev.model
        if model is None:
            return []
        deadline = evidence.parameters.get("request_timeout_ms", 0.0)
        if deadline <= 0:
            deadline = model.parameters.request_timeout_ms
        if deadline <= 0:
            return []

        params = model.parameters
        budget = model.budget.freshness_budget_ms

        # A margin, so the request comes back inside the deadline rather than
        # exactly on it.
        margin = max(2.0, deadline * 0.05)
        # The shortest window the server may be given: below this the server
        # stops batching at all.
        min_window = 5.0

        changes: List[ProposedChange] = []

        # --- 1. the service cost of a full batch --------------------------
        service_max = params.service_base_ms + params.service_per_item_ms * max(
            1, int(params.max_batch_size)
        )
        if (
            params.service_per_item_ms > 0
            and params.max_batch_size > 1
            and service_max + margin + min_window > deadline
        ):
            # The service alone does not fit inside the deadline, so the wait
            # cannot be shortened enough to save it: the batch has to be
            # smaller.  This is the *only* way a configuration change makes
            # the service itself faster.
            allowed = int(
                math.floor(
                    (deadline - margin - min_window - params.service_base_ms)
                    / params.service_per_item_ms
                )
            )
            new_max = max(1, min(int(params.max_batch_size) - 1, allowed))
            if new_max < int(params.max_batch_size):
                declared = self._declared_in_bundle(ev, "max_batch_size")
                changes.append(
                    ProposedChange(
                        parameter="max_batch_size",
                        current_value=float(params.max_batch_size),
                        target_value=float(new_max),
                        file=declared[0] if declared else None,
                        config_key=declared[1] if declared else None,
                        rationale=(
                            f"A full batch costs {service_max:.0f} ms to serve, which "
                            f"does not fit inside a {deadline:.0f} ms deadline on its "
                            f"own. Capping the batch at {new_max} item(s) brings the "
                            f"service cost down to "
                            f"{params.service_base_ms + params.service_per_item_ms * new_max:.0f} ms."
                        ),
                        sufficient_on_its_own=False,
                    )
                )
                service_max = params.service_base_ms + (
                    params.service_per_item_ms * new_max
                )

        # --- 2. the wait for the batch to close -----------------------------
        # The wait has to leave room for the service inside the deadline, and
        # the frame must not arrive so late that it is stale either: a lost
        # request traded for a stale one is not a fix.
        ceiling = deadline - margin - service_max
        if budget > 0:
            ceiling = min(
                ceiling, budget - margin - service_max - params.transport_mean_ms
            )
        if ceiling >= min_window:
            target = min(params.batching_window_ms, ceiling)
            if target < params.batching_window_ms * 0.99:
                declared = self._declared_in_bundle(ev, "batching_window_ms")
                changes.append(
                    ProposedChange(
                        parameter="batching_window_ms",
                        current_value=round(params.batching_window_ms, 3),
                        target_value=round(target, 3),
                        file=declared[0] if declared else None,
                        config_key=declared[1] if declared else None,
                        rationale=(
                            f"The request waits for its batch to close before the service "
                            f"even starts. With {service_max:.0f} ms of service inside a "
                            f"{deadline:.0f} ms deadline, the wait has to fit in "
                            f"{max(0.0, ceiling):.0f} ms."
                        ),
                        sufficient_on_its_own=True,
                    )
                )

        # --- 3. the queue behind a busy worker ------------------------------
        # Requests that queue behind a busy worker wait for the one in front.
        # Another worker removes that wait; it is proposed only when the
        # bundle shows a backlog, because adding workers to a system that is
        # idle changes nothing.
        if params.server_workers < 8 and (
            model.queue_depth_samples and max(model.queue_depth_samples) > 1
        ):
            declared = self._declared_in_bundle(ev, "server_workers")
            changes.append(
                ProposedChange(
                    parameter="server_workers",
                    current_value=float(params.server_workers),
                    target_value=float(params.server_workers * 2),
                    file=declared[0] if declared else None,
                    config_key=declared[1] if declared else None,
                    rationale=(
                        "The queue depth grew during the incident, so requests were "
                        "waiting for a busy worker. A second worker serves the next "
                        "request instead of queueing behind it."
                    ),
                    sufficient_on_its_own=False,
                )
            )

        return changes

    def _propose_lock(
        self, ev: _Evidence, evidence: FailureEvidence
    ) -> List[ProposedChange]:
        """
        Let the caller wait for the lock as long as the lock is actually held.

        The acquire deadline is bounded twice, and both bounds matter:

        * by the caller's own deadline on the request - waiting for the lock
          longer than the request allows does not help, it just turns a lock
          failure into a deadline failure;
        * by the freshness budget - a caller that waits that long produces a
          frame that is already stale when it arrives, which is a different
          incident with a worse outcome.

        When the lock is held for longer than both bounds allow, no
        configuration change can fix it: the critical section itself has to be
        shorter, and that is a change to the code rather than to a knob.  In
        that case nothing is proposed, because a proposal the twin cannot
        clear is worse than no proposal.
        """
        model = ev.model
        if model is None:
            return []
        timeout = evidence.parameters.get("lock_timeout_ms", 0.0)
        hold = evidence.parameters.get("lock_hold_ms", 0.0)
        if timeout <= 0 or hold <= 0:
            return []

        params = model.parameters
        budget = model.budget.freshness_budget_ms
        request_deadline = params.request_timeout_ms
        margin = max(2.0, hold * 0.05)

        # The service cost of the batch the caller is waiting for.
        service_max = params.service_base_ms + params.service_per_item_ms * max(
            1, int(params.max_batch_size)
        )

        ceilings: List[float] = []
        if request_deadline > 0:
            ceilings.append(request_deadline - service_max - margin)
        if budget > 0:
            ceilings.append(budget - service_max - margin - params.transport_mean_ms)
        if not ceilings:
            return []
        ceiling = min(ceilings)

        # The hold time is a measurement of one occasion; the deadline has to
        # cover more than it, without waiting for a hold that never happens.
        target = min(hold * 1.25, ceiling)
        if ceiling <= hold:
            # The lock is held for longer than the caller may safely wait, so
            # the fix cannot be a longer wait: the critical section has to be
            # held for less time, which is a change to the code rather than to
            # a knob.  Proposing a deadline that still expires before the
            # hold ends would be a proposal the twin cannot clear.
            logger.info(
                f"The lock is held for {hold:.0f} ms and the caller may safely wait "
                f"for at most {ceiling:.0f} ms, so no acquire deadline can cover the "
                "hold; the critical section itself has to be shortened."
            )
            return []
        if target <= timeout:
            # The ceiling does not even beat the deadline the caller already
            # has, so raising it would not help.
            return []

        declared = self._declared_in_bundle(ev, "lock_timeout_ms")
        return [
            ProposedChange(
                parameter="lock_timeout_ms",
                current_value=round(timeout, 3),
                target_value=round(target, 3),
                file=declared[0] if declared else None,
                config_key=declared[1] if declared else None,
                rationale=(
                    f"The lock is held for {hold:.0f} ms but the caller gives up after "
                    f"{timeout:.0f} ms, so every contended request is abandoned. The "
                    f"acquire deadline is raised to {target:.0f} ms, which covers the "
                    "hold time and stays inside both the request deadline and the "
                    "freshness budget."
                ),
                sufficient_on_its_own=True,
            )
        ]

    def _propose_connection_pool(
        self, ev: _Evidence, evidence: FailureEvidence
    ) -> List[ProposedChange]:
        """Scale database connection pool capacity so peak concurrent query demand fits inside."""
        pool_size = evidence.parameters.get("db_pool_size", 0.0)
        demand = evidence.parameters.get("db_demand_connections", 0.0)
        declared = self._declared_in_bundle(ev, "db_pool_size")
        if pool_size <= 0 and declared:
            try:
                pool_size = float(declared[2])
            except (ValueError, TypeError):
                pool_size = 10.0
        if pool_size <= 0:
            return []

        target = float(int(math.ceil(max(demand, pool_size) * 1.5)))
        if target <= pool_size:
            target = pool_size * 2.0

        return [
            ProposedChange(
                parameter="db_pool_size",
                current_value=round(pool_size, 1),
                target_value=round(target, 1),
                file=declared[0] if declared else None,
                config_key=declared[1] if declared else None,
                rationale=(
                    f"Peak connection demand ({demand:.0f} connections) exhausted the configured "
                    f"pool limit ({pool_size:.0f} connections). Scaling pool capacity to {target:.0f} "
                    "connections restores headroom and prevents connection checkout timeouts."
                ),
                sufficient_on_its_own=True,
            )
        ]

    def _intervention_text(
        self, mechanism: str, changes: Sequence[ProposedChange]
    ) -> str:
        """The intervention, described in words as well as in structured form."""
        if not changes:
            if mechanism == FailureMechanism.RESOURCE_EXHAUSTION:
                return (
                    "Give the workload a memory envelope its measured working set fits "
                    "inside, and halve the batch so less of it is held in memory at once."
                )
            if mechanism == FailureMechanism.DEPENDENCY_TIMEOUT:
                return (
                    "Bring the request inside the deadline the client set: shorten the "
                    "wait for the batch to close, and serve requests concurrently instead "
                    "of one behind another."
                )
            if mechanism == FailureMechanism.CONNECTION_POOL_EXHAUSTION:
                return (
                    "Scale the connection pool capacity so peak concurrent query demand "
                    "fits inside, eliminating checkout timeouts."
                )
            return (
                "Give the caller enough patience for the lock it is waiting on, bounded "
                "by the safety budget, and impose a global lock order so the wait cannot "
                "grow without bound."
            )

        parts = []
        for change in changes:
            where = change.config_key or change.parameter
            if change.file:
                where = f"{where} in {change.file}"
            parts.append(f"{where}: {change.current_value} -> {change.target_value}")
        return "; ".join(parts) + "."

    def _safety_constraints(
        self, mechanism: str, changes: Sequence[ProposedChange]
    ) -> List[str]:
        """The constraints a trial of this hypothesis must respect."""
        constraints = [
            "Keep the safety watchdog active while the fix is trialled",
            "Do not disable the limit that raised the failure",
        ]
        if mechanism == FailureMechanism.DEPENDENCY_TIMEOUT:
            constraints.append(
                "Do not raise the request deadline to hide a slow dependency: the "
                "request has to come back inside the deadline it already has"
            )
        if mechanism == FailureMechanism.LOCK_CONTENTION:
            constraints.append(
                "The acquire deadline must stay inside the safety budget, so a longer "
                "wait can never turn a lost request into a stale one"
            )
        if mechanism == FailureMechanism.RESOURCE_EXHAUSTION:
            constraints.append(
                "The new envelope must fit the host's available memory; a limit the "
                "machine cannot honour is not a fix"
            )
        if mechanism == FailureMechanism.CONNECTION_POOL_EXHAUSTION:
            constraints.append(
                "The scaled connection pool must not exceed upstream database server maximum connection limits"
            )
        return constraints


    # --------------------------------------------------------------- helpers

    def _largest_feasible_window(
        self,
        ev: _Evidence,
        current: float,
        delta: Any,
    ) -> Tuple[float, SimulationOutcome, bool]:
        """
        The largest batching window whose modelled age still meets the budget.

        The candidates are the value the window was rolled back from (if the
        deployment recorded one) and a geometric ladder below the current
        value.  The window has to be searched for rather than guessed: a
        shorter window is not automatically safe, because a shorter epoch means
        a smaller batch and a less efficient server.

        "Meets the budget" means three things at once - the mean age, the 95th
        percentile age and the stale rate all have to hold.  Checking only the
        mean would call a window feasible while one detection in five is still
        too old to act on.
        """
        model = ev.model
        budget = model.budget.freshness_budget_ms if model else 0.0

        rollback: Optional[float] = None
        candidates: List[float] = []
        if delta is not None:
            pair = delta.numeric
            if pair and 0 < pair[0] < current:
                rollback = float(pair[0])
                candidates.append(rollback)
        window = current
        while window > 5.0:
            window /= 2.0
            candidates.append(window)
        candidates.append(5.0)

        ordered: List[float] = []
        for candidate in sorted(candidates, reverse=True):
            if not any(abs(candidate - seen) < 1e-6 for seen in ordered):
                ordered.append(candidate)

        # If the incident exhibits a known deployment rollback target (e.g. v41
        # prior value), it is preferred - the system demonstrably ran with it.
        # But being a value the system has run with is not the same as being a
        # value that meets the budget: the rollback restored the *latency*, not
        # necessarily the *freshness*.  So the rollback is only preferred when
        # the model says it is actually compliant.
        if rollback is not None:
            outcome = ev.predict(batching_window_ms=rollback)
            if outcome is not None and self._outcome_within_budget(outcome, budget):
                return rollback, outcome, True

        last: Optional[SimulationOutcome] = None
        for candidate in ordered:
            outcome = ev.predict(batching_window_ms=candidate)
            if outcome is None:
                continue
            last = outcome
            if self._outcome_within_budget(outcome, budget):
                return candidate, outcome, True

        # Nothing meets the budget.  Then the recommendation has to be a value
        # the system has demonstrably run with, not an invented one - so the
        # rollback wins over the smallest window the ladder produced.
        if rollback is not None:
            outcome = ev.predict(batching_window_ms=rollback)
            if outcome is not None:
                return rollback, outcome, False

        fallback = ordered[-1] if ordered else current
        outcome = ev.predict(batching_window_ms=fallback)
        final_outcome = outcome or last or ev.predict() or SimulationOutcome()
        return fallback, final_outcome, False

    @staticmethod
    def _outcome_within_budget(outcome: SimulationOutcome, budget_ms: float) -> bool:
        """Whether a simulated outcome satisfies the freshness budget."""
        if budget_ms <= 0:
            return False
        return (
            outcome.mean_age_ms <= budget_ms
            and outcome.p95_age_ms <= budget_ms
            and outcome.stale_rate <= 0.02
        )

    @staticmethod
    def _device_name(label: str) -> str:
        """
        The name of the device a resource series describes.

        Resource series are labelled ``"<path>:<key>"`` (``metrics/gpu.csv:
        gpu_utilization``).  The device is the file the samples came from, not
        the path it was stored under: "GPU", not "metrics/gpu.csv".
        """
        series = label.split(":", 1)[0]
        stem = Path(series).stem or series
        acronyms = {"gpu", "cpu", "npu", "tpu", "fpga", "soc"}
        if stem.lower() in acronyms:
            return stem.upper()
        return stem.replace("_", " ") or "device"

    def _contradiction_discount(self, model: SystemModel) -> float:
        """
        Discount confidence when the evidence contradicts itself.

        A hypothesis built on evidence that another part of the bundle
        contradicts has to be less confident than one built on evidence that
        agrees with itself.
        """
        critical = [
            finding
            for finding in model.consistency_findings
            if finding.get("severity") == "critical"
        ]
        if not critical:
            return 1.0
        return max(0.7, 0.9 ** len(critical))

    def _contradiction_ratio(self, model: SystemModel) -> Optional[float]:
        """The factor by which the two arrival-rate estimates disagree."""
        for finding in model.consistency_findings:
            if finding.get("id") == "arrival-rate-disagreement":
                detail = str(finding.get("detail", ""))
                match = re.search(r"\((\d+(?:\.\d+)?)x higher\)", detail)
                if match:
                    return float(match.group(1))
                return 2.0
        return None

    def _deployment_gap_text(self, model: SystemModel) -> str:
        """How long before the anomaly onset the correlated deployment landed."""
        deployment = model.anomaly_onset_correlated_deployment
        onset = model.change_point_time
        if deployment is None or deployment.timestamp is None or onset is None:
            return ""
        seconds = (onset - deployment.timestamp).total_seconds()
        if seconds <= 0:
            return " and landed after the onset"
        if seconds >= 3600:
            return f", {seconds / 3600:.1f} h before the anomaly onset"
        return f", {seconds / 60:.0f} min before the anomaly onset"

    def _network_symptoms(self, ev: _Evidence) -> str:
        """
        Packet loss and jitter, if the bundle's network series records them.

        Samples are summarised as a range: listing every sample ("jitter of 1
        ms and jitter of 2 ms and ...") reads as noise and buries the shape.
        """
        model = ev.model
        if model is None:
            return ""
        losses: List[float] = []
        jitters: List[float] = []
        for series_name, samples in (model.bundle.metrics or {}).items():
            if "network" not in series_name.lower():
                continue
            for sample in samples:
                loss = sample.get("packet_loss")
                jitter = sample.get("jitter")
                if loss is not None and loss > 0:
                    losses.append(float(loss))
                if jitter is not None and jitter > 0:
                    jitters.append(float(jitter))
        details: List[str] = []
        if losses:
            details.append(
                f"packet loss of {min(losses):g}-{max(losses):g}%"
                if min(losses) != max(losses)
                else f"packet loss of {min(losses):g}%"
            )
        if jitters:
            details.append(
                f"jitter of {min(jitters):g}-{max(jitters):g} ms"
                if min(jitters) != max(jitters)
                else f"jitter of {min(jitters):g} ms"
            )
        if not details:
            return ""
        return "the link also shows " + " and ".join(details)

    def _source_declares(self, ev: _Evidence, needles: Sequence[str]) -> bool:
        """Whether any source file in the bundle declares one of the tokens."""
        model = ev.model
        if model is None:
            return False
        lowered = [n.lower() for n in needles]
        for text in (model.bundle.source_files or {}).values():
            haystack = text.lower()
            if any(needle in haystack for needle in lowered):
                return True
        return False

    # -------------------------------------------------------------- gateway

    async def _gateway_hypothesis(
        self, incident: Incident, ev: _Evidence
    ) -> Optional[Hypothesis]:
        """Ask the model gateway for a hypothesis grounded in the evidence."""
        if not self.model_gateway.is_available():
            self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_UNAVAILABLE
            return None

        self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_RUNNING
        prompt = self._build_prompt(incident, ev)
        response: Optional[ModelResponse] = None
        try:
            try:
                response = await self.model_gateway.generate(
                    prompt=prompt,
                    schema=Hypothesis,
                    task_type=ModelTaskType.HYPOTHESIS_PROPOSAL,
                    incident_id=incident.id,
                    incident_context={
                        "incident_id": incident.id,
                        "title": incident.title,
                        "evidence_categories": list(ev.categories.keys()),
                    },
                )
            except TypeError as te:
                if "unexpected keyword argument" in str(te):
                    response = await self.model_gateway.generate(
                        prompt=prompt,
                        schema=Hypothesis,
                    )
                else:
                    raise
            logger.info(f"Model gateway response provider: {response.provider}")
        except Exception as exc:
            logger.warning(f"Model gateway query failed: {exc}")
            self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_FAILED
            return None

        if response is None:
            self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_FAILED
            return None
        if not getattr(response, "inference", True):
            # The provider returned something, but not an inference - a
            # template, a placeholder, a deterministic default.  Presenting it
            # as a conclusion about this incident would be a mock disguised as
            # a result, so it is dropped and the evidence rules carry the
            # analysis on their own.
            logger.info(
                "Ignoring the gateway answer from %s: it is not an inference",
                response.provider,
            )
            self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_REJECTED
            return None

        self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_VALIDATING
        if response.structured_data and isinstance(response.structured_data, dict):
            data = dict(response.structured_data)
            # Real models emit natural-language statuses ("CONFIRMED", "PROVEN", ...)
            # that are not valid StatusLabel values - coerce instead of dropping
            # the model's entire causal analysis on one bad field.
            raw_status = str(data.get("status", "")).strip().upper()
            data["status"] = raw_status if raw_status in StatusLabel.__members__ else "INFERRED"
            try:
                conf = float(data.get("confidence_prior", 0.85))
            except (TypeError, ValueError):
                conf = 0.85
            # Deterministic confidence ceiling: model confidence can never exceed 0.85
            data["confidence_prior"] = min(0.85, max(0.0, conf))

            # Coerce string fields to lists if the LLM emitted a single string instead of array
            for list_field in ["missing_evidence", "supporting_artifact_ids", "likely_parameters"]:
                if isinstance(data.get(list_field), str):
                    data[list_field] = [data[list_field]]
                elif data.get(list_field) is None:
                    data[list_field] = []

            # The id is derived from the incident and the provider that
            # produced it, never from the model's own choice: two runs of the
            # same provider on two different incidents must not collide, and
            # the same incident must always get the same identifier.
            data["hypothesis_id"] = f"hyp-{incident.id}-{response.provider}"
            data["incident_id"] = incident.id
            data["provider_execution_id"] = getattr(response, "execution_id", None) or getattr(response, "request_id", None) or f"exec-{incident.id}-{response.provider}"
            data.setdefault(
                "confidence_rationale",
                f"Generated by {response.provider} assistance under bounded validation constraints",
            )
            data.setdefault(
                "causal_claim", "Model-inferred root cause from multi-source incident analysis"
            )
            data.setdefault("status", "INFERRED")
            data.setdefault(
                "expected_observation", "Latency anomaly correlates with the parameter change"
            )
            data.setdefault(
                "falsifying_observation", "Counterfactual test does not reproduce latency spike"
            )
            data.setdefault(
                "falsification_criteria", "Counterfactual test does not reproduce latency spike"
            )
            data.setdefault(
                "intervention", "Tune configuration to the pre-incident baseline parameters"
            )
            # Never persist a leaked reasoning trace as the causal claim.
            if isinstance(data.get("causal_claim"), str):
                data["causal_claim"] = _strip_cot_preamble(data["causal_claim"])
            if isinstance(data.get("confidence_rationale"), str):
                data["confidence_rationale"] = _strip_cot_preamble(
                    data["confidence_rationale"]
                )[:300]
            try:
                hyp = Hypothesis(**data)
                self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_ACCEPTED
                return hyp
            except Exception as val_err:
                logger.warning(
                    f"Could not construct Hypothesis from model structured data: {val_err}"
                )
                self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_REJECTED

        if response.content:
            first_line = _strip_cot_preamble(response.content.strip().split("\n")[0][:250])
            self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_PARTIAL
            return Hypothesis(
                hypothesis_id=f"hyp-{incident.id}-{response.provider}",
                incident_id=incident.id,
                causal_claim=first_line or f"AI-inferred root cause for {incident.title}",
                status=StatusLabel.INFERRED,
                supporting_artifact_ids=[],
                confidence_prior=0.85,
                confidence_rationale=f"Model text inference from {response.provider} (speculative due to ungrounded raw text)",
                provider_execution_id=getattr(response, "execution_id", None) or getattr(response, "request_id", None) or f"exec-{incident.id}-{response.provider}",
                expected_observation="Observed anomaly aligns with the model's reasoning",
                falsifying_observation=(
                    "Targeted counterfactual perturbation fails to restore baseline"
                ),
                falsification_criteria="Targeted counterfactual perturbation fails to restore baseline",
                intervention="Apply the model-recommended parameter correction",
                speculative=True,
            )
        self.last_assistance_status = ModelAssistanceStatus.MODEL_ASSISTANCE_REJECTED
        return None

    def _build_prompt(self, incident: Incident, ev: _Evidence) -> str:
        """Build a prompt from the evidence, not from a fixed set of fields."""
        model = ev.model
        summary: Dict[str, Any] = {
            "incident_id": incident.id,
            "title": incident.title,
            "safety_budget": model.budget.as_dict() if model else {},
            "artefacts": {name: paths[:4] for name, paths in ev.categories.items() if paths},
        }
        if model is not None:
            summary["config_deltas"] = [delta.as_dict() for delta in model.config_deltas]
            summary["calibration"] = model.calibration.as_dict() if model.calibration else None
            summary["consistency_findings"] = model.consistency_findings
            summary["notes"] = model.notes[:6]
            summary["kinematics"] = model.kinematics.as_dict()
        return (
            "Analyse this incident and formulate ONE falsifiable root-cause hypothesis "
            "with an expected observation, a falsifying observation and a concrete "
            "intervention.\n"
            f"Evidence summary:\n{json.dumps(summary, default=str, indent=2)}\n"
        )

    # -------------------------------------------------------------- fallback

    def _fallback_hypothesis(self, incident: Incident) -> Hypothesis:
        """
        The honest last resort: say what is known and what is missing.

        It is emitted only when the bundle yielded no hypothesis at all, so it
        states plainly that the evidence is not sufficient to name a cause.
        """
        return Hypothesis(
            hypothesis_id="h_unclassified_latency_excess",
            causal_claim=(
                "The bundle does not contain the evidence needed to name a specific cause: no "
                "stage-level latency breakdown, no configuration delta and no resource series "
                "were recovered, so the incident remains unclassified"
            ),
            status=StatusLabel.INFERRED,
            supporting_artifact_ids=["manifest.yaml"],
            contradicting_artifact_ids=[],
            missing_evidence=[
                "A stage-by-stage latency profile of the perception path",
                "The configuration in force before and after the incident",
                "The rate at which detections were requested and served",
            ],
            confidence_prior=0.2,
            expected_observation="The measurable latency exceeds the declared safety budget",
            falsifying_observation="The measured latency stays inside the declared safety budget",
            intervention=(
                "Capture the missing evidence (traces across the server boundary, the network "
                "metric series and the deployment history) and re-run the analysis"
            ),
            estimated_trials=1,
            estimated_cost=0.2,
            likely_files=[],
            likely_parameters=[],
            safety_constraints=["Keep the safety watchdog active while the evidence is gathered"],
        )

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

import yaml

from cauveris.analysis import (
    ParameterRole,
    SimulationOutcome,
    SystemModel,
    arrival_rate_evidence,
    flatten_config,
    get_system_model,
)
from cauveris.analysis.system_model import classify_parameter
from cauveris.config import get_settings
from cauveris.model_gateway import create_model_gateway
from cauveris.model_gateway.base import ModelGateway, ModelResponse
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
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                if path.suffix.lower() in (".yaml", ".yml"):
                    data = yaml.safe_load(text)
                else:
                    data = json.loads(text)
            except Exception:
                continue
            if not isinstance(data, dict):
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

        # Domain-agnostic failure patterns recovered from the logs.
        hypotheses.extend(self._rule_log_patterns(evidence))

        # A model gateway may contribute a hypothesis the rules did not reach.
        gateway_hypothesis = await self._gateway_hypothesis(incident, evidence)
        if gateway_hypothesis is not None:
            hypotheses.append(gateway_hypothesis)

        if not hypotheses:
            logger.warning("Could not generate specific hypotheses, using fallback")
            hypotheses.append(self._fallback_hypothesis(incident))

        hypotheses.sort(key=lambda h: h.confidence_prior, reverse=True)
        logger.info(
            f"Generated {len(hypotheses)} hypotheses for incident {incident.id}: "
            f"{[h.hypothesis_id for h in hypotheses]}"
        )
        return hypotheses

    # ------------------------------------------------------------- evidence

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
        candidates.append(Path(f"./incident-{incident_id}"))

        # Any bundle directory named after the incident, however its parent
        # directory is called: ``incident-<id>`` in the working directory or
        # one level below it.
        if incident_id:
            try:
                candidates.extend(sorted(Path(".").glob(f"incident-{incident_id}")))
                candidates.extend(sorted(Path(".").glob(f"*/incident-{incident_id}")))
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
        configuration and metrics say nothing about the failure.
        """
        model = ev.model
        if model is None:
            return []

        patterns = (
            (
                "h_memory_exhaustion",
                (r"\boom\b", r"out of memory", r"memory limit", r"cgroup", r"heap"),
                "Process memory consumption exceeded its quota, so the process was killed and the "
                "requests it was serving were dropped",
                "Memory usage approaches 100% of the limit immediately before the process dies",
                "Peak memory usage stays below 60% of the limit across the incident window",
                "Increase the container memory quota and fix the allocation that grows without "
                "bound",
                ["memory_limit_mb", "max_heap_size"],
            ),
            (
                "h_dependency_timeout",
                (r"timed? ?out", r"timeout", r"connection refused", r"connection reset"),
                "An upstream dependency did not answer inside the client's deadline, so the "
                "request was cancelled and the work was discarded",
                "The downstream call duration rises past the configured timeout and the "
                "cancellation propagates to the caller",
                "Round-trip latency to the dependency stays well inside the configured timeout",
                "Give the dependency a circuit breaker with bounded retries and a deadline "
                "derived from the safety budget",
                ["timeout_ms", "connect_timeout", "max_attempts"],
            ),
            (
                "h_lock_contention",
                (r"deadlock", r"lock timeout", r"pool exhausted", r"thread starvation"),
                "Concurrent workers deadlocked on a shared resource, so the requests behind them "
                "stopped being served",
                "The worker pool reaches its maximum size without completing tasks, and the "
                "completion rate collapses",
                "Active worker threads turn over normally and the lock turnaround time stays flat",
                "Impose a global lock order and a bounded acquire timeout so a contended lock "
                "cannot stall the pool",
                ["lock_timeout_ms", "max_workers"],
            ),
        )

        hypotheses: List[Hypothesis] = []
        logs = model.bundle.logs
        if not logs:
            return hypotheses

        for (
            hypothesis_id,
            needles,
            claim,
            expected,
            falsifying,
            intervention,
            parameters,
        ) in patterns:
            regex = re.compile("|".join(needles), re.IGNORECASE)
            matches = [record for record in logs if regex.search(record.text)]
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
                    intervention=intervention,
                    estimated_trials=3,
                    estimated_cost=1.2,
                    likely_files=sources,
                    likely_parameters=parameters,
                    safety_constraints=[
                        "Keep the safety watchdog active while the fix is trialled",
                        "Do not disable the limit that raised the failure",
                    ],
                )
            )
        return hypotheses

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
        return fallback, outcome or last, False

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
        prompt = self._build_prompt(incident, ev)
        response: Optional[ModelResponse] = None
        try:
            response = await self.model_gateway.generate(prompt=prompt, schema=Hypothesis)
            logger.info(f"Model gateway response provider: {response.provider}")
        except Exception as exc:
            logger.warning(f"Model gateway query failed: {exc}")
            return None

        if response is None:
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
            return None

        if response.structured_data and isinstance(response.structured_data, dict):
            data = dict(response.structured_data)
            # Real models emit natural-language statuses ("CONFIRMED", "PROVEN", ...)
            # that are not valid StatusLabel values - coerce instead of dropping
            # the model's entire causal analysis on one bad field.
            raw_status = str(data.get("status", "")).strip().upper()
            data["status"] = raw_status if raw_status in StatusLabel.__members__ else "INFERRED"
            try:
                data["confidence_prior"] = float(data.get("confidence_prior", 0.85))
            except (TypeError, ValueError):
                data["confidence_prior"] = 0.85

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
                "intervention", "Tune configuration to the pre-incident baseline parameters"
            )
            data.setdefault("confidence_prior", 0.85)
            try:
                return Hypothesis(**data)
            except Exception as val_err:
                logger.warning(
                    f"Could not construct Hypothesis from model structured data: {val_err}"
                )

        if response.content:
            first_line = response.content.strip().split("\n")[0][:250]
            return Hypothesis(
                hypothesis_id=f"hyp-{incident.id}-{response.provider}",
                causal_claim=first_line or f"AI-inferred root cause for {incident.title}",
                status=StatusLabel.INFERRED,
                supporting_artifact_ids=[],
                confidence_prior=0.85,
                expected_observation="Observed anomaly aligns with the model's reasoning",
                falsifying_observation=(
                    "Targeted counterfactual perturbation fails to restore baseline"
                ),
                intervention="Apply the model-recommended parameter correction",
            )
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

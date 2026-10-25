"""
The incident system model.

:class:`SystemModel` is the single source of truth that every downstream stage
(hypothesis generation, sandbox experiments, simulation, patch generation,
verification, reporting) reads from.  It is built entirely from the incident
bundle - there is no scenario-specific constant anywhere in this module.

The model contains:

* the **safety budget** the robot actually declares (freshness budget, control
  deadline, required rate), with evidence-derived fallbacks when the config
  omits them;
* the **measured latency series**, assembled from spans, logs, CSV metrics and
  MCAP detections;
* a **change-point analysis** that finds *when* the behaviour changed, and the
  **deployment correlation** that identifies which change coincided with it;
* the **configuration deltas** carried by deployments, classified by the role
  each parameter plays (batch window, queue depth, worker count, timeout, ...);
* a **calibrated latency model** (see :mod:`cauveris.analysis.model`) with its
  fit residuals, so downstream claims carry an honest confidence;
* the **robot kinematics** recovered from the recording (speed, acceleration,
  deceleration, path), used for ISO 3691-4 stopping-distance calculations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .evidence import (
    DeploymentEvent,
    EvidenceBundle,
    parse_timestamp,
)
from .model import (
    LatencyCalibration,
    SimulationOutcome,
    TwinParameters,
    calibrate_latency_model,
    simulate_pipeline,
)
from .statistics import (
    ChangePoint,
    Distribution,
    detect_change_point,
    distribution,
    linear_fit,
    percentile,
)

logger = logging.getLogger(__name__)

#: Minimum simulated horizon for a calibration, in seconds.  The bundle's own
#: observation window is often far shorter than this.
_MIN_CALIBRATION_HORIZON_S = 12.0
#: Number of control-loop periods the calibration horizon should span, so the
#: consumed-frame statistics rest on a few hundred samples.
_CALIBRATION_CONSUMER_SAMPLES = 150

__all__ = [
    "ParameterRole",
    "ConfigDelta",
    "SafetyBudget",
    "Kinematics",
    "SystemModel",
    "arrival_rate_evidence",
    "classify_parameter",
    "build_system_model",
    "get_system_model",
]


class ParameterRole:
    """
    Roles a configuration parameter can play.

    Roles are assigned from the *shape* of the parameter name, not from a
    hard-coded list of keys, so a different incident that names its batching
    window ``dynamic_batching.max_delay_ms`` is understood just as well.
    """

    BATCH_WINDOW = "batch_window"
    BATCH_SIZE = "batch_size"
    QUEUE_DEPTH = "queue_depth"
    WORKER_COUNT = "worker_count"
    TIMEOUT = "timeout"
    PERIOD = "period"
    THROUGHPUT = "throughput"
    MEMORY = "memory"
    RETRIES = "retries"
    CONCURRENCY = "concurrency"
    SAFETY_BUDGET = "safety_budget"
    CONTROL_RATE = "control_rate"
    OTHER = "other"

    ALL = (
        BATCH_WINDOW,
        BATCH_SIZE,
        QUEUE_DEPTH,
        WORKER_COUNT,
        TIMEOUT,
        PERIOD,
        THROUGHPUT,
        MEMORY,
        RETRIES,
        CONCURRENCY,
        SAFETY_BUDGET,
        CONTROL_RATE,
        OTHER,
    )


_ROLE_PATTERNS: List[Tuple[str, Tuple[str, ...]]] = [
    (ParameterRole.SAFETY_BUDGET, ("freshness_budget", "staleness_budget", "max_age", "max_staleness")),
    (ParameterRole.BATCH_WINDOW, ("batch_window", "batch_timeout", "batching_window", "max_delay", "batching_delay")),
    (ParameterRole.BATCH_SIZE, ("max_batch_size", "batch_size", "max_batch", "batch_limit")),
    (ParameterRole.QUEUE_DEPTH, ("queue_depth", "qos_depth", "depth", "queue_size", "buffer_size", "cache_size")),
    (ParameterRole.WORKER_COUNT, ("worker_count", "num_workers", "n_workers", "pool_size", "thread_count")),
    (ParameterRole.CONCURRENCY, ("max_concurrent", "concurrency", "parallel", "worker_threads")),
    (ParameterRole.CONTROL_RATE, ("frequency_hz", "_hz", "rate_hz", "control_hz", "publish_rate")),
    (ParameterRole.TIMEOUT, ("timeout", "deadline", "ttl", "expiry")),
    (ParameterRole.PERIOD, ("period_ms", "interval_ms", "interval", "period", "tick_ms", "cycle_ms")),
    (ParameterRole.THROUGHPUT, ("throughput", "fps", "rate", "bandwidth", "qps")),
    (ParameterRole.MEMORY, ("memory", "heap", "ram", "cache_mb", "max_size_mb", "max_size")),
    (ParameterRole.RETRIES, ("retries", "retry_count", "max_attempts", "backoff")),
]


def classify_parameter(key: str, value: Any = None) -> str:
    """
    Classify a configuration key into a :class:`ParameterRole`.

    The classification is name-based and works on any incident's vocabulary.
    The value is consulted for ambiguous names such as ``max_size``: a string
    value such as ``"512Mi"`` is a memory limit, while an integer is a count
    of frames or messages.
    """
    lowered = str(key or "").lower()
    for role, needles in _ROLE_PATTERNS:
        for needle in needles:
            if needle in lowered:
                # ``max_size`` is ambiguous: the value decides what it is.
                if needle == "max_size":
                    if isinstance(value, str):
                        return ParameterRole.MEMORY
                    if "batch" in lowered:
                        return ParameterRole.BATCH_SIZE
                    if "queue" in lowered or "buffer" in lowered:
                        return ParameterRole.QUEUE_DEPTH
                    return ParameterRole.OTHER
                return role
    return ParameterRole.OTHER


@dataclass
class ConfigDelta:
    """A configuration change detected between a baseline and the incident state."""

    key: str
    role: str
    old_value: Any
    new_value: Any
    source: str = "deployment"
    description: str = ""
    file: str = ""
    deployment_id: str = ""
    deployment_time: Optional[datetime] = None

    @property
    def numeric(self) -> Optional[Tuple[float, float]]:
        try:
            return float(self.old_value), float(self.new_value)
        except (TypeError, ValueError):
            return None

    @property
    def ratio(self) -> Optional[float]:
        pair = self.numeric
        if not pair or pair[0] == 0:
            return None
        return pair[1] / pair[0]

    @property
    def direction(self) -> str:
        pair = self.numeric
        if not pair:
            return "changed"
        if pair[1] > pair[0]:
            return "increased"
        if pair[1] < pair[0]:
            return "decreased"
        return "unchanged"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "role": self.role,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "direction": self.direction,
            "ratio": round(self.ratio, 4) if self.ratio is not None else None,
            "source": self.source,
            "description": self.description,
            "file": self.file,
            "deployment_id": self.deployment_id,
            "deployment_time": self.deployment_time.isoformat() if self.deployment_time else None,
        }


@dataclass
class SafetyBudget:
    """The safety limits the system declares."""

    freshness_budget_ms: float = 120.0
    control_deadline_ms: float = 100.0
    required_rate_hz: float = 10.0
    emergency_stop_on_stale: bool = True
    sources: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "freshness_budget_ms": self.freshness_budget_ms,
            "control_deadline_ms": self.control_deadline_ms,
            "required_rate_hz": self.required_rate_hz,
            "emergency_stop_on_stale": self.emergency_stop_on_stale,
            "sources": dict(self.sources),
        }


@dataclass
class Kinematics:
    """
    Robot motion parameters recovered from the recording.

    Used for the ISO 3691-4 stopping-distance calculation, which is what
    turns a latency measurement into a physical safety consequence.
    """

    max_speed_mps: float = 1.4
    nominal_speed_mps: float = 0.8
    acceleration_mps2: float = 0.8
    braking_deceleration_mps2: float = 3.0
    reaction_time_s: float = 0.2
    safety_margin_m: float = 0.1
    path: List[Dict[str, float]] = field(default_factory=list)
    sample_count: int = 0
    source: str = "declared-configuration"

    def stopping_distance(self, speed_mps: Optional[float] = None) -> float:
        """
        ISO 3691-4 style stopping distance.

        ``S = v * (t_reaction + t_delay) + v^2 / (2 * a) + margin``

        where ``t_delay`` is the perception staleness, which is added by the
        caller as the reaction delay introduced by stale data.
        """
        v = self.max_speed_mps if speed_mps is None else speed_mps
        a = max(1e-3, self.braking_deceleration_mps2)
        return (
            v * self.reaction_time_s
            + (v * v) / (2.0 * a)
            + self.safety_margin_m
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "max_speed_mps": self.max_speed_mps,
            "nominal_speed_mps": self.nominal_speed_mps,
            "acceleration_mps2": self.acceleration_mps2,
            "braking_deceleration_mps2": self.braking_deceleration_mps2,
            "reaction_time_s": self.reaction_time_s,
            "safety_margin_m": self.safety_margin_m,
            "path_points": len(self.path),
            "sample_count": self.sample_count,
            "source": self.source,
        }


@dataclass
class SystemModel:
    """Everything the analysis layer knows about one incident."""

    incident_id: str
    bundle_root: Optional[Path] = None
    manifest: Dict[str, Any] = field(default_factory=dict)

    # Evidence
    bundle: Optional[EvidenceBundle] = None
    timeline_events: List[Dict[str, Any]] = field(default_factory=list)

    # Safety
    budget: SafetyBudget = field(default_factory=SafetyBudget)
    config: Dict[str, Any] = field(default_factory=dict)
    config_sources: Dict[str, str] = field(default_factory=dict)
    #: Which configuration key declared each physical parameter.  A parameter
    #: that is absent from this mapping was *not* declared by the bundle: the
    #: model is using a default, and a default is not evidence.
    parameter_sources: Dict[str, str] = field(default_factory=dict)

    # Measurements
    latency_samples: List[Dict[str, Any]] = field(default_factory=list)
    latency_distribution: Distribution = field(default_factory=Distribution)
    baseline_distribution: Distribution = field(default_factory=Distribution)
    incident_distribution: Distribution = field(default_factory=Distribution)
    change_point: Optional[ChangePoint] = None
    change_point_time: Optional[datetime] = None
    change_point_evidence: List[str] = field(default_factory=list)

    # Network / queue / resources
    transport_distribution: Distribution = field(default_factory=Distribution)
    queue_depth_samples: List[float] = field(default_factory=list)
    queue_depth_series: List[Tuple[Optional[datetime], float]] = field(default_factory=list)
    resource_series: Dict[str, Distribution] = field(default_factory=dict)
    clock_skew_ms: float = 0.0

    # Configuration deltas
    config_deltas: List[ConfigDelta] = field(default_factory=list)
    deployments: List[DeploymentEvent] = field(default_factory=list)

    # Model
    base_parameters: TwinParameters = field(default_factory=TwinParameters)
    calibration: Optional[LatencyCalibration] = None
    kinematics: Kinematics = field(default_factory=Kinematics)

    # Derived observations
    anomaly_onset_correlated_deployment: Optional[DeploymentEvent] = None
    observation_window_s: float = 1.0
    simulation_horizon_s: float = 1.0
    notes: List[str] = field(default_factory=list)
    consistency_findings: List[Dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------ API

    @property
    def parameters(self) -> TwinParameters:
        """The calibrated parameters (falling back to the declared ones)."""
        if self.calibration is not None:
            return self.calibration.params
        return self.base_parameters

    def declares(self, parameter: str) -> bool:
        """
        Whether the bundle itself declared this parameter.

        A parameter the model has to default is not evidence: it is the
        modeller's assumption.  A hypothesis built on an assumption is a
        guess, so the hypothesis layer only fires on declared parameters and
        on measurements.
        """
        return parameter in self.parameter_sources

    def declares_budget(self) -> bool:
        """Whether the bundle declared the freshness budget itself."""
        return "freshness_budget_ms" in self.budget.sources

    def has_fitted_model(self) -> bool:
        """
        Whether the model was actually fitted to this incident's measurements.

        When the bundle holds no measurable latency the calibration falls back
        to the declared configuration; that is a set of assumptions, not a
        model of the incident, and nothing may be predicted from it.
        """
        return (
            self.calibration is not None
            and self.calibration.quality != "declared-configuration-only"
            and bool(self.calibration.fitted)
        )

    def predict(self, overrides: Dict[str, Any], *, seed: int = 4242) -> SimulationOutcome:
        """
        Predict the pipeline outcome under modified parameters.

        The simulation runs over the same horizon the calibration used, so a
        prediction is comparable with the fit and with every other
        counterfactual.  Using the bundle's (often sub-second) observation
        window here would produce statistics from a handful of frames.

        Args:
            overrides: Field values to override on the calibrated model.
            seed: RNG seed for reproducibility.
        """
        params = self.parameters
        merged = params.as_dict()
        merged.update({k: v for k, v in overrides.items() if v is not None})
        new_params = TwinParameters(**merged)
        horizon = max(self.observation_window_s, self.simulation_horizon_s)
        return simulate_pipeline(
            new_params,
            duration_s=horizon,
            warmup_s=horizon,
            seed=seed,
            freshness_budget_ms=self.budget.freshness_budget_ms,
            control_deadline_ms=self.budget.control_deadline_ms,
            age_basis="delivery",
        )

    def parameter_for_role(self, role: str) -> Optional[Tuple[str, Any]]:
        """Return the (key, value) of the first config entry with ``role``."""
        for key, value in self.config.items():
            if classify_parameter(key, value) == role:
                return key, value
        return None

    def delta_for_role(self, role: str) -> Optional[ConfigDelta]:
        for delta in self.config_deltas:
            if delta.role == role:
                return delta
        return None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "bundle_root": str(self.bundle_root) if self.bundle_root else None,
            "budget": self.budget.as_dict(),
            "latency": self.latency_distribution.as_dict(),
            "baseline_latency": self.baseline_distribution.as_dict(),
            "incident_latency": self.incident_distribution.as_dict(),
            "transport": self.transport_distribution.as_dict(),
            "change_point": self.change_point.as_dict() if self.change_point else None,
            "change_point_time": self.change_point_time.isoformat() if self.change_point_time else None,
            "config_deltas": [d.as_dict() for d in self.config_deltas],
            "calibration": self.calibration.as_dict() if self.calibration else None,
            "kinematics": self.kinematics.as_dict(),
            "clock_skew_ms": round(self.clock_skew_ms, 4),
            "queue_depth_samples": len(self.queue_depth_samples),
            "observation_window_s": round(self.observation_window_s, 4),
            "simulation_horizon_s": round(self.simulation_horizon_s, 4),
            "notes": list(self.notes),
            "consistency_findings": [dict(f) for f in self.consistency_findings],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LATENCY_PATTERNS = (
    re.compile(r"inference\s+(?:completed|took|duration|latency)[^\d]{0,20}(\d+(?:\.\d+)?)\s*ms", re.I),
    re.compile(r"latency[^\d]{0,20}(\d+(?:\.\d+)?)\s*ms", re.I),
    re.compile(r"age[^\d]{0,20}(\d+(?:\.\d+)?)\s*ms", re.I),
    re.compile(r"took\s+(\d+(?:\.\d+)?)\s*ms", re.I),
    re.compile(r"(\d+(?:\.\d+)?)\s*ms\s+latency", re.I),
)

_BATCH_PATTERN = re.compile(r"batch\s+(?:of|filled with|size)\s*(\d+)|filled with (\d+)\s+frames", re.I)
_QUEUE_PATTERN = re.compile(r"queue depth[^\d]{0,20}(\d+)|(\d+)\s+frames pending", re.I)


class PipelineStage:
    """
    The stage of the data path a latency observation belongs to.

    Observations from different stages are *different physical quantities*.
    A server's request latency (batch wait + compute) and the age of a
    detection when the control loop consumes it are not two samples of the
    same thing, and averaging them produces a number that corresponds to no
    point in the system.
    """

    SERVER_REQUEST = "server_request"
    """Server-side request latency: time from request to response (wait + compute)."""

    QUEUE_WAIT = "queue_wait"
    """Time a frame spent waiting for its batch to close."""

    SERVICE = "service"
    """Pure server compute time for a batch."""

    TRANSPORT = "transport"
    """Link latency between two hosts."""

    AGE = "age"
    """End-to-end age of the data at the moment it was consumed."""

    CONTROL_PERIOD = "control_period"
    """Duration of one control-loop iteration."""


#: Stages whose observations describe how long a request took end to end
#: inside the server's own boundary.
_SERVER_STAGES = frozenset(
    {PipelineStage.SERVER_REQUEST, PipelineStage.QUEUE_WAIT, PipelineStage.SERVICE}
)

#: Span names that denote the inference server's request boundary.
_REQUEST_SPAN_HINTS = ("inference", "predict", "request", "model")
#: Span names that denote the consumer's control loop.
_CONTROL_SPAN_HINTS = ("control", "loop", "cycle", "tick")


def _classify_span_stage(span) -> str:
    """
    Decide which stage of the data path a span measures.

    A control-loop span is *not* a latency measurement: its duration is the
    period at which the robot asks for a new detection.  Treating it as a
    latency is the mistake that produced a meaningless 102 ms mean age.
    """
    name = (span.name or "").lower()
    if any(hint in name for hint in _CONTROL_SPAN_HINTS):
        return PipelineStage.CONTROL_PERIOD
    if any(hint in name for hint in _REQUEST_SPAN_HINTS):
        return PipelineStage.SERVER_REQUEST
    return PipelineStage.SERVER_REQUEST


def _classify_text_latency(text: str) -> Optional[Tuple[float, str]]:
    """
    Extract a latency value from free text together with its stage.

    Returns ``(value_ms, stage)`` or None when the text carries no latency.
    """
    lowered = text.lower()
    for pattern in _LATENCY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except (TypeError, ValueError):
            continue
        # "stale detection age 155ms" is the age of the data, not a service
        # time; "inference completed in 155ms" is a server-side request.
        if "age" in lowered and "budget" not in lowered.split("age", 1)[1][:40]:
            stage = PipelineStage.AGE
        elif "inference" in lowered or "batch" in lowered:
            stage = PipelineStage.SERVER_REQUEST
        else:
            stage = PipelineStage.SERVER_REQUEST
        return value, stage
    return None


def _extract_latency_from_text(text: str) -> Optional[float]:
    for pattern in _LATENCY_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _extract_batch_size(text: str) -> Optional[int]:
    match = _BATCH_PATTERN.search(text)
    if not match:
        return None
    for group in match.groups():
        if group:
            try:
                return int(group)
            except ValueError:
                continue
    return None


def _extract_queue_depth(text: str) -> Optional[int]:
    match = _QUEUE_PATTERN.search(text)
    if not match:
        return None
    for group in match.groups():
        if group:
            try:
                return int(group)
            except ValueError:
                continue
    return None


def _numeric(value: Any) -> Optional[float]:
    try:
        if isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _find_config_value(config: Dict[str, Any], roles: Sequence[str]) -> Optional[Tuple[str, float]]:
    """Find the first config value whose key matches one of ``roles``."""
    for key, value in config.items():
        if classify_parameter(key, value) in roles:
            number = _numeric(value)
            if number is not None:
                return key, number
    return None


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_system_model(
    incident_id: str,
    bundle_root: Optional[Path] = None,
    *,
    bundle: Optional[EvidenceBundle] = None,
    timeline_events: Optional[List[Dict[str, Any]]] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> SystemModel:
    """
    Build a :class:`SystemModel` from an incident bundle.

    Args:
        incident_id: Identifier of the incident.
        bundle_root: Directory containing the bundle.  Optional when a
            pre-loaded ``bundle`` is supplied.
        bundle: An already-loaded evidence bundle.
        timeline_events: Normalised timeline events (from the timeline builder).
        manifest: The incident manifest.
    """
    if bundle is None:
        if bundle_root is None:
            raise ValueError("Either bundle_root or bundle must be supplied")
        bundle = EvidenceBundle.load(bundle_root)

    model = SystemModel(
        incident_id=incident_id,
        bundle_root=bundle_root or bundle.root,
        manifest=dict(manifest or bundle.manifest or {}),
        bundle=bundle,
        timeline_events=list(timeline_events or []),
    )

    model.config = dict(bundle.config)
    model.config_sources = dict(bundle.config_sources)
    model.deployments = list(bundle.deployments)

    _build_budget(model)
    _collect_latency_measurements(model)
    _collect_transport_and_queue(model)
    _collect_resources(model)
    _collect_clock_skew(model)
    _collect_config_deltas(model)
    _detect_change_point(model)
    _correlate_with_deployments(model)
    _build_kinematics(model)
    _build_base_parameters(model)
    _calibrate(model)
    _check_consistency(model)

    return model


#: Built system models, keyed by bundle and manifest revision.  Building a
#: model runs a global calibration, which is expensive; every stage that
#: needs one (the hypothesis layer, the digital twin, the verifier) reads
#: the same one.
_SYSTEM_MODEL_CACHE: Dict[Tuple[str, float], "SystemModel"] = {}
_SYSTEM_MODEL_CACHE_LIMIT = 8


def get_system_model(
    incident_id: str,
    bundle_root: Optional[Path] = None,
    *,
    timeline_events: Optional[List[Dict[str, Any]]] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> Optional["SystemModel"]:
    """
    Build the incident's system model, reusing a cached one when possible.

    Returns ``None`` when there is no bundle to analyse.
    """
    if bundle_root is None:
        return None
    root = Path(bundle_root)
    manifest_path = root / "manifest.yaml"
    try:
        key = (str(root.resolve()), manifest_path.stat().st_mtime if manifest_path.exists() else 0.0)
    except OSError:
        key = (str(root), 0.0)

    cached = _SYSTEM_MODEL_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        model = build_system_model(
            incident_id,
            root,
            timeline_events=list(timeline_events or []),
            manifest=dict(manifest or {}),
        )
    except Exception as exc:
        logger.warning(f"Could not build the system model for {root}: {exc}")
        return None

    if len(_SYSTEM_MODEL_CACHE) >= _SYSTEM_MODEL_CACHE_LIMIT:
        _SYSTEM_MODEL_CACHE.pop(next(iter(_SYSTEM_MODEL_CACHE)))
    _SYSTEM_MODEL_CACHE[key] = model
    return model


def _build_budget(model: SystemModel) -> None:
    """Derive the safety budget from configuration and evidence."""
    budget = SafetyBudget()
    config = model.config

    found = _find_config_value(config, (ParameterRole.SAFETY_BUDGET,))
    if found:
        budget.freshness_budget_ms = found[1]
        budget.sources["freshness_budget_ms"] = found[0]
    else:
        # Fall back to the budget the evidence itself cites.
        for record in model.bundle.logs:
            match = re.search(r"budget\s+(\d+(?:\.\d+)?)\s*ms", record.text, re.I)
            if match:
                budget.freshness_budget_ms = float(match.group(1))
                budget.sources["freshness_budget_ms"] = f"log:{record.source}"
                break
        for span in model.bundle.spans:
            if "freshness_budget_ms" in span.attributes:
                budget.freshness_budget_ms = float(span.attributes["freshness_budget_ms"])
                budget.sources["freshness_budget_ms"] = f"span:{span.name}"
                break

    deadline = _find_config_value(config, (ParameterRole.TIMEOUT,))
    if deadline and "control" in deadline[0].lower():
        budget.control_deadline_ms = deadline[1]
        budget.sources["control_deadline_ms"] = deadline[0]
    else:
        for key, value in config.items():
            if "control" in key.lower() and "deadline" in key.lower():
                number = _numeric(value)
                if number is not None:
                    budget.control_deadline_ms = number
                    budget.sources["control_deadline_ms"] = key
                    break
    if budget.control_deadline_ms > budget.freshness_budget_ms:
        # A deadline tighter than the freshness budget is unusual but legal;
        # keep the declared value and note it.
        model.notes.append(
            "Control deadline "
            f"({budget.control_deadline_ms:g}ms) exceeds the freshness budget "
            f"({budget.freshness_budget_ms:g}ms); both are enforced independently."
        )

    rate = _find_config_value(config, (ParameterRole.CONTROL_RATE,))
    if rate:
        budget.required_rate_hz = rate[1]
        budget.sources["required_rate_hz"] = rate[0]

    for key, value in config.items():
        if "emergency_stop" in key.lower() and "stale" in key.lower():
            budget.emergency_stop_on_stale = bool(value)
            budget.sources["emergency_stop_on_stale"] = key
            break

    model.budget = budget


def _collect_latency_measurements(model: SystemModel) -> None:
    """
    Gather every latency observation the bundle contains, tagged by stage.

    Every sample carries the pipeline stage it was measured at.  Pooling
    stages is what makes a latency distribution meaningless, so the stages
    are kept apart from the moment of collection.
    """
    samples: List[Dict[str, Any]] = []
    bundle = model.bundle

    def add(
        value: float,
        *,
        timestamp: Optional[datetime],
        source: str,
        kind: str,
        stage: str,
        series: str = "",
    ) -> None:
        if value is None or value <= 0:
            return
        samples.append(
            {
                "value": float(value),
                "timestamp": timestamp,
                "source": source,
                "kind": kind,
                "stage": stage,
                "series": series,
            }
        )

    # 1. OpenTelemetry spans: the duration is the request latency, and the
    #    attributes break it into its components.
    for span in bundle.spans:
        duration_ms = span.duration_ms
        stage = _classify_span_stage(span)
        if duration_ms > 0:
            add(
                duration_ms,
                timestamp=span.timestamp,
                source=f"trace:{span.name}",
                kind="span_duration",
                stage=stage,
                series="trace",
            )

        for attr, value in span.attributes.items():
            number = _numeric(value)
            if number is None or number <= 0:
                continue
            lowered = attr.lower()
            if "wait" in lowered:
                attr_stage = PipelineStage.QUEUE_WAIT
            elif "observed" in lowered or lowered in ("latency_ms", "age_ms"):
                # An *observed* latency reported by the consumer is the age of
                # the data at consumption - the end-to-end quantity.
                attr_stage = PipelineStage.AGE
            elif "window" in lowered or "budget" in lowered or "deadline" in lowered:
                # Configuration/deadline values, not observations of latency.
                continue
            elif "duration" in lowered:
                attr_stage = stage
            else:
                continue
            add(
                number,
                timestamp=span.timestamp,
                source=f"trace:{span.name}.{attr}",
                kind=attr,
                stage=attr_stage,
                series="trace",
            )

    # 2. CSV metric series carrying a latency column.
    for series_name, metric_samples in bundle.metrics.items():
        series_lower = series_name.lower()
        for metric in metric_samples:
            for key, value in metric.values.items():
                key_lower = key.lower()
                if "latency" not in key_lower and not key_lower.endswith("_latency_ms"):
                    continue
                if "network" in series_lower or key_lower in (
                    "latency_ms",
                    "rtt_ms",
                    "round_trip_ms",
                    "network_latency_ms",
                    "link_latency_ms",
                ):
                    metric_stage = PipelineStage.TRANSPORT
                elif "inference" in key_lower or "model" in key_lower:
                    metric_stage = PipelineStage.SERVER_REQUEST
                else:
                    metric_stage = PipelineStage.SERVER_REQUEST
                add(
                    value,
                    timestamp=metric.timestamp,
                    source=f"{series_name}:{key}",
                    kind="metric",
                    stage=metric_stage,
                    series=series_name,
                )

    # 3. Log lines that report a duration.
    for record in bundle.logs:
        extracted = _classify_text_latency(record.text)
        if extracted is None:
            continue
        value, text_stage = extracted
        add(
            value,
            timestamp=record.timestamp,
            source=f"log:{record.source}",
            kind="log",
            stage=text_stage,
            series="log",
        )

    # 4. MCAP detection messages carry the measured detection age.
    for message in bundle.recording_messages("detection", "perception", "bgr"):
        data = message.data
        for key in ("age_ms", "stale_age_ms", "detection_age_ms"):
            value = _numeric(data.get(key))
            if value is not None:
                add(
                    value,
                    timestamp=message.timestamp,
                    source=f"mcap:{message.topic}.{key}",
                    kind="detection_age",
                    stage=PipelineStage.AGE,
                    series="mcap",
                )

    # 5. Timeline events produced by the timeline builder.
    for event in model.timeline_events:
        attrs = event.get("attributes", {}) or {}
        for key, value in attrs.items():
            lowered = str(key).lower()
            if "observed_latency" in lowered:
                event_stage = PipelineStage.AGE
            elif "latency" in lowered or "duration_ms" in lowered:
                event_stage = PipelineStage.SERVER_REQUEST
            else:
                continue
            number = _numeric(value)
            if number is not None:
                add(
                    number,
                    timestamp=parse_timestamp(event.get("timestamp")),
                    source=f"timeline:{event.get('source', '')}",
                    kind="timeline",
                    stage=event_stage,
                    series="timeline",
                )

    samples.sort(key=lambda s: (s["timestamp"] is None, s["timestamp"]))
    model.latency_samples = samples

    # Counts per stage, for the notes and for the report.
    by_stage: Dict[str, int] = {}
    for sample in samples:
        by_stage[sample["stage"]] = by_stage.get(sample["stage"], 0) + 1
    model.notes.append(
        f"Collected {len(samples)} latency observations across "
        f"{len(by_stage)} pipeline stages: "
        + ", ".join(f"{stage}={count}" for stage, count in sorted(by_stage.items()))
        + "."
    )

    # The headline latency distribution is the end-to-end age when the bundle
    # reports one - that is the quantity the safety budget is written in.
    age_values = [s["value"] for s in samples if s["stage"] == PipelineStage.AGE]
    server_values = [
        s["value"] for s in samples if s["stage"] == PipelineStage.SERVER_REQUEST
    ]
    model.latency_distribution = distribution(age_values or server_values or [s["value"] for s in samples])

    # Measurement window from the evidence timestamps.
    stamps = [s["timestamp"] for s in samples if s["timestamp"]]
    if len(stamps) >= 2:
        span = (max(stamps) - min(stamps)).total_seconds()
        model.observation_window_s = max(0.25, span)
    elif len(stamps) == 1:
        model.observation_window_s = 1.0


def _collect_transport_and_queue(model: SystemModel) -> None:
    """Measure the transport link and the queue depth."""
    bundle = model.bundle

    # Prefer observations already classified as transport stage; that keeps the
    # link latency separate from the inference server's own latency.
    latencies: List[float] = [
        s["value"] for s in model.latency_samples if s["stage"] == PipelineStage.TRANSPORT
    ]

    # Fallback for bundles whose transport metrics are not classified yet.
    if not latencies:
        for series_name, metric_samples in bundle.metrics.items():
            series_lower = series_name.lower()
            for metric in metric_samples:
                value = metric.get(
                    "rtt_ms", "round_trip_ms", "network_latency_ms", "link_latency_ms"
                )
                if value is not None:
                    latencies.append(value)
                elif "network" in series_lower or "link" in series_lower:
                    value = metric.get("latency_ms")
                    if value is not None:
                        latencies.append(value)
    model.transport_distribution = distribution(latencies)

    depths: List[float] = []
    series: List[Tuple[Optional[datetime], float]] = []
    for series_name, metric_samples in bundle.metrics.items():
        for metric in metric_samples:
            value = metric.get("queue_depth", "depth", "pending", "backlog", "queue_size")
            if value is not None:
                depths.append(value)
                series.append((metric.timestamp, value))
    for record in bundle.logs:
        depth = _extract_queue_depth(record.text)
        if depth is not None:
            depths.append(float(depth))
            series.append((record.timestamp, float(depth)))
    model.queue_depth_samples = depths
    model.queue_depth_series = series


def _collect_resources(model: SystemModel) -> None:
    """Summarise the resource metric series (GPU/CPU/memory utilisation)."""
    bundle = model.bundle
    for series_name, metric_samples in bundle.metrics.items():
        keys: Dict[str, List[float]] = {}
        for metric in metric_samples:
            for key, value in metric.values.items():
                keys.setdefault(key, []).append(value)
        for key, values in keys.items():
            label = f"{series_name}:{key}"
            model.resource_series[label] = distribution(values)


#: Clock-offset statements as they appear in time-sync logs.  The unit is
#: part of the pattern because a bare number is ambiguous between milliseconds
#: and seconds.
_CLOCK_OFFSET_PATTERNS = (
    (re.compile(r"offset\s*([+-]?\d+(?:\.\d+)?)\s*ms", re.I), 1.0),
    (re.compile(r"offset\s*([+-]?\d+(?:\.\d+)?)\s*s\b", re.I), 1000.0),
    (re.compile(r"(?:clock|system)[^.\n]{0,40}?(?:wrong|off|skew|drift)[^.\n]{0,16}?([+-]?\d+(?:\.\d+)?)\s*ms", re.I), 1.0),
    (re.compile(r"drift[^.\n]{0,16}?([+-]?\d+(?:\.\d+)?)\s*ms", re.I), 1.0),
)


def _clock_skew_from_text(text: str) -> Optional[float]:
    """Recover an inter-host clock offset, in milliseconds, from a log line."""
    for pattern, scale in _CLOCK_OFFSET_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            return abs(float(match.group(1)) * scale)
        except (TypeError, ValueError):
            continue
    return None


def _collect_clock_skew(model: SystemModel) -> None:
    """
    Recover the measured inter-host clock skew.

    The manifest may carry an explicit alignment block; when it does not, the
    time-sync log does, and that is where the skew is actually recorded.
    """
    alignment = model.manifest.get("clock_alignment") or {}
    skew = 0.0
    if isinstance(alignment, dict):
        for value in alignment.values():
            number = _numeric(value)
            if number is not None:
                skew = max(skew, abs(number))
        domains = alignment.get("domains") or alignment.get("hosts")
        if isinstance(domains, list):
            for domain in domains:
                if isinstance(domain, dict):
                    for key, value in domain.items():
                        if isinstance(value, (int, float)) and "offset" in key.lower():
                            skew = max(skew, abs(float(value)))
                        if isinstance(value, (int, float)) and "drift" in key.lower():
                            skew = max(skew, abs(float(value)))
    model.clock_skew_ms = skew

    if model.clock_skew_ms <= 0.0:
        # No manifest alignment block: read the offset the time-sync daemon
        # reported.  A synced host states a small residual offset, and that
        # number is the one the model needs.
        for record in model.bundle.logs:
            recovered = _clock_skew_from_text(record.text)
            if recovered is not None:
                model.clock_skew_ms = recovered
                model.notes.append(
                    f"Recovered a clock offset of {recovered:.3f} ms from "
                    f"{record.source}."
                )
                break


def _collect_config_deltas(model: SystemModel) -> None:
    """Build the list of configuration changes, from deployments and from history."""
    deltas: List[ConfigDelta] = []
    seen: set = set()

    for deployment in model.deployments:
        for change in deployment.changes:
            key = change.key or ""
            if not key:
                continue
            role = classify_parameter(key, change.new_value)
            normalised = key.strip().lower()
            if normalised in seen:
                continue
            seen.add(normalised)
            deltas.append(
                ConfigDelta(
                    key=key,
                    role=role,
                    old_value=change.old_value,
                    new_value=change.new_value,
                    source="deployment",
                    description=change.description,
                    file=change.file,
                    deployment_id=deployment.deployment_id,
                    deployment_time=deployment.timestamp,
                )
            )

    model.config_deltas = deltas


def _detect_change_point(model: SystemModel) -> None:
    """
    Find the point in the evidence where the behaviour changed.

    A change point is only meaningful on a *coherent* time series - repeated
    samples of the same quantity, in order, from the same source.  Pooling the
    samples of a bundle across sources produces a series whose ordering
    reflects nothing but the order the files happened to be read, so this
    routine searches each metric series separately and uses the strongest
    candidate.
    """
    candidates: List[Tuple[str, List[Tuple[datetime, float]]]] = []

    for series_name, metric_samples in (model.bundle.metrics if model.bundle else {}).items():
        for key in ("queue_depth", "depth", "pending", "backlog", "queue_size"):
            points = [
                (m.timestamp, m.get(key))
                for m in metric_samples
                if m.timestamp is not None and m.get(key) is not None
            ]
            if len(points) >= 6:
                candidates.append((f"{series_name}:{key}", points))
                break

    for series_name, metric_samples in (model.bundle.metrics if model.bundle else {}).items():
        for key in ("inference_latency_ms", "latency_ms", "observed_latency_ms"):
            points = [
                (m.timestamp, m.get(key))
                for m in metric_samples
                if m.timestamp is not None and m.get(key) is not None
            ]
            if len(points) >= 6:
                candidates.append((f"{series_name}:{key}", points))
                break

    if not candidates:
        model.notes.append(
            "No metric series in the bundle has enough time-ordered samples "
            "(6 or more) to locate a change point statistically; the onset is "
            "taken from the incident's own timestamps instead."
        )
        model.change_point_evidence = [s["source"] for s in model.latency_samples[:5]]
        return

    best: Optional[Tuple[str, Any, List[Tuple[datetime, float]]]] = None
    for label, points in candidates:
        points.sort(key=lambda item: item[0])
        values = [v for _, v in points]
        change_point = detect_change_point(values)
        if change_point is None:
            continue
        if best is None or abs(change_point.t_statistic) > abs(best[1].t_statistic):
            best = (label, change_point, points)

    if best is None:
        model.notes.append(
            "A time-ordered metric series was found but no convincing change "
            "point was detected in it; the onset is taken from the incident's "
            "own timestamps instead."
        )
        return

    label, change_point, points = best
    model.change_point = change_point
    index = change_point.index
    if 0 < index < len(points):
        model.change_point_time = points[index][0]
    model.baseline_distribution = change_point.before
    model.incident_distribution = change_point.after
    model.change_point_evidence = [label]
    model.notes.append(
        f"Change point detected in '{label}' at sample {index} "
        f"(Welch t={change_point.t_statistic:.2f}, p={change_point.p_value:.3g}, "
        f"Cohen's d={change_point.effect_size:.2f}); "
        f"mean rose from {change_point.before.mean:.2f} to {change_point.after.mean:.2f}."
    )


def _correlate_with_deployments(model: SystemModel) -> None:
    """Link the anomaly onset to the deployment that preceded it."""
    if not model.deployments:
        return

    onset = _incident_onset_time(model)
    if onset is None:
        model.notes.append(
            "No onset time could be established from the evidence, so no "
            "deployment could be correlated with the incident."
        )
        return

    preceding = [
        d
        for d in model.deployments
        if d.timestamp is not None and d.timestamp <= onset
    ]
    following = [
        d
        for d in model.deployments
        if d.timestamp is not None and d.timestamp > onset
    ]

    if preceding:
        suspect = preceding[-1]
        model.anomaly_onset_correlated_deployment = suspect
        if suspect.timestamp is not None:
            delta = (onset - suspect.timestamp).total_seconds()
            model.notes.append(
                f"Deployment {suspect.deployment_id} preceded the anomaly onset by "
                f"{delta:.1f}s ({delta / 60.0:.1f} min); it is the most recent "
                "rollout before the incident and is the prime suspect."
            )
            # A rollout that is very old is a weaker suspect than one that landed
            # shortly before the onset; say so rather than implying equal weight.
            if delta > 24 * 3600:
                model.notes.append(
                f"Deployment {suspect.deployment_id} landed more than a day before "
                "the onset, so a causal link is possible but not strong."
            )
    else:
        # The onset precedes every known deployment: the cause is not a rollout.
        model.notes.append(
            "Anomaly onset precedes every recorded deployment; no rollout is implicated."
        )

    if following:
        model.notes.append(
            "Deployment(s) "
            + ", ".join(d.deployment_id for d in following)
            + " landed after the onset and cannot explain it."
        )


def _incident_onset_time(model: SystemModel) -> Optional[datetime]:
    """
    The best available timestamp for when the incident was observed.

    Preference order: a statistically detected change point, the manifest's
    declared incident time, then the earliest evidence timestamp.  Deployment
    timestamps are deliberately *not* used here - the onset must come from
    evidence, and the deployment is the thing being correlated against it.
    """
    if model.change_point_time is not None:
        return model.change_point_time

    for key in ("approximate_time", "incident_time", "started_at", "occurred_at", "timestamp"):
        raw = model.manifest.get(key)
        if not raw:
            continue
        parsed = parse_timestamp(raw)
        if parsed is not None:
            return parsed

    stamps = [s["timestamp"] for s in model.latency_samples if s["timestamp"]]
    if stamps:
        return min(stamps)
    return None


def _build_kinematics(model: SystemModel) -> None:
    """Recover robot motion parameters from configuration and the recording."""
    kin = Kinematics()
    config = model.config

    for key, value in config.items():
        lowered = key.lower()
        number = _numeric(value)
        if number is None:
            continue
        if "max_speed" in lowered or "linear_max" in lowered:
            kin.max_speed_mps = number
            kin.source = "declared-configuration"
        elif lowered.endswith("max_vel") or lowered.endswith("max_velocity"):
            kin.max_speed_mps = max(kin.max_speed_mps, number)
        elif "accel" in lowered:
            kin.acceleration_mps2 = number
        elif "decel" in lowered or "braking" in lowered:
            kin.braking_deceleration_mps2 = number

    # The recording is the authoritative source for what the robot actually did.
    poses: List[Dict[str, float]] = []
    speeds: List[float] = []
    for message in model.bundle.recording_messages():
        data = message.data
        translation = data.get("translation")
        if isinstance(translation, dict):
            x = _numeric(translation.get("x"))
            y = _numeric(translation.get("y"))
            if x is not None and y is not None:
                poses.append({"x": x, "y": y, "t": message.log_time_ns / 1e9})
        linear = data.get("linear")
        if isinstance(linear, dict):
            vx = _numeric(linear.get("x"))
            if vx is not None:
                speeds.append(abs(vx))

    if poses:
        kin.path = poses
        kin.sample_count = len(poses)
        kin.source = "recorded-poses"
    if speeds:
        observed_max = max(speeds)
        if observed_max > 0:
            kin.nominal_speed_mps = observed_max
            kin.max_speed_mps = max(kin.max_speed_mps, observed_max)

    model.kinematics = kin


def _build_base_parameters(model: SystemModel) -> None:
    """Seed the physical model with the incident's declared configuration."""
    params = TwinParameters()
    config = model.config

    window = _find_config_value(config, (ParameterRole.BATCH_WINDOW,))
    if window:
        params.batching_window_ms = window[1]
        model.parameter_sources["batching_window_ms"] = window[0]
    else:
        # Fall back to the window the trace attributes report.
        for span in model.bundle.spans:
            for key, value in span.attributes.items():
                if "window" in key.lower():
                    number = _numeric(value)
                    if number is not None:
                        params.batching_window_ms = number
                        model.parameter_sources["batching_window_ms"] = f"span:{span.name}.{key}"
                        break

    batch_size = _find_config_value(config, (ParameterRole.BATCH_SIZE,))
    if batch_size:
        params.max_batch_size = int(batch_size[1])
        model.parameter_sources["max_batch_size"] = batch_size[0]

    depth = _find_config_value(config, (ParameterRole.QUEUE_DEPTH,))
    if depth:
        params.qos_queue_depth = int(depth[1])
        model.parameter_sources["qos_queue_depth"] = depth[0]

    workers = _find_config_value(config, (ParameterRole.WORKER_COUNT, ParameterRole.CONCURRENCY))
    if workers:
        params.server_workers = max(1, int(workers[1]))
        model.parameter_sources["server_workers"] = workers[0]

    params.consumer_rate_hz = model.budget.required_rate_hz
    if "required_rate_hz" in model.budget.sources:
        model.parameter_sources["consumer_rate_hz"] = model.budget.sources["required_rate_hz"]

    if model.transport_distribution.count:
        params.transport_mean_ms = model.transport_distribution.p50
        params.transport_sigma_ms = model.transport_distribution.stdev or max(
            0.5, model.transport_distribution.p50 * 0.1
        )
        model.parameter_sources["transport_mean_ms"] = "measured"

    if model.queue_depth_samples:
        params.initial_backlog_frames = model.queue_depth_samples[0]

    params.clock_skew_ms = model.clock_skew_ms

    model.base_parameters = params


def _arrival_rate_evidence(model: SystemModel) -> Dict[str, Any]:
    """
    Estimate the frame arrival rate from two independent kinds of evidence.

    * The **batch size** says how many frames a batching epoch collected.  If
      the batch closed on the timer, that count is one window's worth of
      arrivals; if it filled up first, the server drained at least
      ``max_batch_size`` frames per window.
    * The **backlog growth** says how fast frames are piling up, which is a
      lower bound on the arrival rate.

    Both are estimates of the same physical quantity, so they can be compared
    with each other - and when they disagree, the disagreement is a property
    of the evidence, not of the model.
    """
    params = model.base_parameters
    window_s = params.batching_window_ms / 1000.0
    max_batch = params.max_batch_size

    observed_batch: Optional[float] = None
    for record in model.bundle.logs:
        size = _extract_batch_size(record.text)
        if size:
            observed_batch = float(size)
            break
    if observed_batch is None and model.calibration is not None:
        candidate = model.calibration.targets.get("mean_batch_size")
        observed_batch = float(candidate) if candidate else None

    from_batch: Optional[float] = None
    regime: Optional[str] = None
    if observed_batch and window_s > 0:
        if observed_batch < max_batch - 1e-9:
            regime = "window-limited"
            from_batch = observed_batch / window_s
        else:
            regime = "size-limited"
            from_batch = max_batch / window_s

    from_backlog: Optional[float] = None
    growth: Optional[float] = None
    timed = [(t, v) for t, v in model.queue_depth_series if t is not None]
    if len(timed) >= 3:
        timed.sort(key=lambda item: item[0])
        base_t = timed[0][0]
        xs = [(t - base_t).total_seconds() for t, _ in timed]
        ys = [v for _, v in timed]
        fit = linear_fit(xs, ys)
        if fit is not None:
            _, slope, _r2 = fit
            growth = slope
            from_backlog = max(0.0, slope)

    return {
        "observed_batch": observed_batch,
        "from_batch": from_batch,
        "regime": regime,
        "from_backlog": from_backlog,
        "backlog_growth": growth,
        "max_batch": max_batch,
        "window_ms": params.batching_window_ms,
    }


def arrival_rate_evidence(model: SystemModel) -> Dict[str, Any]:
    """
    Public view of the two independent arrival-rate estimates.

    The hypothesis layer needs this to say *why* it believes the server was
    (or was not) overloaded, so it is exposed rather than kept private.
    """
    return _arrival_rate_evidence(model)


def _evidence_contradiction(evidence: Dict[str, Any]) -> Optional[float]:
    """
    The factor by which the two arrival-rate estimates disagree.

    Returns None when there is only one estimate, or when they broadly agree.
    """
    from_batch = evidence.get("from_batch")
    from_backlog = evidence.get("from_backlog")
    if not from_batch or not from_backlog or from_backlog <= 1.0:
        return None
    ratio = from_backlog / from_batch
    if ratio >= 2.0:
        return ratio
    if ratio <= 0.5:
        return ratio
    return None


def _calibration_targets(model: SystemModel) -> Dict[str, Optional[float]]:
    """
    Assemble the measured quantities the latency model is fitted to.

    Each target is taken from the stage of the pipeline it actually measures.
    The end-to-end age, the server-side request latency and the transport
    delay are three different quantities; fitting one model to their pooled
    average produces a model that reproduces none of them.
    """
    bundle = model.bundle
    targets: Dict[str, Optional[float]] = {}

    def values_for(stage: str) -> List[float]:
        return [s["value"] for s in model.latency_samples if s["stage"] == stage]

    age_values = values_for(PipelineStage.AGE)
    server_values = values_for(PipelineStage.SERVER_REQUEST)
    wait_values = values_for(PipelineStage.QUEUE_WAIT)
    transport_values = values_for(PipelineStage.TRANSPORT)

    mean_transport = (
        model.transport_distribution.p50 if model.transport_distribution.count else None
    )

    # --- end-to-end age ---------------------------------------------------
    if age_values:
        targets["mean_age_ms"] = sum(age_values) / len(age_values)
        # A percentile taken from a handful of observations is not a
        # distributional statement, so it is only used as a target when there
        # are enough of them to mean something.
        if len(age_values) >= 5:
            targets["p95_age_ms"] = percentile(age_values, 95)
    elif server_values:
        # No explicit age measurement: rebuild it from the physical path.
        # age = server-side request + return transport + subscriber delay.
        derived = sum(server_values) / len(server_values) + (mean_transport or 0.0)
        targets["mean_age_ms"] = derived
        targets["p95_age_ms"] = percentile(server_values, 95) + (mean_transport or 0.0)
        model.notes.append(
            "The bundle records no explicit detection age; the end-to-end age "
            "target was reconstructed as the server-side request latency plus "
            "the measured transport latency."
        )

    # --- server-side request latency ---------------------------------------
    # The trace span is the authoritative measurement: it is the server's own
    # request boundary and carries the wait/service decomposition that ties the
    # model to the mechanism.  A ramping CSV series measures the same quantity
    # over the observation window but is a weaker statement of the incident
    # state, so it is used only when no trace exists.
    trace_requests = [
        s["value"]
        for s in model.latency_samples
        if s["stage"] == PipelineStage.SERVER_REQUEST and s.get("series") == "trace"
    ]
    if trace_requests:
        targets["mean_request_latency_ms"] = sum(trace_requests) / len(trace_requests)
    elif server_values:
        targets["mean_request_latency_ms"] = sum(server_values) / len(server_values)

    # --- batch wait --------------------------------------------------------
    if wait_values:
        targets["mean_epoch_wait_ms"] = sum(wait_values) / len(wait_values)

    # --- service time ------------------------------------------------------
    # service = request latency - queue wait
    request_target = targets.get("mean_request_latency_ms")
    wait_target = targets.get("mean_epoch_wait_ms")
    if request_target is not None and wait_target is not None:
        derived_service = request_target - wait_target
        if derived_service > 0:
            targets["mean_service_ms"] = derived_service
    else:
        service_values = values_for(PipelineStage.SERVICE)
        if service_values:
            targets["mean_service_ms"] = sum(service_values) / len(service_values)

    # --- batch size --------------------------------------------------------
    batch_sizes: List[float] = []
    for record in bundle.logs:
        size = _extract_batch_size(record.text)
        if size:
            batch_sizes.append(float(size))
    for span in bundle.spans:
        for key, value in span.attributes.items():
            lowered = key.lower()
            if "batch" in lowered and ("size" in lowered or "count" in lowered):
                number = _numeric(value)
                if number is not None:
                    batch_sizes.append(number)
    for message in bundle.recording_messages("detection", "perception"):
        count = _numeric(message.data.get("detection_count"))
        if count:
            batch_sizes.append(count)
    if batch_sizes:
        targets["mean_batch_size"] = sum(batch_sizes) / len(batch_sizes)

    # --- transport ---------------------------------------------------------
    if mean_transport is not None:
        targets["mean_transport_ms"] = mean_transport
    elif transport_values:
        targets["mean_transport_ms"] = sum(transport_values) / len(transport_values)

    # --- backlog -----------------------------------------------------------
    # The queue-depth metric is a server-side counter whose relationship to
    # the model's pending-frame depth is an assumption.  When it contradicts
    # the batch evidence - which gives an independent estimate of the arrival
    # rate - fitting to both would mean fitting to two incompatible numbers.
    # The contradiction is reported instead; the backlog is not a target.
    contradiction = _evidence_contradiction(_arrival_rate_evidence(model))
    if contradiction is not None and contradiction >= 2.0:
        model.notes.append(
            "The queue-depth series was excluded from the calibration targets: it "
            f"implies an arrival rate {contradiction:.1f}x the one implied by the "
            "observed batch size, so the two observations cannot both be fitted at "
            "once. The disagreement is recorded as a consistency finding."
        )
    elif model.queue_depth_samples:
        targets["mean_backlog"] = sum(model.queue_depth_samples) / len(model.queue_depth_samples)

    return targets


def _add_finding(
    model: SystemModel,
    finding_id: str,
    severity: str,
    title: str,
    detail: str,
    *,
    evidence: Optional[Sequence[str]] = None,
    implication: str = "",
) -> None:
    """Record a contradiction or caveat found in the evidence."""
    model.consistency_findings.append(
        {
            "id": finding_id,
            "severity": severity,
            "title": title,
            "detail": detail,
            "evidence": list(evidence or []),
            "implication": implication,
        }
    )


def _check_consistency(model: SystemModel) -> None:
    """
    Cross-check the evidence against itself.

    An incident bundle is a record of what different observers saw.  When two
    observers disagree - the server says it batched four frames while the
    queue counter says frames were arriving at seventy a second - one of them
    is wrong, and a model fitted to both will explain neither.  These
    contradictions are reported rather than averaged away.
    """
    params = model.parameters
    max_batch = params.max_batch_size

    evidence = _arrival_rate_evidence(model)
    observed_batch = evidence.get("observed_batch")
    implied_from_batch = evidence.get("from_batch")
    batch_regime = evidence.get("regime")
    implied_from_backlog = evidence.get("from_backlog")

    # --- do the two agree? -------------------------------------------------
    if implied_from_batch and implied_from_backlog and implied_from_backlog > 1.0:
        ratio = implied_from_backlog / implied_from_batch
        if ratio >= 2.0:
            _add_finding(
                model,
                "arrival-rate-disagreement",
                "critical",
                "Batch size and backlog growth imply incompatible arrival rates",
                f"The observed batch of {observed_batch:.0f} frame(s) in a "
                f"{params.batching_window_ms:.0f} ms window implies an arrival rate of "
                f"about {implied_from_batch:.1f} Hz in a {batch_regime} regime. "
                f"The queue depth, however, grows at {implied_from_backlog:.1f} frames/s, "
                f"which requires at least {implied_from_backlog:.1f} Hz of arrivals "
                f"({ratio:.1f}x higher). With a declared maximum batch of {max_batch}, "
                f"an arrival rate of {implied_from_backlog:.1f} Hz would fill a batch in "
                f"{max_batch / implied_from_backlog * 1000.0:.0f} ms, i.e. the epoch would "
                f"be size-limited and the batch would contain {max_batch} frames, not "
                f"{observed_batch:.0f}.",
                evidence=[
                    f"log batch size = {observed_batch:.0f}",
                    f"batching_window_ms = {params.batching_window_ms:.0f}",
                    f"max_batch_size = {max_batch}",
                    f"queue depth slope = {implied_from_backlog:.1f} frames/s",
                ],
                implication=(
                    "The two observations cannot both be exact. The latency model is fitted "
                    "against the batch evidence, so its counterfactuals describe the "
                    f"{batch_regime} regime; conclusions that depend on the arrival rate "
                    "carry this caveat."
                ),
            )
        elif ratio <= 0.5:
            _add_finding(
                model,
                "arrival-rate-disagreement",
                "warning",
                "Backlog growth is slower than the batch size implies",
                f"The observed batch of {observed_batch:.0f} frame(s) implies about "
                f"{implied_from_batch:.1f} Hz, but the queue depth only grows at "
                f"{implied_from_backlog:.1f} frames/s.",
                implication="The arrival rate is the least certain fitted parameter.",
            )

    # --- the recorded age vs the physical path -----------------------------
    age_target = model.calibration.targets.get("mean_age_ms") if model.calibration else None
    request_target = (
        model.calibration.targets.get("mean_request_latency_ms") if model.calibration else None
    )
    transport_target = (
        model.calibration.targets.get("mean_transport_ms") if model.calibration else None
    )
    if age_target and request_target and transport_target:
        floor = request_target + transport_target
        if age_target < floor - 0.5:
            _add_finding(
                model,
                "age-shorter-than-path",
                "warning",
                "Recorded detection age is shorter than the measured physical path",
                f"The end-to-end age is recorded as {age_target:.1f} ms, but the "
                f"server-side request took {request_target:.1f} ms and the link "
                f"latency was {transport_target:.1f} ms, so a detection cannot reach "
                f"the consumer in less than {floor:.1f} ms.",
                implication=(
                    "The reported age is measured at the server boundary rather than at "
                    "the consumer; the model treats it as the end-to-end quantity and "
                    "the residual on it is reported with the fit."
                ),
            )

    # --- declared configuration vs fitted parameters -----------------------
    declared_pairs = [
        ("consumer_rate_hz", params.consumer_rate_hz, model.budget.required_rate_hz),
        ("qos_queue_depth", params.qos_queue_depth, None),
    ]
    for name, value, declared in declared_pairs:
        if declared and abs(value - declared) > 1e-6:
            _add_finding(
                model,
                f"declared-vs-fitted-{name}",
                "critical",
                f"Fitted {name} contradicts the declared configuration",
                f"The model uses {name}={value:g}, but the incident declares {declared:g}.",
                implication=(
                    "A counterfactual that moves this parameter is describing a system "
                    "the operator never ran."
                ),
            )

    # --- clock skew against the effects it could explain -------------------
    if model.clock_skew_ms > 0 and model.latency_distribution.count:
        observed_spread = model.latency_distribution.maximum - model.latency_distribution.minimum
        if model.clock_skew_ms > 0.2 * max(observed_spread, 1.0):
            _add_finding(
                model,
                "clock-skew-material",
                "info",
                "Clock skew is large relative to the observed latency spread",
                f"The recovered clock skew is {model.clock_skew_ms:.2f} ms against a "
                f"latency spread of {observed_spread:.2f} ms.",
                implication=(
                    "Cross-host timestamps must be corrected before they are used to "
                    "order events; the model adds the skew to the measured age."
                ),
            )

    # --- budget ------------------------------------------------------------
    if age_target and model.budget.freshness_budget_ms:
        budget = model.budget.freshness_budget_ms
        if age_target > budget:
            _add_finding(
                model,
                "budget-exceeded",
                "info",
                "The measured latency exceeds the declared safety budget",
                f"The end-to-end age of {age_target:.1f} ms exceeds the freshness "
                f"budget of {budget:.1f} ms by {age_target - budget:.1f} ms "
                f"({(age_target / budget - 1.0) * 100:.0f}% over).",
                implication=(
                    "This is the condition the incident's safety stop was configured to "
                    "detect; the model's stale_rate reproduces it."
                ),
            )

    if model.consistency_findings:
        model.notes.append(
            f"Recorded {len(model.consistency_findings)} consistency finding(s) in the "
            "evidence; see 'consistency_findings' for details."
        )


def _calibrate(model: SystemModel) -> None:
    """Fit the latency model to the incident's own measurements."""
    targets = _calibration_targets(model)
    if not targets:
        model.calibration = LatencyCalibration(
            params=model.base_parameters,
            score=float("nan"),
            targets=targets,
            residuals={},
            fitted={},
            quality="no-measurable-latency-evidence",
            notes=["The bundle contains no latency measurements to fit against."],
        )
        return

    # The observation window in the bundle is often only a fraction of a
    # second - a handful of samples captured around the moment of failure.
    # Fitting a model on that window produces statistics from a handful of
    # consumed frames, which is indistinguishable from noise.  The system was
    # observed *in a state*; the model is therefore calibrated over a horizon
    # long enough to characterise that state (at least a few hundred control
    # periods), while the observation window is reported separately.
    consumer_hz = (
        model.budget.required_rate_hz
        or model.base_parameters.consumer_rate_hz
        or 10.0
    )
    horizon_s = max(
        _MIN_CALIBRATION_HORIZON_S,
        _CALIBRATION_CONSUMER_SAMPLES / max(0.1, consumer_hz),
    )
    duration_s = max(model.observation_window_s, horizon_s)
    model.simulation_horizon_s = duration_s

    # Derive which simulation-side age quantity the measured age refers to,
    # from the provenance of the age samples themselves:
    #   * MCAP detection ages are stamped by the subscriber on message receipt
    #     -> delivery-side.
    #   * Trace/timeline "observed_latency" values are reported by the consumer
    #     at consumption, which includes the control loop's sampling delay
    #     -> actuation-side (the safety budget's basis).
    #   * No explicit age samples -> the target was reconstructed from the
    #     server-side request latency plus transport, i.e. arrival at the
    #     subscriber -> delivery-side.
    age_samples = [s for s in model.latency_samples if s["stage"] == PipelineStage.AGE]
    series_counts: Dict[str, int] = {}
    for sample in age_samples:
        key = str(sample.get("series") or "unknown")
        series_counts[key] = series_counts.get(key, 0) + 1
    if not age_samples:
        age_basis = "delivery"
    elif series_counts.get("mcap", 0) and not (
        series_counts.get("trace", 0) or series_counts.get("timeline", 0)
    ):
        age_basis = "delivery"
    else:
        age_basis = "actuation"

    calibration = calibrate_latency_model(
        model.base_parameters,
        targets,
        duration_s=duration_s,
        freshness_budget_ms=model.budget.freshness_budget_ms,
        control_deadline_ms=model.budget.control_deadline_ms,
        age_basis=age_basis,
    )
    model.calibration = calibration
    model.notes.append(
        f"Measured detection age was calibrated against the model's '{age_basis}'-side "
        "age (subscriber delivery vs. control-loop consumption), derived from the "
        "provenance of the age samples."
    )
    model.notes.append(
        f"The latency model was calibrated over a {duration_s:.1f}s horizon "
        f"(the bundle's observation window is {model.observation_window_s:.3f}s), so that "
        "the fitted statistics rest on enough consumed frames to be meaningful."
    )
    if calibration.quality in ("partial", "poor"):
        model.notes.append(
            f"Latency model fit quality is '{calibration.quality}'. Residuals are reported "
            "with the model; predictions that depend on it carry reduced confidence."
        )

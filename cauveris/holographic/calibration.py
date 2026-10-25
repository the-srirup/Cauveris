"""
Evidence calibration for the holographic measurement system.

A holographic inversion needs its observations on a common scale: "how
loaded is this component right now", expressed as a fraction of the capacity
that actually matters.  A raw CSV cell is not that number.  ``gpu_utilization
= 90`` is 90 percent of a full GPU; ``inference_latency_ms = 190`` is
unremarkable for a batch job and a hard failure for the 120 ms perception
freshness budget the robot itself declares.

The reference scales come from the incident's own declarations wherever the
bundle states them:

* ``config/robot_params.yaml`` - detection freshness budget, control loop
  deadline, transform timeout, required detection frequency.
* ``config/inference.yaml`` - dynamic batching window, batch size, request
  timeout.
* the metric export itself - ``memory_total_mb`` is the capacity that
  ``memory_used_mb`` is a fraction of.

Only metrics the bundle says nothing about fall back to documented physical
defaults, and every scale records where it came from so a reconstruction can
be audited instead of trusted.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metric classification
# ---------------------------------------------------------------------------

# Scale families.
PERCENT = "percent"  # 0..100
MILLISECOND = "millisecond"
COUNT = "count"
RATIO = "ratio"  # 0..1
MEGABYTE = "megabyte"

# Limit kinds - which declared quantity acts as the "budget" for the metric.
PERCENT_FULL = "percent_full"  # a ratio: 100% is saturation
RATIO_FULL = "ratio_full"  # a 0..1 ratio: 1.0 is saturation
FRESHNESS_BUDGET = "freshness_budget"  # robot_params.safety.detection_freshness_budget_ms
CONTROL_DEADLINE = "control_deadline"  # robot_params.safety.control_loop_deadline_ms
QUEUE_DRAIN = "queue_drain"  # arrival rate x request timeout (frames)
CPU_CORES = "cpu_cores"  # load average per core
PACKET_LOSS = "packet_loss_limit"  # control-plane links fail well below 100%
LEARNED_CAPACITY = "learned_capacity"  # a capacity exported by the same metric stream


@dataclass(frozen=True)
class MetricSpec:
    """How one metric family constrains a state dimension, and how it scales."""

    dimension: str
    scale: str
    limit: str
    saturation_multiplier: float = 2.0
    description: str = ""


# Ordered most-specific-first: "gpu_utilization" must not be captured by the
# generic utilization rule, and "memory_utilization" must not be captured by
# the GPU rule.
_METRIC_RULES: Tuple[Tuple[str, MetricSpec], ...] = (
    (
        "cpu_util",
        MetricSpec(
            "cpu_pressure",
            PERCENT,
            PERCENT_FULL,
            1.0,
            "CPU utilisation - a ratio, 100% is saturation",
        ),
    ),
    (
        "cpu_usage",
        MetricSpec(
            "cpu_pressure",
            RATIO,
            RATIO_FULL,
            1.0,
            "CPU usage - a 0..1 ratio, 1.0 is saturation",
        ),
    ),
    (
        "load_avg",
        MetricSpec(
            "cpu_pressure",
            COUNT,
            CPU_CORES,
            2.0,
            "Load average - saturates at two runnable tasks per core",
        ),
    ),
    (
        "memory_util",
        MetricSpec(
            "memory_pressure",
            PERCENT,
            PERCENT_FULL,
            1.0,
            "Memory utilisation - a ratio, 100% is saturation",
        ),
    ),
    (
        "memory_used",
        MetricSpec(
            "memory_pressure",
            MEGABYTE,
            LEARNED_CAPACITY,
            1.0,
            "Resident memory - a fraction of the exported memory capacity",
        ),
    ),
    (
        "swap_used",
        MetricSpec(
            "memory_pressure",
            MEGABYTE,
            LEARNED_CAPACITY,
            1.0,
            "Swap in use - a fraction of the exported memory capacity",
        ),
    ),
    (
        "memory_total",
        MetricSpec(
            "memory_pressure",
            MEGABYTE,
            LEARNED_CAPACITY,
            1.0,
            "Memory capacity - establishes the scale for memory_used_mb",
        ),
    ),
    (
        "gpu_util",
        MetricSpec(
            "resource_contention",
            PERCENT,
            PERCENT_FULL,
            1.0,
            "GPU utilisation - contention on the accelerator",
        ),
    ),
    (
        "gpu_memory",
        MetricSpec(
            "memory_pressure",
            PERCENT,
            PERCENT_FULL,
            1.0,
            "GPU memory utilisation",
        ),
    ),
    (
        "queue_depth",
        MetricSpec(
            "resource_contention",
            COUNT,
            QUEUE_DRAIN,
            2.0,
            "Backlog depth - saturates when the queue can no longer be drained "
            "before the request timeout",
        ),
    ),
    (
        "inference_latency",
        MetricSpec(
            "network_latency",
            MILLISECOND,
            FRESHNESS_BUDGET,
            2.0,
            "End-to-end inference latency against the detection freshness budget",
        ),
    ),
    (
        "observed_latency",
        MetricSpec(
            "network_latency",
            MILLISECOND,
            FRESHNESS_BUDGET,
            2.0,
            "Observed end-to-end latency against the detection freshness budget",
        ),
    ),
    (
        "queue.wait",
        MetricSpec(
            "network_latency",
            MILLISECOND,
            FRESHNESS_BUDGET,
            2.0,
            "Time spent waiting in the inference queue",
        ),
    ),
    (
        "latency",
        MetricSpec(
            "network_latency",
            MILLISECOND,
            CONTROL_DEADLINE,
            2.0,
            "Request latency against the control loop deadline",
        ),
    ),
    (
        "rtt",
        MetricSpec(
            "network_latency",
            MILLISECOND,
            CONTROL_DEADLINE,
            2.0,
            "Round trip time against the control loop deadline",
        ),
    ),
    (
        "delay",
        MetricSpec(
            "network_latency",
            MILLISECOND,
            CONTROL_DEADLINE,
            2.0,
            "Propagation delay against the control loop deadline",
        ),
    ),
    (
        "jitter",
        MetricSpec(
            "network_latency",
            MILLISECOND,
            CONTROL_DEADLINE,
            0.2,
            "Jitter - saturates at 20% of the control loop deadline",
        ),
    ),
    (
        "duration",
        MetricSpec(
            "network_latency",
            MILLISECOND,
            FRESHNESS_BUDGET,
            2.0,
            "Observed operation duration against the detection freshness budget",
        ),
    ),
    (
        "packet_loss",
        MetricSpec(
            "network_latency",
            PERCENT,
            PACKET_LOSS,
            2.0,
            "Packet loss - a control-plane link fails at a fraction of a percent",
        ),
    ),
    (
        "utilization",
        MetricSpec(
            "resource_contention",
            PERCENT,
            PERCENT_FULL,
            1.0,
            "Utilisation - a ratio, 100% is saturation",
        ),
    ),
)


def classify_metric(metric_name: str) -> Optional[MetricSpec]:
    """Classify a metric name into the state dimension it constrains."""
    if not metric_name:
        return None
    lowered = str(metric_name).strip().lower().replace("-", "_")
    for token, spec in _METRIC_RULES:
        if token in lowered:
            return spec
    return None


# ---------------------------------------------------------------------------
# Calibration profile
# ---------------------------------------------------------------------------

# Declared budgets and where they come from.  The value is the fallback used
# only when the bundle does not declare the quantity itself.
_DECLARED_BUDGETS: Dict[str, Tuple[str, float]] = {
    "detection_freshness_budget_ms": ("robot_params.safety", 120.0),
    "control_loop_deadline_ms": ("robot_params.safety", 100.0),
    "transform_timeout_ms": ("robot_params.safety", 100.0),
    "batching_window_ms": ("inference.dynamic_batching", 200.0),
    "batching_timeout_ms": ("inference.dynamic_batching", 500.0),
    "max_batch_size": ("inference.dynamic_batching", 8.0),
    "detection_frequency_hz": ("robot_params.perception", 10.0),
    "cpu_cores": ("robot_params.resources", 4.0),
}


@dataclass
class CalibrationProfile:
    """The scales an incident's measurements are expressed against."""

    budgets: Dict[str, float] = field(default_factory=dict)
    origins: Dict[str, str] = field(default_factory=dict)
    learned: Dict[str, float] = field(default_factory=dict)

    # -- construction -------------------------------------------------------

    @classmethod
    def from_bundle(cls, bundle_path: Optional[Path]) -> "CalibrationProfile":
        """Build a profile from the bundle's declared configuration."""
        profile = cls()
        profile.budgets = {name: fallback for name, (_, fallback) in _DECLARED_BUDGETS.items()}
        profile.origins = {name: "default" for name in _DECLARED_BUDGETS}

        if not bundle_path:
            return profile

        root = Path(bundle_path)
        robot_params = _read_yaml(root / "config" / "robot_params.yaml")
        inference = _read_yaml(root / "config" / "inference.yaml")

        safety = robot_params.get("safety") if isinstance(robot_params, dict) else None
        perception = robot_params.get("perception") if isinstance(robot_params, dict) else None
        batching = inference.get("dynamic_batching") if isinstance(inference, dict) else None
        resources = robot_params.get("resources") if isinstance(robot_params, dict) else None

        declared = {
            "detection_freshness_budget_ms": _dig(safety, "detection_freshness_budget_ms"),
            "control_loop_deadline_ms": _dig(safety, "control_loop_deadline_ms"),
            "transform_timeout_ms": _dig(safety, "transform_timeout_ms"),
            "batching_window_ms": _dig(batching, "batching_window_ms"),
            "batching_timeout_ms": _dig(batching, "timeout_ms"),
            "max_batch_size": _dig(batching, "max_batch_size"),
            "detection_frequency_hz": _dig(perception, "required_detection_frequency_hz"),
            "cpu_cores": _dig(resources, "default", "cpu_cores"),
        }

        sources = {
            "detection_freshness_budget_ms": "config/robot_params.yaml:safety",
            "control_loop_deadline_ms": "config/robot_params.yaml:safety",
            "transform_timeout_ms": "config/robot_params.yaml:safety",
            "batching_window_ms": "config/inference.yaml:dynamic_batching",
            "batching_timeout_ms": "config/inference.yaml:dynamic_batching",
            "max_batch_size": "config/inference.yaml:dynamic_batching",
            "detection_frequency_hz": "config/robot_params.yaml:perception",
            "cpu_cores": "config/robot_params.yaml:resources",
        }

        for name, value in declared.items():
            if isinstance(value, (int, float)) and value > 0:
                profile.budgets[name] = float(value)
                profile.origins[name] = sources.get(name, "bundle")

        return profile

    # -- learning from evidence --------------------------------------------

    def learn_from_events(self, events: List[Mapping[str, Any]]) -> "CalibrationProfile":
        """Learn capacities the bundle did not declare but the evidence exports.

        A metric stream that reports ``memory_total_mb`` states the capacity
        that ``memory_used_mb`` is a fraction of; there is no reason to
        hardcode one.
        """
        for event in events or []:
            attributes = event.get("attributes")
            if not isinstance(attributes, Mapping):
                continue
            name = attributes.get("metric_name")
            value = attributes.get("metric_value")
            if not isinstance(name, str) or not isinstance(value, (int, float)):
                continue
            lowered = name.strip().lower()
            if lowered.endswith("_total_mb") or lowered.endswith("_total_bytes"):
                self.learned[lowered] = float(value)
        return self

    # -- scaling ------------------------------------------------------------

    def saturation_for(self, spec: MetricSpec) -> Tuple[float, str]:
        """The observation value at which a metric reads as fully saturated."""
        limit = spec.limit

        if limit == PERCENT_FULL:
            return 100.0, "percent scale"
        if limit == RATIO_FULL:
            return 1.0, "unit interval"
        if limit == FRESHNESS_BUDGET:
            budget = self.budgets.get("detection_freshness_budget_ms", 120.0)
            return budget * spec.saturation_multiplier, self.origins.get(
                "detection_freshness_budget_ms", "default"
            )
        if limit == CONTROL_DEADLINE:
            deadline = self.budgets.get("control_loop_deadline_ms", 100.0)
            return deadline * spec.saturation_multiplier, self.origins.get(
                "control_loop_deadline_ms", "default"
            )
        if limit == PACKET_LOSS:
            return 2.0, "control-plane loss limit (1% per cent)"
        if limit == CPU_CORES:
            cores = self.budgets.get("cpu_cores", 4.0)
            return cores * spec.saturation_multiplier, self.origins.get("cpu_cores", "default")
        if limit == QUEUE_DRAIN:
            # A queue deeper than (arrival rate x request timeout) cannot be
            # drained before the request times out.
            frequency = self.budgets.get("detection_frequency_hz", 10.0)
            timeout_ms = self.budgets.get("batching_timeout_ms", 500.0)
            threshold = frequency * (timeout_ms / 1000.0)
            return max(
                threshold * spec.saturation_multiplier, 1.0
            ), "arrival rate x request timeout"
        if limit == LEARNED_CAPACITY:
            for key, value in self.learned.items():
                if "memory" in key and key.endswith("_total_mb"):
                    return value, f"evidence ({key})"
            return 1024.0, "default capacity"

        return 1.0, "uncalibrated"

    def normalise(
        self, metric_name: str, value: float, unit: str = ""
    ) -> Optional[Tuple[str, float]]:
        """Map a raw metric reading onto ``(dimension, pressure in [0,1])``."""
        spec = classify_metric(metric_name)
        if spec is None:
            return None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None

        saturation, _origin = self.saturation_for(spec)

        # A ratio metric reported in percent units is scaled by 100 instead.
        scale = spec.scale
        if scale == PERCENT and unit == "" and abs(value) <= 1.0 and value > 0:
            scale = RATIO
        if scale == RATIO:
            saturation = 1.0
        elif scale == MEGABYTE and "total_mb" in str(metric_name).lower():
            # A capacity reading is not a pressure; it only sets the scale.
            return None

        if saturation <= 0:
            return None

        pressure = float(value) / float(saturation)
        return spec.dimension, max(0.0, min(1.0, pressure))

    def to_dict(self) -> Dict[str, Any]:
        """Serializable description of the calibration in force."""
        return {
            "budgets": dict(self.budgets),
            "origins": dict(self.origins),
            "learned": dict(self.learned),
        }


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - malformed config
        logger.warning(f"Could not read {path}: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def _dig(mapping: Any, *keys: str) -> Any:
    current = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


# ---------------------------------------------------------------------------
# Measurement extraction
# ---------------------------------------------------------------------------

# Attribute names that carry a declared setting rather than an observation.
_CONFIG_LIKE = (
    "budget",
    "window",
    "timeout",
    "deadline",
    "threshold",
    "limit",
    "target",
    "interval",
    "period",
    "sampling",
    "max_batch",
    "batch_size",
    "capacity",
    "total",
)

# Numeric attribute suffixes that make a value a measurement.
_MEASUREMENT_SUFFIXES = ("_ms", "_ns", "_percent", "_pct", "_mb", "_hz", "_utilization")

_MESSAGE_PATTERNS = (
    (re.compile(r"(\d+(?:\.\d+)?)\s*ms\b", re.IGNORECASE), "latency_ms", "ms"),
    (re.compile(r"\bdepth\b[^0-9]{0,12}(\d+)", re.IGNORECASE), "queue_depth", "count"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*frames?\s+pending", re.IGNORECASE), "queue_depth", "count"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:percent|%)", re.IGNORECASE), "utilization_percent", "%"),
)


def _is_measurement_attribute(name: str) -> bool:
    lowered = name.lower()
    if any(token in lowered for token in _CONFIG_LIKE):
        return False
    return lowered.endswith(_MEASUREMENT_SUFFIXES) or lowered in {
        "queue_depth",
        "jitter",
        "packet_loss",
        "latency",
        "utilization",
    }


def extract_measurements(event: Mapping[str, Any]) -> List[Tuple[str, float, str]]:
    """Extract the numeric measurements an evidence event actually carries.

    Returns ``(metric_name, value, unit)`` triples.  Configured settings
    (budgets, batching windows, timeouts) are excluded: they describe what
    the system was told to do, not what it did.
    """
    measurements: List[Tuple[str, float, str]] = []
    attributes = event.get("attributes")
    attributes = attributes if isinstance(attributes, Mapping) else {}

    # A metric export states its metric explicitly.
    metric_name = attributes.get("metric_name")
    metric_value = attributes.get("metric_value")
    if isinstance(metric_name, str) and isinstance(metric_value, (int, float)):
        if not isinstance(metric_value, bool):
            unit = attributes.get("unit")
            measurements.append(
                (metric_name, float(metric_value), str(unit) if isinstance(unit, str) else "")
            )
            return measurements

    # Numeric attributes that look like measurements.
    for key, value in attributes.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if not _is_measurement_attribute(str(key)):
            continue
        name = str(key)
        unit = ""
        if name.endswith("_ns"):
            # Nanosecond durations are converted to the millisecond scale the
            # budgets are expressed in.
            measurements.append((name[:-3] + "_ms", float(value) / 1_000_000.0, "ms"))
            continue
        if name.endswith("_ms"):
            unit = "ms"
        elif name.endswith("_percent") or name.endswith("_pct"):
            unit = "%"
        elif name.endswith("_mb"):
            unit = "MB"
        elif name.endswith("_hz"):
            unit = "Hz"
        measurements.append((name, float(value), unit))

    if measurements:
        return measurements

    # Recordings carry their payload one level down.
    payload = attributes.get("payload")
    if isinstance(payload, Mapping):
        nested = extract_measurements({"attributes": dict(payload)})
        if nested:
            return nested

    # Numbers stated in the message itself.
    message = event.get("message")
    if isinstance(message, str) and message:
        for pattern, name, unit in _MESSAGE_PATTERNS:
            for match in pattern.finditer(message):
                try:
                    measurements.append((name, float(match.group(1)), unit))
                except (TypeError, ValueError):  # pragma: no cover - defensive
                    continue
    return measurements

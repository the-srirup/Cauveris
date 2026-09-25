"""
Temporal analysis configuration.

Thresholds are read from the incident bundle's real configuration files
(`config/robot_params.yaml`, `config/inference.yaml`) wherever possible, so the
analyzer reasons against the same budgets the robot actually enforces rather
than against hard-coded constants.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


#: Default per-provenance tolerance (ms) for a cause -> effect latency.
#: Keys are ``CausalityProvenance`` values; lookups fall back to ``default_ms``.
DEFAULT_PROVENANCE_TOLERANCE_MS: Dict[str, float] = {
    # A span inside a single trace is ordered by the tracer itself; allow only
    # modest scheduling noise.
    "otel_trace_order": 25.0,
    # Two topics on the same ROS 2 middleware hop. Delivery is same-host.
    "ros_topic_order": 50.0,
    # A log line written by a node that consumed the output of another node.
    "log_node_order": 100.0,
    # Cloud service -> robot stack, crossing the network and the middleware.
    "cross_domain_handoff": 250.0,
    # A deployment made hours earlier causing a later runtime effect. The
    # *ordering* is what matters here, not the latency, so the tolerance is the
    # whole observation window.
    "deployment_chain": 24 * 60 * 60 * 1000.0,
    # Statistical proximity only; weakest class of edge.
    "temporal_proximity": 500.0,
}


@dataclass(frozen=True)
class TolerancePolicy:
    """
    Decides how much negative time delta counts as a real causality violation.

    A violation is only asserted when the observed delta is negative by more
    than the tolerance. Tolerance is the sum of:

    * the provenance's expected latency allowance,
    * ``jitter_multiplier`` x the measured inter-domain jitter,
    * ``precision_multiplier`` x the coarser of the two timestamp precisions.

    The precision term is what stops the analyzer from reporting a false
    causality reversal when one side of the edge came from a log file with
    one-second timestamp granularity.
    """

    default_ms: float = 50.0
    per_provenance_ms: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_PROVENANCE_TOLERANCE_MS)
    )
    jitter_multiplier: float = 3.0
    precision_multiplier: float = 1.0

    def allowance_ms(self, provenance: str) -> float:
        """Expected latency allowance for an edge of the given provenance."""
        return float(self.per_provenance_ms.get(provenance, self.default_ms))

    def tolerance_ms(
        self,
        provenance: str,
        jitter_ms: float = 0.0,
        precision_ns: int = 0,
    ) -> float:
        """Total tolerance in milliseconds for one causal edge."""
        precision_ms = precision_ns / 1_000_000.0
        return (
            self.allowance_ms(provenance)
            + self.jitter_multiplier * max(0.0, jitter_ms)
            + self.precision_multiplier * max(0.0, precision_ms)
        )


@dataclass(frozen=True)
class TemporalConfig:
    """Thresholds and limits for a single temporal analysis run."""

    # --- Budgets, normally sourced from the real robot configuration ---
    freshness_budget_ms: float = 120.0
    control_loop_deadline_ms: float = 100.0
    transform_timeout_ms: float = 100.0

    # --- Latency expectation for the inference path, from inference.yaml ---
    batching_window_ms: float = 0.0
    max_batch_size: int = 0
    per_batch_item_ms: float = 5.0
    base_gpu_exec_ms: float = 30.0

    # --- Statistical parameters ---
    clock_skew_threshold_ms: float = 10.0
    mad_k: float = 3.5
    proximity_window_ms: float = 250.0
    duplicate_epsilon: float = 1e-9

    # --- Safety limits ---
    max_events: int = 200_000
    min_loop_confidence: float = 0.5

    tolerance: TolerancePolicy = field(default_factory=TolerancePolicy)

    # ------------------------------------------------------------------ #
    # Expected inference latency ceiling implied by the real batching config
    # ------------------------------------------------------------------ #
    @property
    def expected_inference_latency_ms(self) -> float:
        """
        Upper bound on inference latency implied by the deployed batching
        configuration. Zero when the configuration was not available.
        """
        if self.batching_window_ms <= 0:
            return 0.0
        batch_exec = self.base_gpu_exec_ms + self.max_batch_size * self.per_batch_item_ms
        return self.batching_window_ms + batch_exec

    # ------------------------------------------------------------------ #
    # Constructors
    # ------------------------------------------------------------------ #
    @classmethod
    def from_bundle(cls, bundle_path: Optional[Path]) -> "TemporalConfig":
        """
        Build a configuration from the real bundle configuration files.

        Any file that is missing or unreadable simply leaves the corresponding
        field at its default; the analyzer degrades rather than failing.
        """
        if bundle_path is None:
            return cls()

        robot_params = cls._load_yaml(bundle_path / "config" / "robot_params.yaml")
        inference = cls._load_yaml(bundle_path / "config" / "inference.yaml")

        safety = robot_params.get("safety", {}) if isinstance(robot_params, dict) else {}
        batching = inference.get("dynamic_batching", {}) if isinstance(inference, dict) else {}

        kwargs: Dict[str, object] = {}

        budget = safety.get("detection_freshness_budget_ms")
        if isinstance(budget, (int, float)):
            kwargs["freshness_budget_ms"] = float(budget)

        deadline = safety.get("control_loop_deadline_ms")
        if isinstance(deadline, (int, float)):
            kwargs["control_loop_deadline_ms"] = float(deadline)

        transform_timeout = safety.get("transform_timeout_ms")
        if isinstance(transform_timeout, (int, float)):
            kwargs["transform_timeout_ms"] = float(transform_timeout)

        window = batching.get("batching_window_ms")
        if isinstance(window, (int, float)):
            kwargs["batching_window_ms"] = float(window)

        max_batch = batching.get("max_batch_size")
        if isinstance(max_batch, (int, float)):
            kwargs["max_batch_size"] = int(max_batch)

        # The transform timeout is a defensible proxy for the inter-node
        # tolerance on the robot middleware.
        if isinstance(transform_timeout, (int, float)):
            policy = TolerancePolicy()
            policy.per_provenance_ms["ros_topic_order"] = float(transform_timeout)
            kwargs["tolerance"] = policy

        return cls(**kwargs)  # type: ignore[arg-type]

    @staticmethod
    def _load_yaml(path: Path) -> Dict:
        """Load a YAML file, returning an empty dict on any failure."""
        try:
            import yaml

            if not path.exists():
                return {}
            with open(path, "r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
            return data if isinstance(data, dict) else {}
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not load temporal config from %s: %s", path, exc)
            return {}

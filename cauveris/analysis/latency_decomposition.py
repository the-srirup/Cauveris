"""
Causal Latency Decomposition & Multi-Strategy Repair Evaluation.

Deconstructs end-to-end request latency into atomic, provenance-backed components:
  Total Latency = Queue Wait + Batching Wait + Request Transport + Dependency Wait
                + Compute Time + Response Transport + Scheduling Overhead + Other

Calculates the physical lower bound on achievable latency and prevents
mathematically impossible repairs or unsafe timeout increases.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from cauveris.analysis.provenance import ProvenanceClass, normalize_provenance_string


class RepairStrategyType(str, Enum):
    REDUCE_BATCHING = "reduce_batching"
    REDUCE_QUEUE_WAIT = "reduce_queue_wait"
    INCREASE_WORKERS = "increase_workers"
    REDUCE_DEPENDENCY_LATENCY = "reduce_dependency_latency"
    CACHE = "cache"
    CIRCUIT_BREAKER = "circuit_breaker"
    ASYNC_EXECUTION = "asynchronous_execution"
    TIMEOUT_ADJUSTMENT = "timeout_adjustment"
    FALLBACK_BEHAVIOR = "fallback_behavior"
    NO_SAFE_AUTOMATIC_REPAIR = "no_safe_automatic_repair"


class LatencyComponent(BaseModel):
    """An atomic component of the end-to-end request latency."""
    name: str
    value: Optional[float] = None
    unit: str = "ms"
    provenance: ProvenanceClass = ProvenanceClass.OBSERVED
    source_artifact: Optional[str] = None
    source_locator: Optional[str] = None
    calculation_rationale: Optional[str] = None
    uncertainty: Optional[float] = None
    changed_under_intervention: bool = False
    reason_for_change: Optional[str] = None
    min_physically_achievable_ms: float = 0.0

    @property
    def display_value(self) -> str:
        """String representation showing UNAVAILABLE when value is None or missing."""
        if self.value is None or self.provenance == ProvenanceClass.UNAVAILABLE:
            return "UNAVAILABLE"
        if isinstance(self.value, float) and self.value.is_integer():
            return f"{int(self.value)} {self.unit}".strip()
        return f"{self.value:.2f} {self.unit}".strip()


class StrategyEvaluation(BaseModel):
    """Detailed evaluation of an applicable mitigation strategy."""
    strategy: RepairStrategyType
    viable: bool
    projected_latency_ms: float
    violates_deadline: bool = False
    rejection_reason: Optional[str] = None
    mathematical_proof: str = ""


class LatencyDecomposition(BaseModel):
    """Complete causal latency decomposition and lower-bound verification."""
    queue_wait: LatencyComponent
    batching_wait: LatencyComponent
    request_transport: LatencyComponent
    dependency_wait: LatencyComponent
    compute_time: LatencyComponent
    response_transport: LatencyComponent
    scheduling_overhead: LatencyComponent
    other_components: List[LatencyComponent] = Field(default_factory=list)

    total_latency_ms: float
    active_timeout_ms: float
    control_deadline_ms: float
    min_achievable_latency_ms: float

    root_cause_component: str
    contributing_factors: List[str] = Field(default_factory=list)
    symptom: str = "Request timeout / deadline exceeded"

    strategy_evaluations: List[StrategyEvaluation] = Field(default_factory=list)
    selected_strategy: RepairStrategyType
    explanation: str


def decompose_and_evaluate_latency(
    queue_wait_ms: float,
    batching_wait_ms: float,
    request_transport_ms: float,
    dependency_wait_ms: float,
    compute_time_ms: float,
    response_transport_ms: float,
    scheduling_overhead_ms: float,
    active_timeout_ms: float,
    control_deadline_ms: float,
    dependency_can_be_cached: bool = False,
    workers_can_scale: bool = True,
    provenance_map: Optional[Dict[str, str]] = None,
) -> LatencyDecomposition:
    """
    Performs rigorous causal decomposition and strategy evaluation.
    """
    prov = provenance_map or {}

    def _resolve_prov(key: str, default_prov: ProvenanceClass) -> tuple[ProvenanceClass, Optional[str]]:
        raw = prov.get(key)
        if raw is None:
            return default_prov, None
        if isinstance(raw, ProvenanceClass):
            return raw, None
        return normalize_provenance_string(str(raw))

    p_queue, r_queue = _resolve_prov("queue_wait", ProvenanceClass.OBSERVED)
    c_queue = LatencyComponent(
        name="queue_wait",
        value=queue_wait_ms,
        provenance=p_queue,
        calculation_rationale=r_queue or "Derived from queue ingress to dispatch interval",
        min_physically_achievable_ms=0.5,
    )
    p_batch, r_batch = _resolve_prov("batching_wait", ProvenanceClass.DECLARED)
    c_batch = LatencyComponent(
        name="batching_wait",
        value=batching_wait_ms,
        provenance=p_batch,
        calculation_rationale=r_batch or "Extracted from batching timeout configuration",
        min_physically_achievable_ms=0.0,
    )
    p_req, r_req = _resolve_prov("request_transport", ProvenanceClass.OBSERVED)
    c_req_tx = LatencyComponent(
        name="request_transport",
        value=request_transport_ms,
        provenance=p_req,
        calculation_rationale=r_req or "Measured network transit duration to worker host",
        min_physically_achievable_ms=max(1.0, request_transport_ms * 0.8),
    )
    p_dep, r_dep = _resolve_prov("dependency_wait", ProvenanceClass.OBSERVED)
    c_dep = LatencyComponent(
        name="dependency_wait",
        value=dependency_wait_ms,
        provenance=p_dep,
        calculation_rationale=r_dep or "Measured remote RPC / dependency round-trip duration",
        min_physically_achievable_ms=dependency_wait_ms if not dependency_can_be_cached else 1.0,
    )
    p_comp, r_comp = _resolve_prov("compute_time", ProvenanceClass.OBSERVED)
    c_compute = LatencyComponent(
        name="compute_time",
        value=compute_time_ms,
        provenance=p_comp,
        calculation_rationale=r_comp or "Measured on-device kernel / process CPU execution time",
        min_physically_achievable_ms=max(5.0, compute_time_ms * 0.9),
    )
    p_resp, r_resp = _resolve_prov("response_transport", ProvenanceClass.OBSERVED)
    c_resp_tx = LatencyComponent(
        name="response_transport",
        value=response_transport_ms,
        provenance=p_resp,
        calculation_rationale=r_resp or "Measured response payload transmission duration",
        min_physically_achievable_ms=max(1.0, response_transport_ms * 0.8),
    )
    p_sched, r_sched = _resolve_prov("scheduling_overhead", ProvenanceClass.INFERRED)
    c_sched = LatencyComponent(
        name="scheduling_overhead",
        value=scheduling_overhead_ms,
        provenance=p_sched,
        calculation_rationale=r_sched or "Residual delay attributed to OS thread scheduling and dispatch jitter",
        min_physically_achievable_ms=0.2,
    )

    total_latency = (
        queue_wait_ms
        + batching_wait_ms
        + request_transport_ms
        + dependency_wait_ms
        + compute_time_ms
        + response_transport_ms
        + scheduling_overhead_ms
    )

    # Minimum physically achievable latency assuming zero queue and zero batching wait
    min_achievable = (
        c_queue.min_physically_achievable_ms
        + c_batch.min_physically_achievable_ms
        + c_req_tx.min_physically_achievable_ms
        + c_dep.min_physically_achievable_ms
        + c_compute.min_physically_achievable_ms
        + c_resp_tx.min_physically_achievable_ms
        + c_sched.min_physically_achievable_ms
    )

    # Identify dominant component (root cause)
    components = {
        "dependency_wait": dependency_wait_ms,
        "batching_wait": batching_wait_ms,
        "queue_wait": queue_wait_ms,
        "compute_time": compute_time_ms,
        "request_transport": request_transport_ms + response_transport_ms,
    }
    root_cause = max(components, key=components.get)
    contributing = [k for k, v in components.items() if k != root_cause and v > 0.15 * total_latency]

    # Evaluate Strategies
    evaluations: List[StrategyEvaluation] = []

    # Strategy 1: Reduce batching
    lat_if_batch_reduced = total_latency - batching_wait_ms
    can_batching_alone_fix = (lat_if_batch_reduced <= active_timeout_ms) and (lat_if_batch_reduced <= control_deadline_ms)
    evaluations.append(
        StrategyEvaluation(
            strategy=RepairStrategyType.REDUCE_BATCHING,
            viable=can_batching_alone_fix,
            projected_latency_ms=round(lat_if_batch_reduced, 2),
            violates_deadline=lat_if_batch_reduced > control_deadline_ms,
            rejection_reason=(
                None if can_batching_alone_fix
                else f"Batching reduction to 0ms yields {lat_if_batch_reduced:.1f}ms, which still exceeds timeout {active_timeout_ms}ms"
                if lat_if_batch_reduced > active_timeout_ms
                else f"Violates control deadline {control_deadline_ms}ms"
            ),
            mathematical_proof=f"Total ({total_latency:.1f}ms) - Batching ({batching_wait_ms:.1f}ms) = {lat_if_batch_reduced:.1f}ms vs Target ({min(active_timeout_ms, control_deadline_ms):.1f}ms)",
        )
    )

    # Strategy 2: Reduce queue wait (e.g. scale workers)
    lat_if_queue_reduced = total_latency - max(0.0, queue_wait_ms - 2.0)
    can_queue_fix = (lat_if_queue_reduced <= active_timeout_ms) and workers_can_scale
    evaluations.append(
        StrategyEvaluation(
            strategy=RepairStrategyType.INCREASE_WORKERS,
            viable=can_queue_fix,
            projected_latency_ms=round(lat_if_queue_reduced, 2),
            rejection_reason=None if can_queue_fix else f"Queue reduction yields {lat_if_queue_reduced:.1f}ms, exceeding {active_timeout_ms}ms",
            mathematical_proof=f"Queue reduced to 2ms -> Projected {lat_if_queue_reduced:.1f}ms",
        )
    )

    # Strategy 3: Caching
    if dependency_can_be_cached:
        lat_if_cached = total_latency - dependency_wait_ms + 1.0
        can_cache_fix = lat_if_cached <= active_timeout_ms
        evaluations.append(
            StrategyEvaluation(
                strategy=RepairStrategyType.CACHE,
                viable=can_cache_fix,
                projected_latency_ms=round(lat_if_cached, 2),
                rejection_reason=None if can_cache_fix else f"Cached latency {lat_if_cached:.1f}ms exceeds target",
                mathematical_proof=f"Dependency wait eliminated via cache -> Projected {lat_if_cached:.1f}ms",
            )
        )

    # Strategy 4: Timeout adjustment (PROHIBITED if timeout would exceed control deadline!)
    new_timeout_needed = total_latency + 20.0
    violates_control = new_timeout_needed > control_deadline_ms
    can_timeout_increase = not violates_control
    evaluations.append(
        StrategyEvaluation(
            strategy=RepairStrategyType.TIMEOUT_ADJUSTMENT,
            viable=can_timeout_increase,
            projected_latency_ms=round(total_latency, 2),
            violates_deadline=violates_control,
            rejection_reason=(
                f"Increasing request timeout to {new_timeout_needed:.1f}ms violates stricter control deadline {control_deadline_ms}ms"
                if violates_control else None
            ),
            mathematical_proof=f"Required timeout ({new_timeout_needed:.1f}ms) vs Control Deadline ({control_deadline_ms:.1f}ms)",
        )
    )

    # Strategy Selection
    viable_strategies = [e for e in evaluations if e.viable]
    if not viable_strategies:
        selected_strategy = RepairStrategyType.NO_SAFE_AUTOMATIC_REPAIR
        explanation = (
            f"No safe automatic repair exists: minimum achievable latency {min_achievable:.1f}ms "
            f"exceeds timeout/deadline envelope. Root cause is {root_cause} ({components[root_cause]:.1f}ms)."
        )
    else:
        # Choose most specific strategy addressing root cause
        if root_cause == "batching_wait" and any(e.strategy == RepairStrategyType.REDUCE_BATCHING for e in viable_strategies):
            selected_strategy = RepairStrategyType.REDUCE_BATCHING
            explanation = "Batching wait is the primary root cause and reduction is mathematically sufficient."
        elif root_cause == "queue_wait" and any(e.strategy == RepairStrategyType.INCREASE_WORKERS for e in viable_strategies):
            selected_strategy = RepairStrategyType.INCREASE_WORKERS
            explanation = "Worker queue saturation is the root cause; scaling workers clears bottleneck."
        elif root_cause == "dependency_wait" and any(e.strategy == RepairStrategyType.CACHE for e in viable_strategies):
            selected_strategy = RepairStrategyType.CACHE
            explanation = "Dependency wait dominates; caching responses clears deadline violation."
        else:
            selected_strategy = viable_strategies[0].strategy
            explanation = f"Selected viable mitigation strategy {selected_strategy.value}."

    return LatencyDecomposition(
        queue_wait=c_queue,
        batching_wait=c_batch,
        request_transport=c_req_tx,
        dependency_wait=c_dep,
        compute_time=c_compute,
        response_transport=c_resp_tx,
        scheduling_overhead=c_sched,
        total_latency_ms=round(total_latency, 2),
        active_timeout_ms=active_timeout_ms,
        control_deadline_ms=control_deadline_ms,
        min_achievable_latency_ms=round(min_achievable, 2),
        root_cause_component=root_cause,
        contributing_factors=contributing,
        strategy_evaluations=evaluations,
        selected_strategy=selected_strategy,
        explanation=explanation,
    )

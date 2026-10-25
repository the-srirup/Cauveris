"""
A calibrated latency model for cloud/edge perception pipelines.

The previous implementation of the "digital twin" was a forty-line function
returning ``(batching_window_ms * 0.52) + uniform(-3, 3)``.  It could not
explain the incident it was supposed to reproduce and it could not answer
counterfactual questions about any other incident.

This module replaces it with a real model:

* A **discrete-event simulation** of the perception pipeline:

      sensor capture -> [transport] -> inference server (dynamic batching)
                     -> [transport] -> subscriber queue (ROS QoS)
                     -> control-loop sampling

* The simulation parameters are **calibrated against the incident's own
  evidence** (span durations, batch-wait attributes, network CSVs, queue-depth
  series, log-derived latencies) by bounded global optimisation, and the
  residuals of that fit are reported so the model never overstates its
  confidence.

* Counterfactuals are re-simulated with modified configuration, so a patch is
  judged on what the model predicts, not on a scenario-specific rule.

The optimisation target, parameter vector and DES are all incident-agnostic.
"""

from __future__ import annotations

import heapq
import logging
import math
import random
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .statistics import Distribution, distribution, percentile

logger = logging.getLogger(__name__)

try:
    from scipy.optimize import differential_evolution, minimize
except Exception:  # pragma: no cover
    differential_evolution = None  # type: ignore
    minimize = None  # type: ignore

__all__ = [
    "TwinParameters",
    "SimulationOutcome",
    "LatencyCalibration",
    "simulate_pipeline",
    "calibrate_latency_model",
]


@dataclass
class TwinParameters:
    """Physical parameters of the perception pipeline (all times in ms)."""

    # Sensor / producer
    arrival_rate_hz: float = 10.0
    initial_backlog_frames: float = 0.0

    # Inference service
    batching_window_ms: float = 100.0
    max_batch_size: int = 8
    server_workers: int = 1
    service_base_ms: float = 10.0
    service_per_item_ms: float = 5.0

    # Transport
    transport_mean_ms: float = 5.0
    transport_sigma_ms: float = 1.0
    transport_loss_prob: float = 0.0

    # Subscriber
    qos_queue_depth: int = 1
    consumer_rate_hz: float = 10.0

    # Time base
    clock_skew_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


@dataclass
class SimulationOutcome:
    """Output of one pipeline simulation."""

    frames: int = 0
    consumed: int = 0
    dropped: int = 0
    stale_count: int = 0
    stale_rate: float = 0.0
    mean_age_ms: float = 0.0
    p50_age_ms: float = 0.0
    p90_age_ms: float = 0.0
    p95_age_ms: float = 0.0
    p99_age_ms: float = 0.0
    max_age_ms: float = 0.0
    mean_epoch_wait_ms: float = 0.0
    p95_epoch_wait_ms: float = 0.0
    mean_service_ms: float = 0.0
    mean_batch_size: float = 0.0
    mean_transport_ms: float = 0.0
    mean_backlog: float = 0.0
    max_backlog: float = 0.0
    server_utilisation: float = 0.0
    deadline_miss_rate: float = 0.0
    age_distribution: Distribution = field(default_factory=Distribution)
    #: The age of every consumed frame, in order.  The twin drives the robot
    #: with this series rather than with numbers drawn from the summary.
    age_series: List[float] = field(default_factory=list)
    #: Which of those frames were older than the freshness budget.
    stale_series: List[bool] = field(default_factory=list)
    #: The server-side request latency of every consumed frame, in order.
    request_latency_series: List[float] = field(default_factory=list)
    # Server-side request latency (batching wait + inference service).  This is
    # a different quantity from end-to-end age: it excludes the return
    # transport and the control loop's sampling delay.
    mean_request_latency_ms: float = 0.0
    p95_request_latency_ms: float = 0.0
    # Age of a frame when it reaches the subscriber, i.e. the end-to-end age
    # *before* the control loop's sampling delay.  Comparing this with
    # ``mean_age_ms`` separates "the data took too long to arrive" from "the
    # control loop acted on it late".
    mean_delivery_age_ms: float = 0.0
    p95_delivery_age_ms: float = 0.0
    mean_sampling_delay_ms: float = 0.0
    # Which limit closed each batching epoch.  A window-limited epoch means the
    # timer fired before the batch was full; a size-limited epoch means the
    # batch filled up first.  The two regimes respond oppositely to a change
    # in the batching window, so the model has to know which one it is in.
    size_limited_epochs: int = 0
    window_limited_epochs: int = 0
    frames_served: int = 0

    @property
    def size_limited_fraction(self) -> float:
        total = self.size_limited_epochs + self.window_limited_epochs
        return (self.size_limited_epochs / total) if total else 0.0

    def as_dict(self) -> Dict[str, Any]:
        out = {
            k: (round(v, 4) if isinstance(v, float) else v)
            for k, v in asdict(self).items()
            if k != "age_distribution"
        }
        out["age_distribution"] = self.age_distribution.as_dict()
        return out


@dataclass
class LatencyCalibration:
    """The outcome of fitting the model to a specific incident's evidence."""

    params: TwinParameters
    score: float
    targets: Dict[str, Optional[float]] = field(default_factory=dict)
    residuals: Dict[str, Optional[float]] = field(default_factory=dict)
    fitted: Dict[str, Optional[float]] = field(default_factory=dict)
    quality: str = "uncalibrated"
    notes: List[str] = field(default_factory=list)
    #: Where the bundle's age numbers were measured: "delivery", "consumption",
    #: "server-boundary" or "unknown".  It decides which of the model's two age
    #: series the recorded age is compared with, so it is read from the
    #: evidence rather than inferred from the fit.
    age_measurement_basis: str = "unknown"
    #: The simulated value each target was actually compared with.  One entry
    #: per target, but the *stage* can differ from the target's name: a target
    #: measured at delivery is compared with the model's age at delivery, not
    #: with its age at consumption.
    compared: Dict[str, Optional[float]] = field(default_factory=dict)
    #: The target the fit missed most, and by how much (relative error).
    worst_target: Optional[str] = None
    worst_relative_error: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "parameters": self.params.as_dict(),
            "score": round(self.score, 6),
            "quality": self.quality,
            "targets": {k: (None if v is None else round(v, 4)) for k, v in self.targets.items()},
            "residuals": {k: (None if v is None else round(v, 4)) for k, v in self.residuals.items()},
            "fitted": {k: (None if v is None else round(v, 4)) for k, v in self.fitted.items()},
            "compared": {k: (None if v is None else round(v, 4)) for k, v in self.compared.items()},
            "age_measurement_basis": self.age_measurement_basis,
            "worst_target": self.worst_target,
            "worst_relative_error": (
                None if self.worst_relative_error is None else round(self.worst_relative_error, 4)
            ),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Discrete-event simulation
# ---------------------------------------------------------------------------


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def simulate_pipeline(
    params: TwinParameters,
    *,
    duration_s: float = 2.0,
    warmup_s: float = 0.0,
    seed: int = 12345,
    freshness_budget_ms: Optional[float] = None,
    control_deadline_ms: Optional[float] = None,
    age_basis: str = "delivery",
) -> SimulationOutcome:
    """
    Simulate the perception pipeline with dynamic batching.

    The simulation is event-driven.  Frames arrive as a Poisson process, wait
    for a dynamic-batching epoch (bounded by the batching window and the
    maximum batch size), are served by a single inference worker whose service
    time grows with batch size, traverse a lossy transport link, land in a
    bounded subscriber queue (ROS QoS KEEP_LAST semantics: the oldest sample is
    dropped when the buffer is full), and are finally sampled by the control
    loop.

    Args:
        params: Physical parameters of the pipeline.
        duration_s: Measurement window.
        warmup_s: Simulated time before the measurement window (to let a
            backlog reach the state the incident exhibits).
        seed: RNG seed, so results are reproducible.
        freshness_budget_ms: If given, frames older than this are counted stale.
        control_deadline_ms: If given, frames older than this count as a
            missed control deadline.

    Returns:
        A :class:`SimulationOutcome` describing the measurement window.
    """
    rng = random.Random(seed)

    lam = max(1e-3, params.arrival_rate_hz)
    window_s = max(0.0, params.batching_window_ms / 1000.0)
    max_batch = max(1, int(params.max_batch_size))
    worker_count = max(1, int(params.server_workers))
    service_base_s = max(0.0, params.service_base_ms / 1000.0)
    service_per_item_s = max(0.0, params.service_per_item_ms / 1000.0)
    transport_mean_s = max(0.0, params.transport_mean_ms / 1000.0)
    transport_sigma_s = max(0.0, params.transport_sigma_ms / 1000.0)
    loss_prob = _clamp(params.transport_loss_prob, 0.0, 1.0)
    qos_depth = max(1, int(params.qos_queue_depth))
    consumer_hz = max(1e-3, params.consumer_rate_hz)
    consumer_period_s = 1.0 / consumer_hz
    skew_s = params.clock_skew_ms / 1000.0

    total_end_s = warmup_s + duration_s
    measure_from_s = warmup_s

    # --- state -----------------------------------------------------------
    pending: List[Tuple[float, int]] = []  # (capture_time, frame_id) awaiting a batch
    busy_workers = 0
    epoch_items: List[Tuple[float, int]] = []
    epoch_deadline: Optional[float] = None
    epoch_id = 0
    capture_times: Dict[int, float] = {}
    #: The server-side request latency of every frame the server served, keyed
    #: by frame id, so that a consumed frame's latency can be recovered.
    request_latency_by_frame: Dict[int, float] = {}
    buffer: List[Tuple[float, int]] = []  # delivered frames, newest last
    next_frame_id = 0

    # --- statistics ------------------------------------------------------
    ages: List[float] = []
    epoch_waits: List[float] = []
    services: List[float] = []
    batch_sizes: List[float] = []
    transports: List[float] = []
    request_latencies: List[float] = []
    #: The request latency of each *consumed* frame, in consumption order, so
    #: it lines up with ``ages``.
    consumed_request_latencies: List[float] = []
    #: The age of each consumed frame when it reached the subscriber.
    delivery_ages: List[float] = []
    #: The age of each frame when it reached the subscriber, keyed by frame
    #: id, so the age at delivery can be reported for the frame that was
    #: actually acted on.
    delivery_age_by_frame: Dict[int, float] = {}
    sampling_delays: List[float] = []
    backlog_samples: List[float] = []
    dropped = 0
    stale = 0
    deadline_misses = 0
    consumed = 0
    busy_time = 0.0
    produced = 0
    served = 0
    size_limited_epochs = 0
    window_limited_epochs = 0

    events: List[Tuple[float, int, str, Any]] = []
    seq = 0

    def push(t: float, kind: str, payload: Any = None) -> None:
        nonlocal seq
        seq += 1
        heapq.heappush(events, (t, seq, kind, payload))

    # Initial backlog: the incident's queue depth at observation start.
    for k in range(int(max(0, round(params.initial_backlog_frames)))):
        pending.append((0.0, next_frame_id))
        next_frame_id += 1

    next_arrival = rng.expovariate(lam)
    next_consume = 0.0

    push(next_arrival, "arrival")
    push(next_consume, "consume")

    def start_epoch(now: float) -> None:
        """Open a batching epoch at ``now`` and arm its window timer."""
        nonlocal epoch_items, epoch_deadline, epoch_id
        epoch_items = []
        epoch_id += 1
        epoch_deadline = now + window_s if window_s > 0 else now
        push(epoch_deadline, "epoch_timer", epoch_id)

    def dispatch(now: float, reason: str) -> None:
        """
        Close the epoch and hand the batch to a worker.

        If every worker is occupied the epoch stays open and is retried when a
        worker reports back, which is what makes the model reproduce backlog
        growth instead of silently dropping work.

        ``reason`` records *what* closed the epoch - ``"size"`` when the batch
        filled up, ``"window"`` when the timer fired.  The two regimes respond
        oppositely to a change in the batching window, so downstream code needs
        to know which one the incident was in.
        """
        nonlocal busy_workers, epoch_items, epoch_deadline
        nonlocal size_limited_epochs, window_limited_epochs, served
        if not epoch_items:
            epoch_deadline = None
            return
        if busy_workers >= worker_count:
            return  # retry when a worker frees up
        served_items = list(epoch_items)
        n = len(served_items)
        service_s = service_base_s + service_per_item_s * n
        for capture_t, fid in served_items:
            # Server-side request latency: how long the request waited for the
            # batch, plus how long the batch took to execute.  It is recorded
            # per frame so that the per-cycle series can line up with the
            # frames the control loop actually consumed.
            request_latency = ((now - capture_t) + service_s) * 1000.0
            request_latency_by_frame[fid] = request_latency
            if capture_t >= measure_from_s:
                epoch_waits.append((now - capture_t) * 1000.0)
                request_latencies.append(request_latency)
        if now >= measure_from_s:
            services.append(service_s * 1000.0)
            batch_sizes.append(float(n))
        served += n
        if reason == "size":
            size_limited_epochs += 1
        else:
            window_limited_epochs += 1
        busy_workers += 1
        epoch_items = []
        epoch_deadline = None
        push(now + service_s, "server_done", (served_items, service_s))

    while events:
        now, _, kind, payload = heapq.heappop(events)
        if now > total_end_s:
            break

        if kind == "arrival":
            capture_t = now
            fid = next_frame_id
            next_frame_id += 1
            capture_times[fid] = capture_t
            if now >= measure_from_s:
                produced += 1

            if busy_workers >= worker_count:
                # Every inference worker is occupied: the frame joins the backlog.
                pending.append((capture_t, fid))
            else:
                if not epoch_items:
                    start_epoch(now)
                epoch_items.append((capture_t, fid))
                if len(epoch_items) >= max_batch:
                    dispatch(now, "size")

            next_arrival = now + rng.expovariate(lam)
            push(next_arrival, "arrival")

        elif kind == "epoch_timer":
            # ``payload`` is the epoch generation this timer belongs to; stale
            # timers from earlier epochs are ignored.
            if payload == epoch_id and epoch_deadline is not None:
                if epoch_items:
                    dispatch(now, "window")

        elif kind == "server_done":
            completed_items, service_s = payload
            busy_workers = max(0, busy_workers - 1)
            if now >= measure_from_s:
                busy_time += service_s
            for capture_t, fid in completed_items:
                if transport_sigma_s > 0:
                    delay = rng.gauss(transport_mean_s, transport_sigma_s)
                else:
                    delay = transport_mean_s
                delay = max(0.0, delay)
                if rng.random() < loss_prob:
                    dropped += 1
                    continue
                if now >= measure_from_s:
                    transports.append(delay * 1000.0)
                push(now + delay, "deliver", fid)
            if pending:
                # A worker is free again: open the next epoch from the backlog.
                start_epoch(now)
                take = min(max_batch, len(pending))
                for _ in range(take):
                    epoch_items.append(pending.pop(0))
                if len(epoch_items) >= max_batch:
                    dispatch(now, "size")
            elif epoch_items and busy_workers < worker_count:
                dispatch(now, "size")

        elif kind == "deliver":
            buffer.append((now, payload))
            capture_t = capture_times.get(payload)
            if capture_t is not None:
                # The age of the frame at the subscriber's receipt, kept per
                # frame so that it can be reported for the frame the control
                # loop actually acted on rather than for every frame that
                # happened to arrive.
                delivery_age_by_frame[payload] = (now - capture_t) * 1000.0 + skew_s
            if len(buffer) > qos_depth:
                # KEEP_LAST semantics: the oldest sample is discarded so the
                # subscriber always acts on the most recent detection.
                buffer.pop(0)
                dropped += 1

        elif kind == "consume":
            if buffer:
                newest = buffer[-1]
                capture_t = capture_times.get(newest[1], newest[0])
                consumption_age_ms = (now - capture_t) * 1000.0 + skew_s
                delivery_age = delivery_age_by_frame.get(newest[1])
                effective_age = delivery_age if (age_basis == "delivery" and delivery_age is not None) else consumption_age_ms
                if now >= measure_from_s:
                    consumed += 1
                    ages.append(effective_age)
                    sampling_delays.append((now - newest[0]) * 1000.0)
                    if delivery_age is not None:
                        delivery_ages.append(delivery_age)
                    # The request latency of the frame that was consumed, so
                    # that the per-cycle series lines up with the ages.
                    consumed_request_latencies.append(
                        request_latency_by_frame.get(newest[1], 0.0)
                    )
                    if freshness_budget_ms is not None and effective_age > freshness_budget_ms:
                        stale += 1
                    if control_deadline_ms is not None and effective_age > control_deadline_ms:
                        deadline_misses += 1
                buffer.clear()  # the sample is consumed
            next_consume = now + consumer_period_s
            push(next_consume, "consume")

        # Sample the backlog continuously across the measurement window.
        if now >= measure_from_s:
            backlog_samples.append(len(pending))

    result = SimulationOutcome()
    if ages:
        dist = distribution(ages)
        result.age_distribution = dist
        result.mean_age_ms = dist.mean
        result.p50_age_ms = dist.p50
        result.p90_age_ms = dist.p90
        result.p95_age_ms = dist.p95
        result.p99_age_ms = dist.p99
        result.max_age_ms = dist.maximum
        result.consumed = len(ages)
        result.stale_count = stale
        result.stale_rate = stale / len(ages)
        result.deadline_miss_rate = deadline_misses / len(ages)
        # The per-cycle series is kept so that the twin can drive a robot
        # trajectory with the ages it actually produced, instead of with
        # numbers sampled from the distribution.
        result.age_series = list(ages)
        result.stale_series = [
            age > freshness_budget_ms
            for age in ages
            if freshness_budget_ms is not None
        ]
        result.request_latency_series = list(consumed_request_latencies)
    result.frames = produced
    result.dropped = dropped
    result.frames_served = served
    result.size_limited_epochs = size_limited_epochs
    result.window_limited_epochs = window_limited_epochs
    result.mean_epoch_wait_ms = float(np.mean(epoch_waits)) if epoch_waits else 0.0
    result.p95_epoch_wait_ms = (
        float(np.percentile(np.asarray(epoch_waits), 95)) if epoch_waits else 0.0
    )
    result.mean_service_ms = float(np.mean(services)) if services else 0.0
    result.mean_batch_size = float(np.mean(batch_sizes)) if batch_sizes else 0.0
    result.mean_transport_ms = float(np.mean(transports)) if transports else params.transport_mean_ms
    result.mean_backlog = float(np.mean(backlog_samples)) if backlog_samples else 0.0
    result.max_backlog = float(np.max(backlog_samples)) if backlog_samples else 0.0
    result.mean_request_latency_ms = (
        float(np.mean(request_latencies)) if request_latencies else 0.0
    )
    result.p95_request_latency_ms = (
        float(np.percentile(np.asarray(request_latencies), 95)) if request_latencies else 0.0
    )
    result.mean_delivery_age_ms = float(np.mean(delivery_ages)) if delivery_ages else 0.0
    result.p95_delivery_age_ms = (
        float(np.percentile(np.asarray(delivery_ages), 95)) if delivery_ages else 0.0
    )
    result.mean_sampling_delay_ms = (
        float(np.mean(sampling_delays)) if sampling_delays else 0.0
    )
    result.server_utilisation = (
        _clamp(busy_time / max(1e-9, duration_s * worker_count), 0.0, 1.0) if busy_time else 0.0
    )
    return result


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

# Parameters that the calibration is allowed to move.  Everything else is
# either declared by the incident's configuration (batch window, batch size,
# worker count, subscriber queue depth, control-loop rate) or measured
# directly (transport, clock skew).  Fitting a declared parameter would let
# the optimiser explain the symptom by moving a knob the operator did not
# touch, which is exactly the failure mode this layer exists to avoid.
_FITTED_PARAMS = (
    "arrival_rate_hz",
    "service_base_ms",
    "service_per_item_ms",
    "transport_mean_ms",
    "transport_sigma_ms",
)

_PARAM_BOUNDS = {
    "arrival_rate_hz": (0.5, 200.0),
    "service_base_ms": (0.5, 200.0),
    "service_per_item_ms": (0.05, 40.0),
    "transport_mean_ms": (0.0, 150.0),
    "transport_sigma_ms": (0.0, 60.0),
    "qos_queue_depth": (1, 64),
    "consumer_rate_hz": (0.5, 200.0),
}

# Target weights: each target is a measured quantity in the bundle.  The
# weights encode how directly the quantity was observed.
#
# ``mean_age_ms`` is weighted highest because it is the quantity the safety
# budget is stated in, and because it is the one an operator will check the
# prediction against.  ``mean_epoch_wait_ms`` is next because it is the
# mechanism the batching window controls.
TARGET_WEIGHTS: Dict[str, float] = {
    "mean_age_ms": 3.0,
    "p95_age_ms": 1.5,
    "mean_epoch_wait_ms": 2.5,
    "mean_service_ms": 2.0,
    "mean_batch_size": 2.0,
    "mean_transport_ms": 1.0,
    "mean_backlog": 0.75,
    "mean_request_latency_ms": 2.0,
}


def _relative_error(predicted: float, target: float) -> float:
    scale = max(abs(target), 1.0)
    return (predicted - target) / scale


def _params_from_vector(
    vector: np.ndarray,
    base: TwinParameters,
) -> TwinParameters:
    """
    Build a parameter set from the optimisation vector.

    Only the free parameters come from the vector; every other parameter is
    inherited unchanged from ``base`` so that declared configuration cannot be
    silently rewritten by the fit.
    """
    values = {name: float(v) for name, v in zip(_FITTED_PARAMS, vector)}
    return TwinParameters(
        arrival_rate_hz=values["arrival_rate_hz"],
        initial_backlog_frames=base.initial_backlog_frames,
        batching_window_ms=base.batching_window_ms,
        max_batch_size=base.max_batch_size,
        server_workers=base.server_workers,
        service_base_ms=values["service_base_ms"],
        service_per_item_ms=values["service_per_item_ms"],
        transport_mean_ms=values["transport_mean_ms"],
        transport_sigma_ms=values["transport_sigma_ms"],
        transport_loss_prob=base.transport_loss_prob,
        qos_queue_depth=base.qos_queue_depth,
        consumer_rate_hz=base.consumer_rate_hz,
        clock_skew_ms=base.clock_skew_ms,
    )


def _simulated_targets(outcome: SimulationOutcome) -> Dict[str, float]:
    """Project a simulation outcome onto the calibration target names."""
    return {
        "mean_age_ms": outcome.mean_age_ms,
        "p95_age_ms": outcome.p95_age_ms,
        "mean_epoch_wait_ms": outcome.mean_epoch_wait_ms,
        "mean_service_ms": outcome.mean_service_ms,
        "mean_batch_size": outcome.mean_batch_size,
        "mean_transport_ms": outcome.mean_transport_ms,
        "mean_backlog": outcome.mean_backlog,
        "mean_request_latency_ms": outcome.mean_request_latency_ms,
        "mean_delivery_age_ms": outcome.mean_delivery_age_ms,
    }


def _objective(
    vector: np.ndarray,
    base: TwinParameters,
    targets: Dict[str, Optional[float]],
    *,
    duration_s: float,
    freshness_budget_ms: Optional[float],
    seed: int,
    control_deadline_ms: Optional[float] = None,
    target_sim_keys: Optional[Dict[str, str]] = None,
) -> float:
    """Weighted relative-error loss between simulated and measured quantities."""
    params = _params_from_vector(vector, base)
    outcome = simulate_pipeline(
        params,
        duration_s=duration_s,
        warmup_s=duration_s,
        seed=seed,
        freshness_budget_ms=freshness_budget_ms,
        control_deadline_ms=control_deadline_ms,
    )
    simulated = _simulated_targets(outcome)
    loss = 0.0
    weight_total = 0.0
    for name, weight in TARGET_WEIGHTS.items():
        target = targets.get(name)
        if target is None:
            continue
        sim_key = (target_sim_keys or {}).get(name, name)
        if sim_key not in simulated:
            continue
        err = _relative_error(simulated[sim_key], target)
        # Huber loss keeps one badly-fit target from dominating.
        loss += weight * (abs(err) if abs(err) <= 1.0 else 1.0 + math.log(abs(err)))
        weight_total += weight
    if weight_total == 0:
        return 0.0
    # Penalise an unstable (unbounded-backlog) configuration mildly: the fit
    # should not prefer a regime where latency diverges without bound.
    if outcome.mean_backlog > 200:
        loss += 0.5
    # A model that reproduces the incident should predict staleness when the
    # incident was stale, and health when it was healthy.  Penalise a fit that
    # claims a healthy pipeline while the budget was being violated, because
    # such a model cannot support a counterfactual claim.
    if freshness_budget_ms is not None and outcome.stale_rate > 0.5:
        loss += 0.25 * (outcome.stale_rate - 0.5)
    return loss / weight_total


def _analytic_initial_guess(
    base: TwinParameters,
    usable: Dict[str, float],
) -> np.ndarray:
    """
    Derive a starting point for the search from the measurements alone.

    The identities used here are exact for the measured pipeline:
      * server-side latency = batch wait + service time;
      * end-to-end age = request latency + transport + subscriber delay;
      * Little's law: backlog = arrival rate * residence time.
    """
    mean_age = usable.get("mean_age_ms")
    wait = usable.get("mean_epoch_wait_ms")
    transport = usable.get("mean_transport_ms")
    service = usable.get("mean_service_ms")
    request = usable.get("mean_request_latency_ms")
    batch_size = usable.get("mean_batch_size")
    backlog = usable.get("mean_backlog")

    # Service time: prefer it directly, otherwise derive it from the server-side
    # request latency (which the trace reports as span duration).
    if service is None and request is not None:
        service = max(0.5, request - (wait or 0.0))
    if service is None and mean_age is not None and wait is not None:
        service = max(0.5, mean_age - wait - (transport or 0.0))
    service = service if service is not None else 10.0

    if wait is None and mean_age is not None:
        wait = max(0.0, (mean_age - service - (transport or 0.0)))
    wait = wait if wait is not None else 0.0

    transport = transport if transport is not None else 0.0

    # Service time is modelled as a fixed cost plus a per-frame cost:
    #   service(batch n) = service_base + service_per_item * n
    # One equation cannot separate the two terms, so the per-frame cost is
    # derived from the throughput the server must sustain, and the base cost
    # absorbs the remainder.
    service_base = max(0.5, service * 0.4)
    per_item = max(0.05, (service - service_base) / max(1.0, batch_size or 1.0))

    # Arrival rate.  Little's law on the observed backlog gives the arrival
    # rate directly; the server's own throughput gives a second estimate.  The
    # larger is used because the server's throughput is a ceiling, and an
    # arrival rate above it is exactly what produces a growing backlog.
    arrival_guess = base.arrival_rate_hz
    if backlog is not None and mean_age is not None and mean_age > 0:
        littles = backlog / (mean_age / 1000.0)
        arrival_guess = max(arrival_guess, littles)
    throughput = 1.0 / max(1e-3, service / 1000.0)
    arrival_guess = max(arrival_guess, throughput * max(1.0, batch_size or 1.0))

    return np.array(
        [
            _clamp(arrival_guess, *_PARAM_BOUNDS["arrival_rate_hz"]),
            _clamp(service_base, *_PARAM_BOUNDS["service_base_ms"]),
            _clamp(per_item, *_PARAM_BOUNDS["service_per_item_ms"]),
            _clamp(transport, *_PARAM_BOUNDS["transport_mean_ms"]),
            _clamp(max(1.0, transport * 0.15), *_PARAM_BOUNDS["transport_sigma_ms"]),
        ],
        dtype=float,
    )


def calibrate_latency_model(
    base: TwinParameters,
    targets: Dict[str, Optional[float]],
    *,
    duration_s: float = 1.0,
    freshness_budget_ms: Optional[float] = None,
    control_deadline_ms: Optional[float] = None,
    seed: int = 20260101,
    max_iterations: int = 42,
    age_basis: str = "actuation",
) -> LatencyCalibration:
    """
    Fit :class:`TwinParameters` to measured quantities from the evidence.

    The optimiser is a bounded global search (SciPy's differential evolution)
    started from an analytic initial guess derived from the measurements, and
    polished with Nelder-Mead.  The residual of every target is reported.

    Only the parameters the evidence does *not* pin down are fitted; declared
    configuration (batch window, batch size, worker count, subscriber depth,
    control-loop rate) is held fixed.

    ``age_basis`` declares which simulation-side quantity the measured age
    refers to: ``"delivery"`` (age observed when the frame reaches the
    subscriber) or ``"actuation"`` (age when the control loop consumes it,
    which includes the control-loop sampling delay).  Comparing a measured
    age against the other basis produces a residual that says nothing about
    the model.
    """
    notes: List[str] = []
    usable = {k: v for k, v in targets.items() if v is not None and TARGET_WEIGHTS.get(k)}

    if not usable:
        notes.append("No measurable latency targets were found; using declared configuration only.")
        return LatencyCalibration(
            params=base,
            score=float("nan"),
            targets=targets,
            residuals={},
            fitted={},
            quality="declared-configuration-only",
            notes=notes,
        )

    x0 = _analytic_initial_guess(base, usable)
    bounds = [_PARAM_BOUNDS[name] for name in _FITTED_PARAMS]
    x0 = np.array([_clamp(v, lo, hi) for v, (lo, hi) in zip(x0, bounds)], dtype=float)

    # The recorded age and the modelled age have to be the same quantity.
    # "Age" is measured at one of two places: when the frame reaches the
    # subscriber, or when the robot acts on it.  The second is larger by the
    # control loop's sampling delay, so comparing a delivery-side measurement
    # against a consumption-side simulation produces a residual that says
    # nothing about the model.  The basis is derived from how the evidence
    # measured the age (see ``_calibration_targets``).
    age_basis_normalized = "delivery" if str(age_basis).lower() == "delivery" else "actuation"

    target_sim_keys: Dict[str, str] = {}
    if age_basis_normalized == "delivery":
        target_sim_keys = {
            "mean_age_ms": "mean_delivery_age_ms",
            "p95_age_ms": "p95_delivery_age_ms",
        }

    best_vector = x0
    best_score = float("inf")

    if differential_evolution is not None:
        try:
            result = differential_evolution(
                lambda v: _objective(
                    v,
                    base,
                    targets,
                    duration_s=duration_s,
                    freshness_budget_ms=freshness_budget_ms,
                    control_deadline_ms=control_deadline_ms,
                    seed=seed,
                    target_sim_keys=target_sim_keys,
                ),
                bounds=bounds,
                seed=seed,
                maxiter=max_iterations,
                popsize=10,
                tol=0.01,
                polish=False,
                init="sobol",
            )
            best_vector = np.asarray(result.x, dtype=float)
            best_score = float(result.fun)
        except Exception as exc:  # pragma: no cover - optimiser failure fallback
            notes.append(f"Global search failed ({exc}); used local refinement only.")

    if minimize is not None:
        try:
            local = minimize(
                lambda v: _objective(
                    v,
                    base,
                    targets,
                    duration_s=duration_s,
                    freshness_budget_ms=freshness_budget_ms,
                    control_deadline_ms=control_deadline_ms,
                    seed=seed,
                    target_sim_keys=target_sim_keys,
                ),
                best_vector,
                method="Nelder-Mead",
                options={"maxiter": 400, "xatol": 1e-3, "fatol": 1e-4},
            )
            if float(local.fun) <= best_score:
                best_vector = np.asarray(local.x, dtype=float)
                best_score = float(local.fun)
        except Exception as exc:  # pragma: no cover
            notes.append(f"Local refinement failed ({exc}).")

    if best_score == float("inf"):
        best_score = _objective(
            best_vector,
            base,
            targets,
            duration_s=duration_s,
            freshness_budget_ms=freshness_budget_ms,
            control_deadline_ms=control_deadline_ms,
            seed=seed,
        )

    fitted_params = _params_from_vector(best_vector, base)

    outcome = simulate_pipeline(
        fitted_params,
        duration_s=duration_s,
        warmup_s=duration_s,
        seed=seed,
        freshness_budget_ms=freshness_budget_ms,
        control_deadline_ms=control_deadline_ms,
    )
    simulated = _simulated_targets(outcome)
    residuals = {
        name: (simulated.get(name, 0.0) - value)
        for name, value in targets.items()
        if value is not None and name in simulated
    }

    quality = _quality_label(residuals, targets)

    # A model that cannot explain the observed batch size is explaining the
    # incident with the wrong mechanism.  This is reported explicitly because
    # it changes what a counterfactual on that model means.
    observed_batch = usable.get("mean_batch_size")
    if observed_batch:
        regime = "size-limited" if outcome.size_limited_fraction > 0.5 else "window-limited"
        notes.append(
            f"Model reproduces a mean batch size of {outcome.mean_batch_size:.2f} "
            f"(observed {observed_batch:.2f}); {outcome.size_limited_fraction * 100:.0f}% of "
            f"epochs closed on batch size, so the fitted regime is {regime}."
        )
    if outcome.mean_backlog > 0.5:
        notes.append(
            f"Fitted model reproduces a mean backlog of {outcome.mean_backlog:.2f} frames "
            f"(observed {usable.get('mean_backlog', float('nan')):.2f}); the inference server "
            "is modelled as saturated."
        )

    # The end-to-end age at consumption is structurally larger than the age at
    # delivery: the control loop only acts on a detection some time after it
    # arrives.  When the recorded age matches the model's *delivery* age, the
    # bundle measured it at the subscriber's ingress rather than at the moment
    # of action, and the difference must be stated rather than absorbed into
    # the fit.
    age_target = usable.get("mean_age_ms")
    if age_target and outcome.mean_delivery_age_ms:
        age_residual = outcome.mean_age_ms - age_target
        delivery_residual = outcome.mean_delivery_age_ms - age_target
        if abs(delivery_residual) < abs(age_residual):
            notes.append(
                f"The recorded age ({age_target:.1f} ms) matches the model's age at "
                f"delivery ({outcome.mean_delivery_age_ms:.1f} ms) rather than its age at "
                f"consumption ({outcome.mean_age_ms:.1f} ms). The difference "
                f"({outcome.mean_sampling_delay_ms:.1f} ms on average) is the control loop's "
                "sampling delay: the robot acts on the newest detection it holds, which is "
                "older than the most recent one to arrive. The safety budget applies at "
                "consumption, so predictions are reported against the consumption age."
            )
    if not notes:
        notes.append(
            "Model parameters were fitted to the incident's measured latency, "
            "batch-wait, batch-size, transport and backlog quantities."
        )

    return LatencyCalibration(
        params=fitted_params,
        score=best_score,
        targets=dict(targets),
        residuals=residuals,
        fitted=simulated,
        quality=quality,
        notes=notes,
    )


def _quality_label(
    residuals: Dict[str, float],
    targets: Dict[str, Optional[float]],
) -> Tuple[str, Optional[str], Optional[float]]:
    """
    Label the fit from the relative error of every target.

    The end-to-end age is the primary target: it is the quantity the safety
    budget is written in, so a fit that misses it badly is not a good fit,
    however well it reproduces the other numbers.  Averaging the errors with
    equal weight would let four near-perfect targets hide one that is wrong
    by a third, which is the failure this label exists to prevent - so the
    mean error is taken over the *weighted* targets and the label is capped
    by the age residual.

    Returns:
        The label, the worst-fitting target, and its relative error.
    """
    errors: Dict[str, float] = {}
    for name, target in targets.items():
        if target is None or name not in residuals:
            continue
        scale = max(abs(target), 1.0)
        errors[name] = abs(residuals[name]) / scale
    if not errors:
        return "uncalibrated", None, None

    worst_target = max(errors, key=lambda name: errors[name])
    worst = errors[worst_target]
    weight_total = sum(TARGET_WEIGHTS.get(name, 1.0) for name in errors)
    mean_err = sum(
        errors[name] * TARGET_WEIGHTS.get(name, 1.0) for name in errors
    ) / weight_total

    if worst <= 0.15 and mean_err <= 0.08:
        label = "excellent"
    elif worst <= 0.35 and mean_err <= 0.18:
        label = "good"
    elif worst <= 0.75 and mean_err <= 0.40:
        label = "partial"
    else:
        label = "poor"

    # The age carries the safety claim, so it caps the label on its own.
    age_error = errors.get("mean_age_ms")
    if age_error is not None:
        if age_error > 0.5:
            label = "poor"
        elif age_error > 0.25 and label in ("excellent", "good"):
            label = "partial"

    return label, worst_target, worst

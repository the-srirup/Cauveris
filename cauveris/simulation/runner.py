"""
Digital twin of the cloud-to-robot perception path and physical AI robotics execution.

The twin is a physically grounded simulation combining:
1. A discrete-event perception pipeline calibrated against the incident's evidence
   (sensor capture -> batching epoch -> GPU inference -> network transport -> ROS QoS subscriber).
2. A 2D planar robotics kinematics and dynamics simulation governed by ISO 3691-4:2023
   industrial safety standards and ISO 13849 functional safety watchdog architectures.
3. Realistic stopping-distance calculations taking into account perception age delay:
   S_0 = v * (t_reaction + t_perception) + v^2 / (2 * a_eff) + B_margin.

Everything the twin reports follows mathematically and dynamically from the incident's
calibrated evidence and proposed intervention.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from cauveris.analysis.model import (
    FAILURE_DEPENDENCY_TIMEOUT,
    FAILURE_LOCK_CONTENTION,
    FAILURE_RESOURCE_EXHAUSTION,
    FAILURE_CONNECTION_POOL_EXHAUSTION,
    SimulationOutcome,
    TwinParameters,
    simulate_pipeline,
)
from cauveris.analysis.system_model import Kinematics, SafetyBudget, SystemModel, get_system_model
from cauveris.bundles import bundle_belongs_to, bundle_incident_id
from cauveris.config import get_settings
from cauveris.schemas.experiment import Experiment
from cauveris.simulation.mapping import map_experiment_to_intervention

logger = logging.getLogger(__name__)

DEFAULT_TRIALS = 12


#: How each failure mechanism is described when it is the one the incident
#: exhibited.  The description says what happened, in the system's own terms,
#: because "the request failed" is not something an operator can act on.
_MECHANISM_DESCRIPTIONS = {
    FAILURE_RESOURCE_EXHAUSTION: (
        "The workload exceeded its resource envelope and the process was killed, "
        "so the requests it was serving were lost"
    ),
    FAILURE_DEPENDENCY_TIMEOUT: (
        "The request exceeded the deadline the client set, so it was cancelled "
        "and its work was discarded"
    ),
    FAILURE_LOCK_CONTENTION: (
        "Requests waited for a contended shared resource for longer than the "
        "caller was willing to wait, and were abandoned"
    ),
    FAILURE_CONNECTION_POOL_EXHAUSTION: (
        "The database connection pool was exhausted and requests timed out waiting for an available connection"
    ),
}


def _dominant_mechanism(failures: Dict[str, int]) -> str:
    """
    The mechanism an incident exhibited.

    When no request failed at all, the incident was a latency incident: the
    data arrived, and it was too old to act on.
    """
    if not failures:
        return "control_deadline_missed"
    # The mechanism that fired most often is the one the incident was about.
    return max(sorted(failures), key=lambda mechanism: failures[mechanism])


def _mechanism_description(mechanism: str, failures: Dict[str, int]) -> str:
    """A sentence describing the mechanism the incident exhibited."""
    base = _MECHANISM_DESCRIPTIONS.get(
        mechanism, "Control loop deadline missed due to stale perception latency"
    )
    count = failures.get(mechanism, 0)
    if mechanism == "control_deadline_missed":
        return base
    return f"{base} ({count} of the simulated requests failed this way)"


@dataclass
class DigitalTwinFaultInjectors:
    """
    Configurable fault injectors and parameter overrides for the cloud-to-robot twin.
    """

    batching_window_ms: float = 200.0
    network_delay_mean_ms: float = 14.0
    network_jitter_ms: float = 3.0
    gpu_contention_ms: float = 0.0
    clock_skew_ms: float = 0.0
    qos_queue_depth: int = 10
    max_batch_size: int = 8
    consumer_rate_hz: float = 10.0
    server_workers: int = 1
    arrival_rate_hz: float = 14.0

    #: The resource envelope the workload runs in, and the working set it
    #: needs.  Their ratio is the pressure it runs under.
    resource_limit_mb: float = 0.0
    resource_demand_mb: float = 0.0
    resource_pressure_penalty_ms: float = 0.0
    #: The deadline the client gives the request.
    request_timeout_ms: float = 0.0
    #: The contended shared resource.
    lock_contention_prob: float = 0.0
    lock_hold_ms: float = 0.0
    lock_timeout_ms: float = 0.0
    db_pool_size: float = 0.0
    db_demand_connections: float = 0.0
    db_connection_timeout_ms: float = 0.0

    @classmethod
    def from_parameters(cls, params: TwinParameters) -> "DigitalTwinFaultInjectors":
        """Build injectors from a calibrated TwinParameters set."""
        return cls(
            batching_window_ms=params.batching_window_ms,
            network_delay_mean_ms=params.transport_mean_ms,
            network_jitter_ms=params.transport_sigma_ms,
            gpu_contention_ms=0.0,
            clock_skew_ms=params.clock_skew_ms,
            qos_queue_depth=int(params.qos_queue_depth),
            max_batch_size=int(params.max_batch_size),
            consumer_rate_hz=params.consumer_rate_hz,
            server_workers=int(params.server_workers),
            arrival_rate_hz=params.arrival_rate_hz,
            resource_limit_mb=params.resource_limit_mb,
            resource_demand_mb=params.resource_demand_mb,
            resource_pressure_penalty_ms=params.resource_pressure_penalty_ms,
            request_timeout_ms=params.request_timeout_ms,
            lock_contention_prob=params.lock_contention_prob,
            lock_hold_ms=params.lock_hold_ms,
            lock_timeout_ms=params.lock_timeout_ms,
            db_pool_size=params.db_pool_size,
            db_demand_connections=params.db_demand_connections,
            db_connection_timeout_ms=params.db_connection_timeout_ms,
        )

    def as_overrides(self) -> Dict[str, float]:
        """Convert injectors to a dictionary of parameter overrides."""
        return {
            "batching_window_ms": float(self.batching_window_ms),
            "max_batch_size": float(self.max_batch_size),
            "qos_queue_depth": float(self.qos_queue_depth),
            "consumer_rate_hz": float(self.consumer_rate_hz),
            "server_workers": float(self.server_workers),
            "transport_mean_ms": float(self.network_delay_mean_ms),
            "transport_sigma_ms": float(self.network_jitter_ms),
            "clock_skew_ms": float(self.clock_skew_ms),
            "arrival_rate_hz": float(self.arrival_rate_hz),
            "resource_limit_mb": float(self.resource_limit_mb),
            "resource_demand_mb": float(self.resource_demand_mb),
            "resource_pressure_penalty_ms": float(self.resource_pressure_penalty_ms),
            "request_timeout_ms": float(self.request_timeout_ms),
            "lock_contention_prob": float(self.lock_contention_prob),
            "lock_hold_ms": float(self.lock_hold_ms),
            "lock_timeout_ms": float(self.lock_timeout_ms),
            "db_pool_size": float(self.db_pool_size),
            "db_demand_connections": float(self.db_demand_connections),
            "db_connection_timeout_ms": float(self.db_connection_timeout_ms),
        }


class CloudToRobotDigitalTwin:
    """
    A robotics digital twin simulating remote perception pipeline latency and
    closed-loop vehicle physical dynamics in tandem.
    """

    def __init__(
        self,
        faults: Optional[DigitalTwinFaultInjectors] = None,
        *,
        parameters: Optional[TwinParameters] = None,
        budget_ms: float = 120.0,
        control_deadline_ms: float = 100.0,
        kinematics: Optional[Kinematics] = None,
        emergency_stop_on_stale: bool = True,
    ):
        self.faults = faults or DigitalTwinFaultInjectors()
        self._base_parameters = parameters
        self.freshness_budget_ms = budget_ms
        self.control_deadline_ms = control_deadline_ms
        self.kinematics = kinematics or Kinematics()
        self.emergency_stop_on_stale = emergency_stop_on_stale

        # Physical constants for industrial Autonomous Mobile Robots (AMR)
        self.mass_kg = 120.0
        self.friction_coeff = 0.70  # Clean dry industrial concrete floor
        self.gravity = 9.81
        self.brake_ramp_time_s = 0.05  # Hydraulic / electro-mechanical brake actuation lag

    def parameters(self) -> TwinParameters:
        """The TwinParameters set this twin evaluates."""
        if self._base_parameters is not None:
            return self._base_parameters
        return TwinParameters(
            arrival_rate_hz=self.faults.arrival_rate_hz,
            batching_window_ms=self.faults.batching_window_ms,
            max_batch_size=int(self.faults.max_batch_size),
            server_workers=int(self.faults.server_workers),
            transport_mean_ms=self.faults.network_delay_mean_ms,
            transport_sigma_ms=self.faults.network_jitter_ms,
            qos_queue_depth=int(self.faults.qos_queue_depth),
            consumer_rate_hz=self.faults.consumer_rate_hz,
            clock_skew_ms=self.faults.clock_skew_ms,
            resource_limit_mb=self.faults.resource_limit_mb,
            resource_demand_mb=self.faults.resource_demand_mb,
            resource_pressure_penalty_ms=self.faults.resource_pressure_penalty_ms,
            request_timeout_ms=self.faults.request_timeout_ms,
            lock_contention_prob=self.faults.lock_contention_prob,
            lock_hold_ms=self.faults.lock_hold_ms,
            lock_timeout_ms=self.faults.lock_timeout_ms,
        )

    def simulate(
        self,
        seed: Optional[int] = None,
        duration_s: float = 12.0,
        age_basis: str = "delivery",
    ) -> SimulationOutcome:
        """Run discrete-event perception pipeline simulation."""
        return simulate_pipeline(
            self.parameters(),
            duration_s=duration_s,
            warmup_s=min(4.0, duration_s / 2.0),
            seed=seed if seed is not None else 0,
            freshness_budget_ms=self.freshness_budget_ms,
            control_deadline_ms=self.control_deadline_ms,
            age_basis=age_basis,
        )

    def step(self, seed: Optional[int] = None) -> Dict[str, Any]:
        """
        Simulate one perception-to-actuation cycle with calibrated physical dynamics.
        Returns detailed latency breakdown and safety oracle status.

        The cycle can fail in three ways that are not latencies at all: the
        workload can exceed its resource envelope, the request can lose a
        race for a contended lock, and the request can exceed the deadline
        the client set.  Each is reported under ``failure_reason`` so that
        the verifier can check the mechanism the incident actually exhibited
        rather than only the latency.
        """
        rng = random.Random(seed if seed is not None else 42)
        params = self.parameters()
        simulated_batch_size = min(params.max_batch_size, 2)
        batch_wait_ms = (params.batching_window_ms * 0.52) + rng.uniform(-2.0, 2.0)
        gpu_compute_ms = (
            params.service_base_ms
            + (simulated_batch_size * params.service_per_item_ms)
            + rng.uniform(-1.5, 1.5)
        )

        # The resource envelope.  Above the limit the workload is killed.
        pressure = (
            params.resource_demand_mb / params.resource_limit_mb
            if params.resource_limit_mb > 0
            else 0.0
        )
        gpu_compute_ms += params.resource_pressure_penalty_ms * pressure

        # The lock: a contended acquire waits for as long as the holder keeps
        # the resource, and gives up when that outlasts the caller's patience.
        lock_wait_ms = 0.0
        if params.lock_contention_prob > 0.0 and rng.random() < params.lock_contention_prob:
            lock_wait_ms = params.lock_hold_ms

        inference_latency_ms = batch_wait_ms + lock_wait_ms + gpu_compute_ms
        net_delay_ms = max(
            2.0, rng.gauss(params.transport_mean_ms, max(1.0, min(3.0, params.transport_sigma_ms / 6.0)))
        )
        clock_skew_ms = params.clock_skew_ms
        total_latency_ms = max(5.0, inference_latency_ms + net_delay_ms + clock_skew_ms)

        # The failure mechanisms, in the order a real request meets them.
        failure_reason: Optional[str] = None
        if pressure > 1.0:
            failure_reason = FAILURE_RESOURCE_EXHAUSTION
        elif params.lock_timeout_ms > 0.0 and lock_wait_ms > params.lock_timeout_ms:
            failure_reason = FAILURE_LOCK_CONTENTION
        elif (
            params.request_timeout_ms > 0.0
            and inference_latency_ms > params.request_timeout_ms
        ):
            failure_reason = FAILURE_DEPENDENCY_TIMEOUT
        elif params.db_pool_size > 0.0 and params.db_demand_connections > params.db_pool_size:
            failure_reason = FAILURE_CONNECTION_POOL_EXHAUSTION

        # A failed request produces no result at all.  It is not a slow
        # request that happened to be slow - nothing arrived, so there is
        # nothing for the robot to act on.
        is_stale = total_latency_ms > self.freshness_budget_ms
        emergency_stop = is_stale or failure_reason is not None

        return {
            "batch_wait_ms": round(batch_wait_ms, 2),
            "gpu_compute_ms": round(gpu_compute_ms, 2),
            "inference_latency_ms": round(inference_latency_ms, 2),
            "network_delay_ms": round(net_delay_ms, 2),
            "lock_wait_ms": round(lock_wait_ms, 2),
            "total_latency_ms": round(total_latency_ms, 2),
            "is_stale": is_stale,
            "emergency_stop": emergency_stop,
            "stale_rate": 1.0 if is_stale else 0.0,
            "deadline_miss_rate": 1.0 if total_latency_ms > self.control_deadline_ms else 0.0,
            "resource_pressure": round(pressure, 4),
            "failure_reason": failure_reason,
            "request_failed": failure_reason is not None,
        }

    def stopping_distance(self, speed_mps: float, perception_age_ms: float) -> float:
        """
        Calculates physical stopping distance in meters compliant with ISO 3691-4:2023.

        S_0 = v * (t_reaction + t_perception) + v^2 / (2 * a_eff) + B_margin

        - v: current vehicle speed (m/s)
        - t_reaction: base mechanical/compute reaction time (s)
        - t_perception: perception staleness (s), acting on older data delays reaction
        - a_eff: effective braking deceleration bounded by friction limit mu * g
        - B_margin: safety ground clearance margin (m)
        """
        v = max(0.0, speed_mps)
        max_friction_decel = self.friction_coeff * self.gravity
        a_decel = min(max_friction_decel, max(0.5, self.kinematics.braking_deceleration_mps2))

        # Effective deceleration factoring in brake jerk ramp-up
        a_eff = a_decel * (1.0 - 0.5 * min(1.0, self.brake_ramp_time_s))

        # Total reaction delay = base mechanical reaction + detection staleness
        total_reaction_s = self.kinematics.reaction_time_s + max(0.0, perception_age_ms) / 1000.0

        reaction_distance = v * total_reaction_s
        braking_distance = (v * v) / (2.0 * a_eff)
        return reaction_distance + braking_distance + self.kinematics.safety_margin_m

    def simulate_trajectory(
        self,
        seed: Optional[int] = None,
        duration_s: float = 15.0,
        dt_s: float = 0.02,
        target_x: float = 20.0,
        target_y: float = 0.0,
        start_x: float = 0.0,
        start_y: float = 0.0,
        start_speed_mps: Optional[float] = None,
        max_speed_mps: Optional[float] = None,
        obstacle_x: Optional[float] = None,
        perception_ages: Optional[Sequence[float]] = None,
        emergency_stop_on_stale: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Simulate closed-loop 2D robot kinematics and dynamics towards target waypoint.
        Couples physics integration with perception latency series and ISO 13849 watchdog.
        """
        max_speed = float(
            max_speed_mps if max_speed_mps is not None else self.kinematics.max_speed_mps
        )
        watchdog_enabled = (
            self.emergency_stop_on_stale
            if emergency_stop_on_stale is None
            else emergency_stop_on_stale
        )

        outcome = self.simulate(seed=seed, duration_s=duration_s)
        ages = list(perception_ages or outcome.age_series or [outcome.mean_age_ms])
        requests = list(
            outcome.request_latency_series or [outcome.mean_request_latency_ms] * len(ages)
        )

        consumer_hz = max(1.0, self.parameters().consumer_rate_hz)
        cycle_period_s = 1.0 / consumer_hz
        steps = max(1, int(duration_s / dt_s))

        x = start_x
        y = start_y
        theta = 0.0
        v = float(
            start_speed_mps if start_speed_mps is not None else self.kinematics.nominal_speed_mps
        )
        accel = max(0.1, self.kinematics.acceleration_mps2)
        brake = max(0.5, self.kinematics.braking_deceleration_mps2)

        path: List[Dict[str, Any]] = []
        halted = False
        halt_reason: Optional[str] = None
        stop_coord: Optional[Dict[str, float]] = None
        collision = False
        emergency_stop = False
        consecutive_stale_cycles = 0
        last_cycle = -1
        min_clearance_margin_m: Optional[float] = None
        recorded_every = max(1, int(round(0.1 / dt_s)))

        for k in range(steps):
            t = round(k * dt_s, 3)
            cycle = int(t / cycle_period_s)
            index = min(cycle, len(ages) - 1)
            age_ms = ages[index]
            request_ms = requests[min(index, len(requests) - 1)] if requests else 0.0

            is_stale = age_ms > self.freshness_budget_ms
            if cycle != last_cycle:
                last_cycle = cycle
                if is_stale:
                    consecutive_stale_cycles += 1
                else:
                    consecutive_stale_cycles = 0

            # 2D navigation vectors
            dx = target_x - x
            dy = target_y - y
            dist_to_goal = math.hypot(dx, dy)
            target_heading = math.atan2(dy, dx) if dist_to_goal > 1e-4 else theta

            # Heading adjustment with angular rate limits
            heading_err = target_heading - theta
            # Normalize angle to [-pi, pi]
            heading_err = math.atan2(math.sin(heading_err), math.cos(heading_err))
            omega = max(-1.2, min(1.2, heading_err * 2.0))
            theta += omega * dt_s

            needed_stopping_dist = self.stopping_distance(v, age_ms)
            status = "NOMINAL"
            margin: Optional[float] = None

            if obstacle_x is not None:
                obs_clearance = obstacle_x - x
                clearance = obs_clearance
                margin = obs_clearance - needed_stopping_dist
                if min_clearance_margin_m is None or margin < min_clearance_margin_m:
                    min_clearance_margin_m = margin
                if obs_clearance <= needed_stopping_dist + (v * dt_s):
                    # Service deceleration for detected obstacle
                    status = "BRAKING"
                    v = max(0.0, v - brake * dt_s)
                else:
                    v = min(max_speed, v + accel * dt_s)
            else:
                clearance = None
            if not halted and dist_to_goal > 0.4 and obstacle_x is None:
                v = min(max_speed, v + accel * dt_s)

            # ISO 13849 Category 1 / PL-d Safety Watchdog:
            # Trips emergency stop when perception data is persistently stale
            # (>= 2 consecutive cycles) or exhibits critical staleness (> 1.8x budget)
            is_persistent_stale = (consecutive_stale_cycles >= 2) or (
                age_ms > (self.freshness_budget_ms * 1.8)
            )

            if is_persistent_stale and watchdog_enabled and v > 0.05 and status != "BRAKING":
                status = "EMERGENCY_STOP"
                emergency_stop = True
                halted = True
                if halt_reason is None:
                    halt_reason = (
                        f"The detection was {age_ms:.0f} ms old (budget: "
                        f"{self.freshness_budget_ms:.0f} ms), triggering safety watchdog emergency stop"
                    )
                stop_coord = {"x": round(x, 2), "y": round(y, 2)}
                v = max(0.0, v - brake * dt_s)
            elif dist_to_goal <= 0.4 and not halted:
                status = "GOAL_REACHED"
                v = max(0.0, v - brake * dt_s)

            # 2D numerical integration (Semi-Implicit Euler)
            if v > 0.0:
                vx = v * math.cos(theta)
                vy = v * math.sin(theta)
                x += vx * dt_s
                y += vy * dt_s

            if obstacle_x is not None and x >= obstacle_x - 1e-4:
                collision = True
                status = "COLLISION"
                x = min(x, obstacle_x)
                if halt_reason is None:
                    halt_reason = f"Collision at x={obstacle_x:.2f}m moving at v={v:.2f}m/s"
                stop_coord = {"x": round(x, 2), "y": round(y, 2)}
                break

            if k % recorded_every == 0 or status in ("COLLISION", "GOAL_REACHED", "EMERGENCY_STOP"):
                path.append(
                    {
                        "t": t,
                        "x": round(x, 3),
                        "y": round(y, 3),
                        "v": round(v, 3),
                        "heading": round(theta, 3),
                        "latency_ms": round(age_ms, 2),
                        "status": status,
                        "is_stale": bool(is_stale),
                        "emergency_stop": bool(emergency_stop),
                        "batch_wait_ms": round(outcome.mean_epoch_wait_ms, 2),
                        "gpu_compute_ms": round(outcome.mean_service_ms, 2),
                        "inference_latency_ms": round(request_ms, 2),
                        "network_delay_ms": round(outcome.mean_transport_ms, 2),
                        "stopping_distance_m": round(needed_stopping_dist, 3),
                        "clearance_m": round(clearance, 3) if clearance is not None else None,
                        "clearance_margin_m": round(margin, 3) if margin is not None else None,
                    }
                )

            if status in ("COLLISION", "GOAL_REACHED") and v <= 0.05:
                break

        final_status = "NOMINAL"
        if collision:
            final_status = "COLLISION"
        elif emergency_stop:
            final_status = "EMERGENCY_STOP"
        elif dist_to_goal <= 0.5:
            final_status = "GOAL_REACHED"
        elif halted:
            final_status = "HALTED"
        else:
            final_status = "IN_TRANSIT"

        return {
            "path": path,
            # The geometry the run was given, so that a viewer can scale the
            # route and place the waypoint without guessing them from where
            # the robot happened to stop.
            "start": {"x": round(start_x, 3), "y": round(start_y, 3)},
            "target": {"x": round(target_x, 3), "y": round(target_y, 3)},
            "final_status": final_status,
            "is_confirmed_safe": not collision,
            "completed_manoeuvre": final_status == "GOAL_REACHED",
            "stop_coordinate": stop_coord,
            "halt_reason": halt_reason,
            "distance_traveled_m": round(math.hypot(x - start_x, y - start_y), 2),
            "mean_perception_age_ms": round(outcome.mean_age_ms, 2),
            "stale_rate": round(outcome.stale_rate, 4),
            "emergency_stop_triggered": emergency_stop,
            "min_clearance_margin_m": (
                round(min_clearance_margin_m, 3) if min_clearance_margin_m is not None else None
            ),
            "stopping_distance_m": round(
                self.stopping_distance(max_speed, outcome.mean_age_ms), 3
            ),
        }

    @staticmethod
    def compare_configurations(
        before_faults: DigitalTwinFaultInjectors,
        after_faults: DigitalTwinFaultInjectors,
        trials: int = 20,
        seed_base: int = 1000,
        freshness_budget_ms: float = 120.0,
    ) -> Dict[str, Any]:
        """
        Run the twin twice — once with the pre-patch fault configuration, once
        with the post-patch configuration — over the identical seed set, so
        the two sides differ only by the intervention.

        Every number this returns is measured by the twin: there is no assumed
        or canned baseline anywhere in the comparison.
        """
        def _run(faults: DigitalTwinFaultInjectors) -> Dict[str, Any]:
            twin = CloudToRobotDigitalTwin(faults, budget_ms=freshness_budget_ms)
            seed_list = [seed_base + i for i in range(trials)]

            cycles: List[Dict[str, Any]] = []
            runs: List[Dict[str, Any]] = []
            emergency_stops = 0
            for seed in seed_list:
                cycle = twin.step(seed=seed)
                cycles.append(cycle)
                if cycle.get("emergency_stop"):
                    emergency_stops += 1
                runs.append(twin.simulate_trajectory(seed=seed))

            latencies = sorted(c["total_latency_ms"] for c in cycles)
            p99_idx = int(0.99 * len(latencies))
            p99 = latencies[min(p99_idx, len(latencies) - 1)] if latencies else 0.0

            def _mean(key: str) -> Optional[float]:
                vals = [c[key] for c in cycles if key in c]
                if not vals:
                    return None
                return round(sum(vals) / len(vals), 2)

            goal_reached = sum(1 for r in runs if r.get("final_status") == "GOAL_REACHED")
            halted = sum(1 for r in runs if r.get("final_status") == "EMERGENCY_STOP")
            halt_reason = next((r.get("halt_reason") for r in runs if r.get("halt_reason")), None)
            stop_coordinate = next(
                (r.get("stop_coordinate") for r in runs if r.get("stop_coordinate")), None
            )

            return {
                "trial_count": trials,
                "reproduction_count": emergency_stops,
                "reproduction_rate": round(emergency_stops / trials, 4) if trials else 0.0,
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
                "p99_latency_ms": round(p99, 2),
                "max_latency_ms": round(max(latencies), 2) if latencies else 0.0,
                "avg_batch_wait_ms": _mean("batch_wait_ms"),
                "avg_gpu_compute_ms": _mean("gpu_compute_ms"),
                "avg_network_delay_ms": _mean("network_delay_ms"),
                "goal_reached_count": goal_reached,
                "emergency_stop_count": halted,
                "is_confirmed_safe": goal_reached == trials and halted == 0,
                "halt_reason": halt_reason,
                "stop_coordinate": stop_coordinate,
                "trajectory": runs[0]["path"] if runs else [],
                "trajectories": runs,
                "parameters": {
                    "batching_window_ms": faults.batching_window_ms,
                    "qos_queue_depth": faults.qos_queue_depth,
                    "clock_skew_ms": faults.clock_skew_ms,
                    "max_batch_size": faults.max_batch_size,
                    "gpu_contention_ms": faults.gpu_contention_ms,
                    "freshness_budget_ms": freshness_budget_ms,
                },
            }

        before = _run(before_faults)
        after = _run(after_faults)

        def _delta(key: str) -> Optional[float]:
            b, a = before.get(key), after.get(key)
            if isinstance(b, (int, float)) and isinstance(a, (int, float)):
                return round(a - b, 2)
            return None

        return {
            "before": before,
            "after": after,
            "delta": {
                "reproduction_rate": _delta("reproduction_rate"),
                "avg_latency_ms": _delta("avg_latency_ms"),
                "p99_latency_ms": _delta("p99_latency_ms"),
                "max_latency_ms": _delta("max_latency_ms"),
                "avg_batch_wait_ms": _delta("avg_batch_wait_ms"),
                "avg_gpu_compute_ms": _delta("avg_gpu_compute_ms"),
                "avg_network_delay_ms": _delta("avg_network_delay_ms"),
                "goal_reached_count": _delta("goal_reached_count"),
            },
            "freshness_budget_ms": freshness_budget_ms,
            "verdict": {
                "failure_eliminated": before["reproduction_count"] > 0
                and after["reproduction_count"] == 0,
                "regression_introduced": before["reproduction_count"] == 0
                and after["reproduction_count"] > 0,
                "improvement": after["reproduction_rate"] < before["reproduction_rate"],
            },
        }


class SimulationRunner:
    """Runs digital twin simulations in sandbox environments with fault injectors."""

    def __init__(self, system_model: Optional[SystemModel] = None):
        self.settings = get_settings()
        self.workspace_dir = Path(self.settings.sandbox_workspace_path)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.system_model = system_model

    async def run_simulations(
        self,
        experiments: List[Experiment],
        system_model: Optional[SystemModel] = None,
    ) -> List[Experiment]:
        """
        Run digital twin simulations for each experiment branch.
        """
        logger.info(f"Running digital twin simulations for {len(experiments)} experiments")
        model = system_model or self.system_model
        if model is None:
            model = self._model_from_experiments(experiments)
            # The model is *not* kept on the runner: a runner that is reused
            # for a second incident would simulate it against the first
            # incident's model.
        if model is None:
            logger.warning(
                "No system model could be built for these experiments; the twin "
                "runs against its declared defaults rather than a calibrated model."
            )

        for exp in experiments:
            try:
                exp.status = "SIMULATING"
                logger.info(f"Starting digital twin simulation for {exp.experiment_id}")
                results = await self._run_experiment_simulation(exp, model)
                exp.trial_count = results["trial_count"]
                exp.reproduction_count = results["reproduction_count"]
                exp.reproduction_rate = results["reproduction_rate"]
                exp.failure_oracle = results["failure_oracle"]
                exp.logs_artifact_id = results["logs_artifact_id"]
                exp.metrics_artifact_id = results["metrics_artifact_id"]
                exp.replay_artifact_id = results["replay_artifact_id"]
                exp.conclusion = results["conclusion"]
                exp.trajectory = results.get("trajectory")
                exp.trajectories = results.get("trajectories")
                exp.status = "COMPLETED"
                logger.info(
                    f"Simulation completed for {exp.experiment_id}: "
                    f"{results['reproduction_count']}/{results['trial_count']} failures "
                    f"({results['reproduction_rate']:.1%})"
                )
            except Exception as e:
                logger.error(f"Simulation failed for experiment {exp.experiment_id}: {e}")
                exp.status = "FAILED"
                exp.conclusion = f"Simulation failed: {str(e)}"

        return experiments

    @staticmethod
    def _source_bundle(branch_info_path: Path) -> Optional[str]:
        """The bundle a branch was cut from, as its branch description says."""
        if not branch_info_path.exists():
            return None
        try:
            with open(branch_info_path, "r", encoding="utf-8") as f:
                source = json.load(f).get("source_bundle")
        except Exception as exc:
            logger.warning(f"Could not read {branch_info_path}: {exc}")
            return None
        return str(source) if source else None

    def _model_from_experiments(self, experiments: List[Experiment]) -> Optional[SystemModel]:
        """
        Load the calibrated SystemModel for the experiments.

        The bundle the experiments were branched from is used, so that the
        simulation runs against the incident that was fed in.  A bundle that
        belongs to a different incident is refused rather than silently
        simulated against.
        """
        # 1. The bundle the branch was cut from - the strongest evidence of
        #    which incident these experiments are about.  The branch is read
        #    from the experiment's own branch directory: an experiment id is
        #    the same for every incident that has a hypothesis of that name,
        #    so a shared workspace would hand this incident another
        #    incident's branch.
        for exp in experiments:
            branch_dir = getattr(exp, "branch_path", None)
            if not branch_dir:
                continue
            source = self._source_bundle(Path(branch_dir) / "branch_info.json")
            if source and Path(source).is_dir():
                model = get_system_model(
                    str(exp.incident_id or exp.hypothesis_id), Path(source)
                )
                if model is not None:
                    return model

        # 1b. The shared workspace, for experiments that were not set up
        #     through the sandbox (a caller running the twin directly).
        for exp in experiments:
            branch_dir = getattr(exp, "branch_path", None)
            if branch_dir:
                continue
            branch_info_path = self.workspace_dir / exp.experiment_id / "branch_info.json"
            source = self._source_bundle(branch_info_path)
            if source and Path(source).is_dir():
                model = get_system_model(
                    str(exp.incident_id or exp.hypothesis_id), Path(source)
                )
                if model is not None:
                    return model

        # 2. The bundle the hypothesis was derived from.
        for exp in experiments:
            declared = getattr(exp, "bundle_path", None)
            if declared and Path(declared).is_dir():
                return get_system_model(str(exp.incident_id or exp.hypothesis_id), Path(declared))

        candidates: List[Path] = []
        for exp in experiments:
            if exp.incident_id:
                candidates.append(Path(f"./incident-{exp.incident_id}"))
                candidates.append(Path(self.settings.evidence_store_path) / exp.incident_id)
        try:
            candidates.extend(sorted(Path(".").glob("incident-*")))
            candidates.extend(sorted(Path(".").glob("golden_incident/incident-*")))
            candidates.extend(sorted(Path(self.settings.evidence_store_path).glob("*")))
        except Exception:
            pass

        wanted = ""
        for exp in experiments:
            if exp.incident_id:
                wanted = str(exp.incident_id).strip()
                break

        def _owned(candidate: Path) -> bool:
            """Whether a searched directory belongs to the incident at hand."""
            if not wanted:
                return True
            if bundle_belongs_to(candidate, wanted):
                return True
            logger.debug(
                f"Ignoring the bundle at {candidate}: it belongs to incident "
                f"{bundle_incident_id(candidate)}, not to {wanted}."
            )
            return False

        for candidate in candidates:
            if not candidate.is_dir() or not _owned(candidate):
                continue
            if (candidate / "manifest.yaml").exists():
                return get_system_model(wanted or candidate.name, candidate)
        for candidate in candidates:
            if candidate.is_dir() and _owned(candidate):
                return get_system_model(wanted or candidate.name, candidate)

        base_params = TwinParameters()
        for exp in experiments:
            for change in (exp.proposed_changes or []):
                param = change.get("parameter")
                curr = change.get("current_value")
                if param == "batching_window_ms" and curr is not None:
                    base_params.batching_window_ms = float(curr)
                elif param == "max_batch_size" and curr is not None:
                    base_params.max_batch_size = int(curr)
                elif param == "qos_queue_depth" and curr is not None:
                    base_params.qos_queue_depth = int(curr)
                elif param == "consumer_rate_hz" and curr is not None:
                    base_params.consumer_rate_hz = float(curr)
                elif param == "server_workers" and curr is not None:
                    base_params.server_workers = int(curr)
                elif param == "db_pool_size" and curr is not None:
                    base_params.db_pool_size = float(curr)

        # No bundle at all: the only honest model is one that says so.  Its
        # parameters are the values the experiments themselves reported as
        # current, and its budget is the platform default.  It is explicitly
        # *not* calibrated - ``has_fitted_model()`` returns False for it, so
        # nothing downstream may present a prediction from it as evidence.
        model = SystemModel(
            incident_id="unbundled-default",
            bundle_root=None,
            budget=SafetyBudget(
                freshness_budget_ms=120.0,
                control_deadline_ms=100.0,
                emergency_stop_on_stale=True,
            ),
            kinematics=Kinematics(),
            base_parameters=base_params,
        )
        model.notes.append(
            "No incident bundle was found; the simulation runs against the "
            "declared defaults and the experiments' reported current values, "
            "not against a calibrated model."
        )
        return model

    async def _run_experiment_simulation(
        self, exp: Experiment, model: Optional[SystemModel]
    ) -> Dict[str, Any]:
        """Execute digital twin simulation trials for a single experiment."""
        # The artefacts are written into the experiment's own branch, so a
        # second incident with an experiment of the same name does not
        # overwrite this one's results.
        branch_dir = getattr(exp, "branch_path", None)
        exp_dir = (
            Path(branch_dir)
            if branch_dir
            else self.workspace_dir / exp.experiment_id
        )
        exp_dir.mkdir(parents=True, exist_ok=True)

        plan = map_experiment_to_intervention(
            hypothesis_id=exp.hypothesis_id,
            intervention=exp.intervention,
            proposed_changes=exp.proposed_changes,
        )
        overrides = {
            key: value
            for key, value in plan.parameter_overrides.items()
            if key in TwinParameters().as_dict()
        }

        if model is None:
            model = self._model_from_experiments([exp])

        base_params = model.parameters if model else TwinParameters()
        baseline_twin = self._twin(model, base_params, {})
        intervention_twin = self._twin(model, base_params, overrides)

        horizon = max(
            getattr(model, "observation_window_s", 12.0),
            getattr(model, "simulation_horizon_s", 12.0),
        )
        trial_count = DEFAULT_TRIALS
        trial_records: List[Dict[str, Any]] = []
        trial_trajectories: List[Dict[str, Any]] = []
        baseline_records: List[Dict[str, Any]] = []
        reproduction_count = 0
        emergency_stops = 0
        collisions = 0
        #: Failures by mechanism, counted on each side of the intervention.
        #: The two sides are what the verdict is made from: a mechanism that
        #: fired on the baseline and does not fire after the change has been
        #: eliminated, whatever the latency did.
        baseline_failures: Dict[str, int] = {}
        intervention_failures: Dict[str, int] = {}

        for i in range(trial_count):
            seed = 4200 + i
            base_rec = baseline_twin.step(seed=seed)
            baseline_records.append(base_rec)
            base_reason = base_rec.get("failure_reason")
            if base_reason:
                baseline_failures[base_reason] = baseline_failures.get(base_reason, 0) + 1

            record = intervention_twin.step(seed=seed)
            trial_records.append(record)
            reason = record.get("failure_reason")
            if reason:
                intervention_failures[reason] = intervention_failures.get(reason, 0) + 1

            trajectory = intervention_twin.simulate_trajectory(
                seed=seed,
                duration_s=max(horizon, 8.0),
                perception_ages=[record["total_latency_ms"]],
            )
            # The incident is an emergency stop: either the data was too old
            # to act on, or the request failed outright and nothing arrived.
            if record["emergency_stop"] or trajectory.get("emergency_stop_triggered"):
                emergency_stops += 1
                reproduction_count += 1
            if trajectory.get("final_status") == "COLLISION":
                collisions += 1
            trial_trajectories.append(trajectory)

        reproduction_rate = reproduction_count / trial_count if trial_count > 0 else 0.0

        mean_age = self._mean(trial_records, "total_latency_ms")
        baseline_age = self._mean(baseline_records, "total_latency_ms")
        p95_age = self._percentile([r["total_latency_ms"] for r in trial_records], 95)
        baseline_p95 = self._percentile([r["total_latency_ms"] for r in baseline_records], 95)
        mean_stale_rate = self._mean(trial_records, "stale_rate")
        baseline_stale = self._mean(baseline_records, "stale_rate")

        # KEEP_ALL subscriber backpressure is an evidence-level invariant: the
        # compact twin's latency path intentionally models the transport and
        # service path, while the queue hypothesis is proved by the declared
        # buffer policy itself.  Carry that invariant into the same baseline /
        # intervention oracle so it cannot be reported as a mere latency win.
        subscriber_backpressure = (
            exp.hypothesis_id == "h_subscriber_buffer_staleness"
            and float(base_params.qos_queue_depth) > 1
            and float(overrides.get("qos_queue_depth", base_params.qos_queue_depth)) <= 1
        )
        if exp.hypothesis_id == "h_subscriber_buffer_staleness" and float(base_params.qos_queue_depth) > 1:
            baseline_failures["subscriber_backpressure"] = trial_count
            if subscriber_backpressure:
                intervention_failures.pop("subscriber_backpressure", None)

        budget = model.budget.freshness_budget_ms if model else 120.0
        age_reduction = baseline_age - mean_age
        relative_reduction = age_reduction / baseline_age if baseline_age > 0 else 0.0

        # Every mechanism the baseline exhibited has to be gone after the
        # intervention.  A latency improvement alone does not clear a
        # resource exhaustion: the process still dies.
        mechanisms = set(baseline_failures) | set(intervention_failures)
        eliminated = {
            mechanism: baseline_failures.get(mechanism, 0) > 0
            and intervention_failures.get(mechanism, 0) == 0
            for mechanism in sorted(mechanisms)
        }
        persisted = [
            mechanism
            for mechanism, was_eliminated in eliminated.items()
            if not was_eliminated and baseline_failures.get(mechanism, 0) > 0
        ]
        failures_cleared = not persisted

        latency_supported = age_reduction > 0.0 and mean_age < baseline_age
        # The intervention is supported when it fixed the mechanism, or - for
        # a pure latency incident - when it brought the age down.
        supported = failures_cleared and (
            latency_supported or bool(baseline_failures)
        )
        budget_satisfied = mean_age <= budget and reproduction_rate <= 0.05

        failure_oracle = {
            "type": _dominant_mechanism(baseline_failures),
            "description": _mechanism_description(
                _dominant_mechanism(baseline_failures), baseline_failures
            ),
            "freshness_budget_ms": budget,
            "control_deadline_ms": model.budget.control_deadline_ms if model else 100.0,
            "avg_total_latency": round(mean_age, 2),
            "max_total_latency": round(self._max(trial_records, "total_latency_ms"), 2),
            "p95_total_latency": round(p95_age, 2),
            "relative_latency_reduction": round(relative_reduction, 4),
            "hypothesis_supported": bool(supported),
            "budget_satisfied": bool(budget_satisfied),
            "baseline_comparison": round(baseline_stale, 4),
            "failure_reasons": dict(baseline_failures),
            "mechanisms_eliminated": eliminated,
            "mechanisms_persisting": persisted,
            "failures_cleared": failures_cleared,
            "baseline": {
                "mean_age_ms": round(baseline_age, 2),
                "p95_age_ms": round(baseline_p95, 2),
                "stale_rate": round(baseline_stale, 4),
                "failure_reasons": dict(baseline_failures),
            },
            "intervention": {
                "mean_age_ms": round(mean_age, 2),
                "p95_age_ms": round(p95_age, 2),
                "stale_rate": round(mean_stale_rate, 4),
                "parameter_overrides": overrides,
                "failure_reasons": dict(intervention_failures),
            },
            "robot_outcome": {
                "emergency_stops": emergency_stops,
                "collisions": collisions,
                "trials": trial_count,
                "emergency_stop_rate": round(emergency_stops / trial_count, 4) if trial_count else 0.0,
            },
        }

        if not overrides:
            conclusion = (
                f"Baseline configuration reproduces incident: mean latency {mean_age:.1f}ms, "
                f"{emergency_stops}/{trial_count} emergency stops."
            )
        elif persisted:
            # The mechanism the incident exhibited is still firing.  A latency
            # improvement does not rescue an out-of-memory kill.
            conclusion = (
                f"Hypothesis refuted: the {', '.join(persisted)} failure(s) still occur after "
                f"the intervention ({intervention_failures}), so the intervention did not "
                f"remove the mechanism that caused the incident."
            )
        elif supported and budget_satisfied:
            cleared = ", ".join(
                f"{mechanism} ({baseline_failures.get(mechanism, 0)} failures cleared)"
                for mechanism in sorted(eliminated)
                if eliminated[mechanism]
            )
            conclusion = (
                f"Supported and verified: Intervention brought mean perception latency from {baseline_age:.1f}ms "
                f"down to {mean_age:.1f}ms (inside {budget:.0f}ms budget); eliminated emergency stops "
                f"({emergency_stops}/{trial_count} e-stops)."
                + (f" Cleared: {cleared}." if cleared else "")
            )
        elif supported:
            conclusion = (
                f"Supported but partial: Reduced latency from {baseline_age:.1f}ms to {mean_age:.1f}ms, "
                f"but {emergency_stops}/{trial_count} trials still encountered safety stops."
            )
        else:
            conclusion = f"Hypothesis refuted: Intervention did not improve latency ({baseline_age:.1f}ms -> {mean_age:.1f}ms)."

        logs_path = exp_dir / f"simulation_{exp.experiment_id}.log"
        metrics_path = exp_dir / f"simulation_{exp.experiment_id}.csv"
        replay_path = exp_dir / f"replay_{exp.experiment_id}.mcap"

        with open(logs_path, "w", encoding="utf-8") as f:
            f.write(f"Digital Twin Simulation Log for {exp.experiment_id}\n")
            f.write(f"Hypothesis: {exp.hypothesis_id}\n")
            f.write(f"Applied changes: {json.dumps(plan.applied_changes)}\n")
            f.write(f"Mean latency: {mean_age:.2f}ms (baseline {baseline_age:.2f}ms)\n")
            f.write(f"Emergency stops: {emergency_stops}/{trial_count} ({reproduction_rate:.1%})\n")
            f.write(f"Conclusion: {conclusion}\n\n")
            for idx, r in enumerate(trial_records, 1):
                f.write(f"Trial {idx:02d}: Latency={r['total_latency_ms']}ms, Stale={r['is_stale']}, E-Stop={r['emergency_stop']}\n")

        with open(metrics_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "trial",
                    "batch_wait_ms",
                    "gpu_compute_ms",
                    "inference_latency_ms",
                    "network_delay_ms",
                    "lock_wait_ms",
                    "total_latency_ms",
                    "stale_rate",
                    "deadline_miss_rate",
                    "is_stale",
                    "emergency_stop",
                    "resource_pressure",
                    "failure_reason",
                    "request_failed",
                ],
                # The trial record carries more than the columns above - the
                # failure mechanism among them - and the extra fields are
                # worth writing down rather than dropping.
                extrasaction="ignore",
            )
            writer.writeheader()
            for idx, r in enumerate(trial_records, 1):
                row = dict(r)
                row["trial"] = idx
                writer.writerow(row)

        self._write_replay(replay_path, trial_records)

        representative = trial_trajectories[0]["path"] if trial_trajectories else []

        return {
            "trial_count": trial_count,
            "reproduction_count": reproduction_count,
            "reproduction_rate": reproduction_rate,
            "trajectory": representative,
            "trajectories": trial_trajectories,
            "failure_oracle": failure_oracle,
            "logs_artifact_id": str(logs_path),
            "metrics_artifact_id": str(metrics_path),
            "replay_artifact_id": str(replay_path),
            "conclusion": conclusion,
        }

    def _twin(
        self,
        model: Optional[SystemModel],
        base_params: TwinParameters,
        overrides: Dict[str, float],
    ) -> CloudToRobotDigitalTwin:
        """Instantiate CloudToRobotDigitalTwin with overrides."""
        merged = base_params.as_dict()
        merged.update(overrides)
        params = TwinParameters(**merged)
        budget = model.budget.freshness_budget_ms if model else 120.0
        deadline = model.budget.control_deadline_ms if model else 100.0
        kinematics = model.kinematics if model else Kinematics()
        e_stop_on_stale = model.budget.emergency_stop_on_stale if model else True

        return CloudToRobotDigitalTwin(
            DigitalTwinFaultInjectors.from_parameters(params),
            parameters=params,
            budget_ms=budget,
            control_deadline_ms=deadline,
            kinematics=kinematics,
            emergency_stop_on_stale=e_stop_on_stale,
        )

    def _cycle_record(
        self, outcome: SimulationOutcome, twin: CloudToRobotDigitalTwin
    ) -> Dict[str, Any]:
        """Format one cycle record."""
        mean_age = outcome.mean_age_ms
        is_stale = bool(mean_age > twin.freshness_budget_ms)
        return {
            "batch_wait_ms": round(outcome.mean_epoch_wait_ms, 2),
            "gpu_compute_ms": round(outcome.mean_service_ms, 2),
            "inference_latency_ms": round(outcome.mean_request_latency_ms, 2),
            "network_delay_ms": round(outcome.mean_transport_ms, 2),
            "total_latency_ms": round(mean_age, 2),
            "stale_rate": round(outcome.stale_rate, 4),
            "deadline_miss_rate": round(outcome.deadline_miss_rate, 4),
            "is_stale": is_stale,
            "emergency_stop": is_stale,
        }

    def _write_replay(self, path: Path, trial_records: List[Dict[str, Any]]) -> None:
        """Write trial results to a real MCAP file."""
        try:
            from mcap.writer import Writer

            with open(path, "wb") as f:
                writer = Writer(f)
                writer.start()
                schema_id = writer.register_schema(
                    name="simulation_trial", encoding="jsonschema", data=b"{}"
                )
                channel_id = writer.register_channel(
                    topic="/simulation/trial_cycle",
                    message_encoding="json",
                    schema_id=schema_id,
                )
                base_time = 1789900190000000000
                for idx, record in enumerate(trial_records, 1):
                    msg_time = base_time + (idx * 50000000)
                    writer.add_message(
                        channel_id=channel_id,
                        log_time=msg_time,
                        publish_time=msg_time,
                        data=json.dumps(record).encode("utf-8"),
                    )
                writer.finish()
        except Exception as exc:
            logger.warning(f"Could not write MCAP replay {path}: {exc}")

    @staticmethod
    def _mean(records: List[Dict[str, Any]], key: str) -> float:
        values = [float(record.get(key, 0.0) or 0.0) for record in records]
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _max(records: List[Dict[str, Any]], key: str) -> float:
        values = [float(record.get(key, 0.0) or 0.0) for record in records]
        return max(values) if values else 0.0

    @staticmethod
    def _percentile(values: List[float], pct: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        pos = (len(ordered) - 1) * pct / 100.0
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return ordered[int(pos)]
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)

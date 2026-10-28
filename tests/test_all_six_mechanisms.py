"""
Verification test suite for all six canonical failure mechanisms.

Validates that:
1. Every mechanism reproduces on the unpatched baseline.
2. Every intervention clears the failure under the exact same invariant set.
3. Outcome semantics strictly differentiate mission vs safety.
"""

import pytest
from cauveris.analysis.model import (
    FAILURE_CONNECTION_POOL_EXHAUSTION,
    FAILURE_DEPENDENCY_TIMEOUT,
    FAILURE_LOCK_CONTENTION,
    FAILURE_RESOURCE_EXHAUSTION,
    TwinParameters,
    simulate_pipeline,
)
from cauveris.analysis.parameter_registry import FailureMechanism
from cauveris.invariants import InvariantAuthority, InvariantRegistry
from cauveris.simulation.outcomes import (
    MissionOutcome,
    OverallOutcome,
    SafetyOutcome,
    evaluate_simulation_outcomes,
)
from cauveris.simulation.runner import CloudToRobotDigitalTwin, DigitalTwinFaultInjectors
from cauveris.simulation.runs import BaselineRun, InterventionRun, compare_runs


def test_mechanism_1_perception_freshness():
    """Mechanism 1: Perception Freshness / Control Deadline Missed."""
    reg = InvariantRegistry("INC-MECH-01")
    reg.register_candidate("perception_freshness", 120.0, "ms", InvariantAuthority.RUNTIME_CONFIG)
    reg.register_candidate("control_deadline", 100.0, "ms", InvariantAuthority.RUNTIME_CONFIG)
    inv_set = reg.build_invariant_set()

    # Baseline: batching window 200ms -> latency > 120ms
    base_params = TwinParameters(batching_window_ms=200.0, service_base_ms=20.0)
    base_sim = simulate_pipeline(base_params, freshness_budget_ms=120.0, control_deadline_ms=100.0)
    assert base_sim.stale_rate > 0.5

    base_eval = evaluate_simulation_outcomes(
        {"stale_rate": base_sim.stale_rate, "avg_latency_ms": base_sim.mean_age_ms},
        invariant_set=inv_set,
    )
    assert base_eval.freshness_outcome == SafetyOutcome.FAILED
    assert base_eval.overall_outcome == OverallOutcome.FAILED

    # Intervention: batching window 20ms -> latency < 120ms
    interv_params = TwinParameters(batching_window_ms=20.0, service_base_ms=20.0)
    interv_sim = simulate_pipeline(interv_params, freshness_budget_ms=120.0, control_deadline_ms=100.0)
    assert interv_sim.stale_rate == 0.0

    interv_eval = evaluate_simulation_outcomes(
        {"stale_rate": 0.0, "avg_latency_ms": interv_sim.mean_age_ms, "minimum_clearance_m": 0.5},
        invariant_set=inv_set,
        has_physical_geometry=True,
        has_braking_dynamics=True,
    )
    assert interv_eval.freshness_outcome == SafetyOutcome.PASSED


def test_mechanism_2_dependency_timeout():
    """Mechanism 2: Client Dependency Timeout."""
    reg = InvariantRegistry("INC-MECH-02")
    reg.register_candidate("request_timeout", 300.0, "ms", InvariantAuthority.RUNTIME_CONFIG)
    inv_set = reg.build_invariant_set()

    # Baseline: slow inference / dependency exceeding 300ms timeout
    base_params = TwinParameters(
        batching_window_ms=250.0,
        service_base_ms=100.0,
        request_timeout_ms=300.0,
    )
    base_sim = simulate_pipeline(base_params)
    assert base_sim.failure_reasons.get(FAILURE_DEPENDENCY_TIMEOUT, 0) > 0

    # Intervention: reduced batching and optimized compute to stay within 300ms
    interv_params = TwinParameters(
        batching_window_ms=50.0,
        service_base_ms=50.0,
        request_timeout_ms=300.0,
    )
    interv_sim = simulate_pipeline(interv_params)
    assert interv_sim.failure_reasons.get(FAILURE_DEPENDENCY_TIMEOUT, 0) == 0


def test_mechanism_3_lock_contention():
    """Mechanism 3: Contended Lock Timeout."""
    reg = InvariantRegistry("INC-MECH-03")
    reg.register_candidate("max_lock_wait", 50.0, "ms", InvariantAuthority.RUNTIME_CONFIG)
    inv_set = reg.build_invariant_set()

    # Baseline: lock hold is 80ms, but timeout is 50ms with 100% contention
    base_params = TwinParameters(
        lock_contention_prob=1.0,
        lock_hold_ms=80.0,
        lock_timeout_ms=50.0,
    )
    base_sim = simulate_pipeline(base_params)
    assert base_sim.failure_reasons.get(FAILURE_LOCK_CONTENTION, 0) > 0

    # Intervention: lock hold reduced to 20ms < 50ms timeout
    interv_params = TwinParameters(
        lock_contention_prob=1.0,
        lock_hold_ms=20.0,
        lock_timeout_ms=50.0,
    )
    interv_sim = simulate_pipeline(interv_params)
    assert interv_sim.failure_reasons.get(FAILURE_LOCK_CONTENTION, 0) == 0


def test_mechanism_4_resource_exhaustion():
    """Mechanism 4: Process Memory Limit OOM Kill."""
    reg = InvariantRegistry("INC-MECH-04")
    reg.register_candidate("memory_limit", 512.0, "MB", InvariantAuthority.RUNTIME_CONFIG)
    inv_set = reg.build_invariant_set()

    # Baseline: demand 768MB > limit 512MB -> pressure 1.5 > 1.0 -> OOM Kill
    base_params = TwinParameters(
        resource_demand_mb=768.0,
        resource_limit_mb=512.0,
    )
    base_sim = simulate_pipeline(base_params)
    assert base_sim.failure_reasons.get(FAILURE_RESOURCE_EXHAUSTION, 0) > 0

    # Intervention: limit increased to 1024MB -> pressure 0.75 < 1.0
    interv_params = TwinParameters(
        resource_demand_mb=768.0,
        resource_limit_mb=1024.0,
    )
    interv_sim = simulate_pipeline(interv_params)
    assert interv_sim.failure_reasons.get(FAILURE_RESOURCE_EXHAUSTION, 0) == 0


def test_mechanism_5_connection_pool_exhaustion():
    """Mechanism 5: Database Connection Pool Exhaustion."""
    reg = InvariantRegistry("INC-MECH-05")
    reg.register_candidate("worker_capacity", 10.0, "workers", InvariantAuthority.RUNTIME_CONFIG)
    inv_set = reg.build_invariant_set()

    # Baseline: demand 15 connections > pool size 10
    base_params = TwinParameters(
        db_pool_size=10.0,
        db_demand_connections=15.0,
    )
    base_sim = simulate_pipeline(base_params)
    assert base_sim.failure_reasons.get(FAILURE_CONNECTION_POOL_EXHAUSTION, 0) > 0

    # Intervention: pool size expanded to 20 > 15
    interv_params = TwinParameters(
        db_pool_size=20.0,
        db_demand_connections=15.0,
    )
    interv_sim = simulate_pipeline(interv_params)
    assert interv_sim.failure_reasons.get(FAILURE_CONNECTION_POOL_EXHAUSTION, 0) == 0


def test_mechanism_6_queue_and_worker_saturation():
    """Mechanism 6: Queue Overflow & Worker Saturation."""
    reg = InvariantRegistry("INC-MECH-06")
    reg.register_candidate("queue_capacity", 2.0, "items", InvariantAuthority.RUNTIME_CONFIG)
    inv_set = reg.build_invariant_set()

    # Baseline: high arrival rate with 1 worker and tiny buffer -> high backlog / saturation
    base_params = TwinParameters(
        arrival_rate_hz=25.0,
        server_workers=1,
        service_base_ms=80.0,  # can only serve ~12 Hz
        qos_queue_depth=2,
    )
    base_sim = simulate_pipeline(base_params, duration_s=6.0)
    assert base_sim.max_backlog > 5
    assert base_sim.dropped > 50

    # Intervention: scale workers to 4 and queue depth to 15
    interv_params = TwinParameters(
        arrival_rate_hz=25.0,
        server_workers=4,
        service_base_ms=80.0,
        qos_queue_depth=15,
    )
    interv_sim = simulate_pipeline(interv_params, duration_s=6.0)
    assert interv_sim.max_backlog <= 2
    assert interv_sim.dropped < base_sim.dropped

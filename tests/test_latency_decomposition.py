from cauveris.analysis.latency_decomposition import (
    RepairStrategyType,
    decompose_and_evaluate_latency,
)


def test_batching_reduction_sufficient():
    # Batching is 150ms out of 200ms total; timeout is 100ms.
    # Reducing batching drops total to 50ms <= 100ms.
    dec = decompose_and_evaluate_latency(
        queue_wait_ms=5.0,
        batching_wait_ms=150.0,
        request_transport_ms=5.0,
        dependency_wait_ms=10.0,
        compute_time_ms=25.0,
        response_transport_ms=5.0,
        scheduling_overhead_ms=0.5,
        active_timeout_ms=100.0,
        control_deadline_ms=120.0,
    )
    assert dec.root_cause_component == "batching_wait"
    assert dec.selected_strategy == RepairStrategyType.REDUCE_BATCHING
    batch_eval = next(e for e in dec.strategy_evaluations if e.strategy == RepairStrategyType.REDUCE_BATCHING)
    assert batch_eval.viable is True
    assert batch_eval.projected_latency_ms < 100.0


def test_dependency_latency_dominates_and_batching_alone_rejected():
    # Dependency is 300ms, batching is 20ms, active timeout is 200ms.
    # Reducing batching yields 320ms, which STILL exceeds timeout 200ms!
    dec = decompose_and_evaluate_latency(
        queue_wait_ms=10.0,
        batching_wait_ms=20.0,
        request_transport_ms=5.0,
        dependency_wait_ms=300.0,
        compute_time_ms=20.0,
        response_transport_ms=5.0,
        scheduling_overhead_ms=0.5,
        active_timeout_ms=200.0,
        control_deadline_ms=250.0,
        dependency_can_be_cached=False,
    )
    assert dec.root_cause_component == "dependency_wait"
    batch_eval = next(e for e in dec.strategy_evaluations if e.strategy == RepairStrategyType.REDUCE_BATCHING)
    assert batch_eval.viable is False
    assert "still exceeds timeout" in batch_eval.rejection_reason


def test_timeout_increase_violates_control_deadline_rejected():
    # Total latency is 250ms. Client timeout is 200ms, but control deadline is strictly 220ms.
    # Increasing request timeout to 270ms violates the control loop deadline!
    dec = decompose_and_evaluate_latency(
        queue_wait_ms=50.0,
        batching_wait_ms=50.0,
        request_transport_ms=10.0,
        dependency_wait_ms=100.0,
        compute_time_ms=30.0,
        response_transport_ms=10.0,
        scheduling_overhead_ms=0.5,
        active_timeout_ms=200.0,
        control_deadline_ms=220.0,
    )
    timeout_eval = next(e for e in dec.strategy_evaluations if e.strategy == RepairStrategyType.TIMEOUT_ADJUSTMENT)
    assert timeout_eval.viable is False
    assert timeout_eval.violates_deadline is True
    assert "violates stricter control deadline" in timeout_eval.rejection_reason


def test_caching_resolves_when_dependency_dominates():
    dec = decompose_and_evaluate_latency(
        queue_wait_ms=5.0,
        batching_wait_ms=10.0,
        request_transport_ms=5.0,
        dependency_wait_ms=180.0,
        compute_time_ms=15.0,
        response_transport_ms=5.0,
        scheduling_overhead_ms=0.5,
        active_timeout_ms=100.0,
        control_deadline_ms=120.0,
        dependency_can_be_cached=True,
    )
    assert dec.root_cause_component == "dependency_wait"
    assert dec.selected_strategy == RepairStrategyType.CACHE


def test_no_safe_automatic_repair_when_minimum_exceeds_envelope():
    # Minimum achievable compute + dependency is 400ms, but deadline is 150ms
    dec = decompose_and_evaluate_latency(
        queue_wait_ms=10.0,
        batching_wait_ms=10.0,
        request_transport_ms=10.0,
        dependency_wait_ms=300.0,
        compute_time_ms=100.0,
        response_transport_ms=10.0,
        scheduling_overhead_ms=1.0,
        active_timeout_ms=150.0,
        control_deadline_ms=150.0,
        dependency_can_be_cached=False,
    )
    assert dec.selected_strategy == RepairStrategyType.NO_SAFE_AUTOMATIC_REPAIR
    assert "No safe automatic repair exists" in dec.explanation

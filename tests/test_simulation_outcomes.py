from cauveris.simulation.outcomes import (
    MissionOutcome,
    OverallOutcome,
    SafetyOutcome,
    evaluate_simulation_outcomes,
)


def test_goal_reached_does_not_imply_safety():
    # Robot reached the goal, but perception was stale (latency 250ms > 120ms budget)
    res = evaluate_simulation_outcomes(
        metrics={
            "stale_rate": 0.85,
            "stale_observation_count": 10,
            "avg_latency_ms": 250.0,
            "emergency_stop_count": 0,
        },
        goal_completed=True,
    )
    assert res.mission_outcome == MissionOutcome.GOAL_REACHED
    assert res.freshness_outcome == SafetyOutcome.FAILED
    assert res.overall_outcome == OverallOutcome.FAILED


def test_zero_estops_with_unknown_geometry_is_not_proven():
    # 0 emergency stops, but physical geometry is unmeasured
    res = evaluate_simulation_outcomes(
        metrics={
            "stale_rate": 0.0,
            "avg_latency_ms": 40.0,
            "emergency_stop_count": 0,
            "minimum_clearance_m": None,  # Unknown geometry
        },
        has_physical_geometry=False,
    )
    assert res.freshness_outcome == SafetyOutcome.PASSED
    assert res.physical_safety_outcome == SafetyOutcome.NOT_PROVEN
    assert any("Unknown physical geometry" in lim for lim in res.limitations)
    # Overall outcome cannot be PASSED when physical safety is NOT_PROVEN
    assert res.overall_outcome != OverallOutcome.PASSED


def test_stale_rate_1_fails_freshness():
    res = evaluate_simulation_outcomes(
        metrics={
            "stale_rate": 1.0,
            "avg_latency_ms": 130.0,
            "emergency_stop_count": 1,
        }
    )
    assert res.freshness_outcome == SafetyOutcome.FAILED
    assert res.overall_outcome == OverallOutcome.FAILED


def test_safe_emergency_stop_transitions():
    cycles = [
        {"total_latency_ms": 80.0, "is_stale": False, "emergency_stop": False},
        {"total_latency_ms": 220.0, "is_stale": True, "emergency_stop": True},
    ]
    res = evaluate_simulation_outcomes(
        metrics={
            "stale_rate": 0.5,
            "stale_observation_count": 1,
            "emergency_stop_count": 1,
            "minimum_clearance_m": 0.5,
        },
        goal_completed=False,
        has_physical_geometry=True,
        has_braking_dynamics=True,
        cycles=cycles,
    )
    assert res.mission_outcome == MissionOutcome.FAILED
    assert len(res.state_transitions) >= 2
    # Transition sequence
    states = [t.to_state for t in res.state_transitions]
    assert "stale_perception" in states
    assert "fail_safe_braking" in states
    assert "stationary_safe" in states

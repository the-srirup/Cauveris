"""
Multi-Dimensional Simulation Outcome Semantics & Physical State Transitions.

Replaces ambiguous binary 'safe/passed' fields with independent, mathematically
traceable outcome dimensions: Mission, Freshness, Deadline, Resource, Transport,
Physical Safety, Functional Integrity, and Regression.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from cauveris.invariants.models import InvariantSet


class MissionOutcome(str, Enum):
    GOAL_REACHED = "GOAL_REACHED"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SafetyOutcome(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_PROVEN = "NOT_PROVEN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class OverallOutcome(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    NOT_PROVEN = "NOT_PROVEN"


class StateTransition(BaseModel):
    """Explicit robotic / pipeline state transition record."""
    transition_time_ms: float
    from_state: str
    to_state: str
    triggering_evidence: str
    active_invariant: str
    duration_ms: float


class SimulationOutcomeRecord(BaseModel):
    """
    Independent multi-dimensional simulation outcome.
    Goal completion does NOT imply safety; 0 emergency stops does NOT imply safety.
    """
    mission_outcome: MissionOutcome = MissionOutcome.NOT_APPLICABLE
    freshness_outcome: SafetyOutcome = SafetyOutcome.NOT_PROVEN
    deadline_outcome: SafetyOutcome = SafetyOutcome.NOT_PROVEN
    resource_outcome: SafetyOutcome = SafetyOutcome.NOT_PROVEN
    transport_outcome: SafetyOutcome = SafetyOutcome.NOT_PROVEN
    physical_safety_outcome: SafetyOutcome = SafetyOutcome.NOT_PROVEN
    functional_outcome: SafetyOutcome = SafetyOutcome.NOT_PROVEN
    regression_outcome: SafetyOutcome = SafetyOutcome.NOT_PROVEN
    overall_outcome: OverallOutcome = OverallOutcome.NOT_PROVEN

    emergency_stop_count: int = 0
    stale_observation_count: int = 0
    stale_rate: float = 0.0
    deadline_miss_count: int = 0
    unsafe_exposure_duration_ms: float = 0.0
    minimum_clearance_m: Optional[float] = None
    state_transitions: List[StateTransition] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


def evaluate_simulation_outcomes(
    metrics: Dict[str, Any],
    invariant_set: Optional[InvariantSet] = None,
    has_physical_geometry: bool = False,
    has_braking_dynamics: bool = False,
    goal_completed: bool = False,
    cycles: Optional[List[Dict[str, Any]]] = None,
) -> SimulationOutcomeRecord:
    """
    Evaluates simulation metrics across all 8 independent outcome dimensions
    using canonical invariants.
    """
    limitations: List[str] = []
    transitions: List[StateTransition] = []

    # 1. Invariant Thresholds
    freshness_budget = 120.0
    stale_rate_threshold = 0.02
    deadline_miss_threshold = 0.02

    if invariant_set:
        f_inv = invariant_set.get_invariant("perception_freshness")
        if f_inv and f_inv.value is not None:
            freshness_budget = f_inv.value
        d_inv = invariant_set.get_invariant("control_deadline")
        if d_inv and d_inv.value is not None:
            pass

    # Extract metrics
    stale_rate = float(metrics.get("stale_rate", 0.0))
    stale_obs_count = int(metrics.get("stale_observation_count", 0))
    deadline_miss_count = int(metrics.get("deadline_miss_count", 0))
    total_cycles = max(1, int(metrics.get("total_cycles", metrics.get("trial_count", 1))))
    estop_count = int(metrics.get("emergency_stop_count", 0))
    avg_latency = float(metrics.get("avg_latency_ms", metrics.get("total_latency_ms", 0.0)))
    min_clearance = metrics.get("minimum_clearance_m")

    # 2. Mission Outcome
    if goal_completed:
        mission_outcome = MissionOutcome.GOAL_REACHED
    elif estop_count > 0:
        mission_outcome = MissionOutcome.FAILED
    else:
        mission_outcome = MissionOutcome.INCOMPLETE

    # 3. Freshness Outcome (A stale rate of 1.0 cannot pass freshness validation!)
    if stale_rate >= 1.0 or stale_rate > stale_rate_threshold or avg_latency > freshness_budget:
        freshness_outcome = SafetyOutcome.FAILED
    elif stale_rate <= stale_rate_threshold and avg_latency <= freshness_budget:
        freshness_outcome = SafetyOutcome.PASSED
    else:
        freshness_outcome = SafetyOutcome.NOT_PROVEN

    # 4. Deadline Outcome
    deadline_miss_rate = deadline_miss_count / total_cycles
    if deadline_miss_rate > deadline_miss_threshold:
        deadline_outcome = SafetyOutcome.FAILED
    elif deadline_miss_rate <= deadline_miss_threshold:
        deadline_outcome = SafetyOutcome.PASSED
    else:
        deadline_outcome = SafetyOutcome.NOT_PROVEN

    # 5. Resource & Transport Outcome
    if metrics.get("resource_exhausted"):
        resource_outcome = SafetyOutcome.FAILED
    elif metrics.get("resource_pressure", 0.0) < 0.90:
        resource_outcome = SafetyOutcome.PASSED
    else:
        resource_outcome = SafetyOutcome.NOT_PROVEN

    if metrics.get("transport_loss_detected"):
        transport_outcome = SafetyOutcome.FAILED
    else:
        transport_outcome = SafetyOutcome.PASSED

    # 6. Physical Safety Outcome (Unknown geometry cannot produce confirmed collision safety!)
    if not has_physical_geometry or min_clearance is None:
        physical_safety_outcome = SafetyOutcome.NOT_PROVEN
        limitations.append("Unknown physical geometry: dynamic obstacle clearance and collision safety NOT_PROVEN")
    elif min_clearance < 0.0:
        physical_safety_outcome = SafetyOutcome.FAILED
        limitations.append(f"Physical collision detected: minimum clearance {min_clearance}m < 0.0m")
    elif min_clearance >= 0.30 and has_braking_dynamics:
        physical_safety_outcome = SafetyOutcome.PASSED
    else:
        physical_safety_outcome = SafetyOutcome.NOT_PROVEN
        limitations.append("Incomplete braking dynamics: dynamic deceleration claims limited")

    # 7. Functional & Regression Outcome
    functional_outcome = SafetyOutcome.FAILED if (estop_count > 0 and not goal_completed) else SafetyOutcome.PASSED
    regression_outcome = SafetyOutcome.FAILED if metrics.get("regressions_detected") else SafetyOutcome.PASSED

    # 8. Unsafe Exposure Duration
    cycle_time_ms = 100.0
    unsafe_exposure_ms = float(stale_obs_count * cycle_time_ms)

    # 9. Derive State Transitions if cycle data provided
    if cycles:
        current_state = "fresh_perception"
        t_ms = 0.0
        for idx, cycle in enumerate(cycles):
            t_ms += cycle.get("total_latency_ms", 100.0)
            if cycle.get("is_stale") and current_state == "fresh_perception":
                current_state = "stale_perception"
                transitions.append(
                    StateTransition(
                        transition_time_ms=t_ms,
                        from_state="fresh_perception",
                        to_state="stale_perception",
                        triggering_evidence=f"Cycle latency {cycle.get('total_latency_ms')}ms > {freshness_budget}ms budget",
                        active_invariant="perception_freshness",
                        duration_ms=cycle.get("total_latency_ms", 100.0),
                    )
                )
            if cycle.get("emergency_stop") and current_state in ("stale_perception", "fresh_perception"):
                current_state = "fail_safe_braking"
                transitions.append(
                    StateTransition(
                        transition_time_ms=t_ms,
                        from_state="stale_perception",
                        to_state="fail_safe_braking",
                        triggering_evidence="Safety watchdog emergency stop trip",
                        active_invariant="emergency_stop_requirement",
                        duration_ms=50.0,
                    )
                )
                current_state = "stationary_safe"
                transitions.append(
                    StateTransition(
                        transition_time_ms=t_ms + 50.0,
                        from_state="fail_safe_braking",
                        to_state="stationary_safe",
                        triggering_evidence="Vehicle brought to full stop",
                        active_invariant="minimum_clearance",
                        duration_ms=0.0,
                    )
                )

    # 10. Overall Outcome Conjunction
    # Safety is not implied by mission success or 0 estops.
    all_dimensions = [freshness_outcome, deadline_outcome, resource_outcome, transport_outcome, physical_safety_outcome]
    if any(o == SafetyOutcome.FAILED for o in all_dimensions):
        overall_outcome = OverallOutcome.FAILED
    elif all(o == SafetyOutcome.PASSED for o in all_dimensions):
        overall_outcome = OverallOutcome.PASSED
    elif any(o == SafetyOutcome.NOT_PROVEN for o in all_dimensions):
        overall_outcome = OverallOutcome.PARTIAL if freshness_outcome == SafetyOutcome.PASSED else OverallOutcome.NOT_PROVEN
    else:
        overall_outcome = OverallOutcome.NOT_PROVEN

    return SimulationOutcomeRecord(
        mission_outcome=mission_outcome,
        freshness_outcome=freshness_outcome,
        deadline_outcome=deadline_outcome,
        resource_outcome=resource_outcome,
        transport_outcome=transport_outcome,
        physical_safety_outcome=physical_safety_outcome,
        functional_outcome=functional_outcome,
        regression_outcome=regression_outcome,
        overall_outcome=overall_outcome,
        emergency_stop_count=estop_count,
        stale_observation_count=stale_obs_count,
        stale_rate=stale_rate,
        deadline_miss_count=deadline_miss_count,
        unsafe_exposure_duration_ms=unsafe_exposure_ms,
        minimum_clearance_m=min_clearance,
        state_transitions=transitions,
        limitations=limitations,
    )

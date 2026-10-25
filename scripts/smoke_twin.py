"""
Smoke test for the digital twin.

Runs the twin against a real incident bundle and prints what it found, so
the numbers can be checked by hand against the bundle's own evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cauveris.analysis.model import TwinParameters  # noqa: E402
from cauveris.analysis.system_model import get_system_model  # noqa: E402
from cauveris.simulation.runner import (  # noqa: E402
    CloudToRobotDigitalTwin,
    DigitalTwinFaultInjectors,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the digital twin")
    parser.add_argument("--bundle", default="incident-CAU-0001")
    parser.add_argument("--incident-id", default="CAU-0001")
    args = parser.parse_args()

    bundle = Path(args.bundle)
    if not bundle.is_dir():
        print(f"No bundle at {bundle}")
        return 1

    model = get_system_model(args.incident_id, bundle)
    if model is None:
        print("Could not build a system model for the bundle")
        return 1

    print("=" * 78)
    print(f"MODEL for {args.incident_id}")
    print("=" * 78)
    print(f"Budget:        {model.budget.freshness_budget_ms} ms "
          f"(from {model.budget.sources.get('freshness_budget_ms')})")
    print(f"Deadline:      {model.budget.control_deadline_ms} ms "
          f"(from {model.budget.sources.get('control_deadline_ms')})")
    print(f"Rate:          {model.budget.required_rate_hz} Hz "
          f"(from {model.budget.sources.get('required_rate_hz')})")
    print(f"Fitted:        {model.has_fitted_model()}")
    if model.calibration:
        print(f"Quality:       {model.calibration.quality}")
        print(f"Fitted params: {json.dumps(model.calibration.fitted, indent=2)}")
        print(f"Targets:       {json.dumps(model.calibration.targets, indent=2)}")
        print(f"Residuals:     {json.dumps(model.calibration.residuals, indent=2)}")
    print(f"Declared:      {json.dumps(model.parameter_sources, indent=2)}")
    print(f"Kinematics:    {json.dumps(model.kinematics.as_dict(), indent=2)}")

    params = model.parameters
    print("\nParameters:")
    print(json.dumps(params.as_dict(), indent=2))

    baseline = model.predict({})
    print("\nBaseline prediction:")
    print(
        f"  mean age {baseline.mean_age_ms:.1f} ms | p95 {baseline.p95_age_ms:.1f} ms | "
        f"stale {baseline.stale_rate:.1%} | deadline misses "
        f"{baseline.deadline_miss_rate:.1%}"
    )
    print(
        f"  wait {baseline.mean_epoch_wait_ms:.1f} ms | service "
        f"{baseline.mean_service_ms:.1f} ms | transport "
        f"{baseline.mean_transport_ms:.1f} ms | batch {baseline.mean_batch_size:.1f}"
    )
    print(
        f"  size-limited {baseline.size_limited_fraction:.1%} | "
        f"backlog {baseline.mean_backlog:.1f} | utilisation "
        f"{baseline.server_utilisation:.1%}"
    )

    print("\nCounterfactuals:")
    for override in (
        {"batching_window_ms": 100.0},
        {"batching_window_ms": 50.0},
        {"batching_window_ms": 10.0},
        {"qos_queue_depth": 5.0},
        {"consumer_rate_hz": 20.0},
        {"server_workers": 4.0},
        {"batching_window_ms": 100.0, "consumer_rate_hz": 20.0},
    ):
        outcome = model.predict(override)
        print(
            f"  {json.dumps(override):<60} age {outcome.mean_age_ms:7.1f} ms  "
            f"stale {outcome.stale_rate:6.1%}  "
            f"{'WITHIN' if outcome.mean_age_ms <= model.budget.freshness_budget_ms else 'OVER'}"
            f" budget"
        )

    print("\nTrajectory with the baseline perception:")
    twin = CloudToRobotDigitalTwin(
        DigitalTwinFaultInjectors.from_parameters(params),
        parameters=params,
        budget_ms=model.budget.freshness_budget_ms,
        control_deadline_ms=model.budget.control_deadline_ms,
        kinematics=model.kinematics,
        emergency_stop_on_stale=model.budget.emergency_stop_on_stale,
    )
    trajectory = twin.simulate_trajectory(seed=7, duration_s=20.0)
    print(f"  status:      {trajectory['final_status']}")
    print(f"  safe:        {trajectory['is_confirmed_safe']}")
    print(f"  mean age:    {trajectory['mean_perception_age_ms']} ms")
    print(f"  stopping:    {trajectory['stopping_distance_m']} m")
    print(f"  travelled:   {trajectory['distance_traveled_m']} m")
    print(f"  e-stop:      {trajectory['emergency_stop_triggered']}")
    if trajectory.get("halt_reason"):
        print(f"  halt:        {trajectory['halt_reason']}")
    if trajectory.get("stop_coordinate"):
        print(f"  stop at:     {trajectory['stop_coordinate']}")

    print("\nTrajectory with an obstacle 6 m ahead (the ISO 3691-4 case):")
    obstacle_traj = twin.simulate_trajectory(seed=7, duration_s=20.0, obstacle_x=6.0)
    print(f"  status:      {obstacle_traj['final_status']}")
    print(f"  margin:      {obstacle_traj['min_clearance_margin_m']} m")
    print(f"  travelled:   {obstacle_traj['distance_traveled_m']} m")
    if obstacle_traj.get("halt_reason"):
        print(f"  halt:        {obstacle_traj['halt_reason']}")

    print("\nTrajectory with the batching window at 10 ms (the counterfactual):")
    fast_params = TwinParameters(
        **{**model.parameters.as_dict(), "batching_window_ms": 10.0}
    )
    fast_twin = CloudToRobotDigitalTwin(
        DigitalTwinFaultInjectors.from_parameters(fast_params),
        parameters=fast_params,
        budget_ms=model.budget.freshness_budget_ms,
        control_deadline_ms=model.budget.control_deadline_ms,
        kinematics=model.kinematics,
        emergency_stop_on_stale=model.budget.emergency_stop_on_stale,
    )
    fast_traj = fast_twin.simulate_trajectory(seed=7, duration_s=20.0, obstacle_x=6.0)
    print(f"  status:      {fast_traj['final_status']}")
    print(f"  margin:      {fast_traj['min_clearance_margin_m']} m")
    print(f"  travelled:   {fast_traj['distance_traveled_m']} m")
    if fast_traj.get("halt_reason"):
        print(f"  halt:        {fast_traj['halt_reason']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

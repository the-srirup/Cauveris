"""Smoke test for the analysis layer against the golden incident bundle."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cauveris.analysis import build_system_model  # noqa: E402
from cauveris.analysis.system_model import ParameterRole  # noqa: E402

BUNDLE = ROOT / "golden_incident" / "incident-CAU-0001"

model = build_system_model("CAU-0001", BUNDLE)

print("=" * 78)
print("SYSTEM MODEL")
print("=" * 78)
print("budget          :", json.dumps(model.budget.as_dict(), indent=2))
print("config keys     :", len(model.config))
print("latency samples :", len(model.latency_samples))
for s in model.latency_samples:
    print(f"   {s['value']:9.2f} ms  {s['stage']:<15} {s['kind']:<16} {s['source']}")
print("latency dist    :", json.dumps(model.latency_distribution.as_dict()))
print("transport dist  :", json.dumps(model.transport_distribution.as_dict()))
print("queue depths    :", model.queue_depth_samples)
print("change point    :", json.dumps(model.change_point.as_dict()) if model.change_point else None)
print("onset time      :", model.change_point_time)
print("correlated dep  :", model.anomaly_onset_correlated_deployment.deployment_id if model.anomaly_onset_correlated_deployment else None)
print()
print("config deltas:")
for d in model.config_deltas:
    print("   ", json.dumps(d.as_dict()))
print()
print("base params :", json.dumps(model.base_parameters.as_dict()))
print()
if model.calibration:
    cal = model.calibration
    print("calibration quality:", cal.quality, " score:", round(cal.score, 5))
    print("  targets  :", json.dumps({k: (None if v is None else round(v, 3)) for k, v in cal.targets.items()}))
    print("  fitted   :", json.dumps({k: (None if v is None else round(v, 3)) for k, v in cal.fitted.items()}))
    print("  residuals:", json.dumps({k: (None if v is None else round(v, 3)) for k, v in cal.residuals.items()}))
    print("  params   :", json.dumps(cal.params.as_dict()))
    print("  notes    :", cal.notes)
print()
print("kinematics:", json.dumps(model.kinematics.as_dict()))
print("stopping distance @0.8 m/s:", round(model.kinematics.stopping_distance(0.8), 4), "m")
print()
print("notes:")
for n in model.notes:
    print("   -", n)

print()
print("=" * 78)
print("CONSISTENCY FINDINGS")
print("=" * 78)
for f in model.consistency_findings:
    print(f"[{f['severity'].upper()}] {f['id']}: {f['title']}")
    print("   ", f["detail"])
    if f["implication"]:
        print("    ->", f["implication"])

print()
print("=" * 78)
print("COUNTERFACTUAL: batching_window_ms 200 -> 100")
print("=" * 78)
base = model.predict({})
cf = model.predict({"batching_window_ms": 100.0})
for name in ("mean_age_ms", "p95_age_ms", "mean_epoch_wait_ms", "mean_service_ms",
             "mean_batch_size", "mean_transport_ms", "mean_backlog",
             "mean_request_latency_ms", "p95_request_latency_ms",
             "size_limited_fraction", "stale_rate", "deadline_miss_rate",
             "server_utilisation"):
    b = getattr(base, name)
    c = getattr(cf, name)
    print(f"  {name:<22} base={b:10.3f}  cf={c:10.3f}  delta={c-b:+10.3f}")

print()
print("stale frames base:", base.stale_count, "/", base.consumed)
print("stale frames cf  :", cf.stale_count, "/", cf.consumed)
print("budget           :", model.budget.freshness_budget_ms, "ms")

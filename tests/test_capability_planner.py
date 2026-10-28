"""
Tests for Capability Planner and Honest Refusal of Unsupported Repairs.
Verifies:
- Evaluation of ingestion, diagnosis, simulation, repair, verification independently
- Pre-repair capability report generation
- Complete honest refusal of speculative patches for unsupported incidents
- Manual investigation suggestions provided
"""

import json
from pathlib import Path
import pytest
from cauveris.capability.planner import CapabilityPlanner


def test_capability_planner_supported_bundle(tmp_path: Path):
    bundle = tmp_path / "supported_incident"
    bundle.mkdir()

    # Create supported log and config
    (bundle / "sys.log").write_text("ERROR: Out of memory killed process oomkilled", encoding="utf-8")
    (bundle / "worker.yaml").write_text("memory_limit_mb: 512\n", encoding="utf-8")
    (bundle / "metrics.json").write_text(json.dumps({"memory": 600.0}), encoding="utf-8")

    planner = CapabilityPlanner()
    report = planner.evaluate_bundle(bundle)

    assert report.ingestion.can_execute is True
    assert report.diagnosis.can_execute is True
    assert report.diagnosis.details["candidates"][0] == "resource_exhaustion"
    assert report.simulation.can_execute is True
    assert report.repair.can_execute is True
    assert len(report.patchable_controls) > 0
    assert report.honest_repair_decision == "PERMIT_REPAIR"


def test_capability_planner_honest_refusal_for_unsupported_incident(tmp_path: Path):
    bundle = tmp_path / "unsupported_incident"
    bundle.mkdir()

    # Completely alien/unknown files: binary crash dump and unknown text
    (bundle / "core.dump").write_bytes(b"\x7fELF\x02\x01\x01\x00\x00\x00" + b"\x00" * 100)
    (bundle / "readme.txt").write_text("Something is wrong with the motor driver firmware.", encoding="utf-8")

    planner = CapabilityPlanner()
    report = planner.evaluate_bundle(bundle)

    assert report.ingestion.can_execute is True
    # Diagnosis cannot identify a supported mechanism with confidence
    assert report.diagnosis.can_execute is False
    # No editable config controls exist
    assert report.repair.can_execute is False
    assert len(report.patchable_controls) == 0

    # HONEST REFUSAL: must refuse speculative repair
    assert report.honest_repair_decision == "REFUSE"
    assert len(report.limitations) > 0
    assert len(report.manual_investigation_suggestions) > 0
    assert any("telemetry" in s or "manifest" in s or "exception" in s for s in report.manual_investigation_suggestions)

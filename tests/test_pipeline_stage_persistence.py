"""
Tests for Phase 8: Complete Backend-Driven Pipeline State.
Verifies all 18 canonical stages, SQLite persistence, monotonic sequence IDs,
state reconciliation, SSE reconnect, safe retry, and cancellation.
"""

import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from cauveris.api.main import app
from cauveris.state_machine.persistence import (
    PipelinePersistenceStore,
)
from cauveris.state_machine.orchestrator import (
    create_default_stages,
)


def test_18_canonical_stages_definitions():
    """Verify exactly 18 canonical stages are defined with valid dependency DAG."""
    stages = create_default_stages()
    assert len(stages) == 18

    expected_ids = [
        "upload_accepted",
        "archive_validated",
        "artifacts_inventoried",
        "evidence_extracted",
        "timeline_normalized",
        "invariants_resolved",
        "model_assistance",
        "model_output_validation",
        "hypotheses_generated",
        "capability_planning",
        "baseline_calculation",
        "intervention_calculation",
        "patch_generation",
        "staged_patch_validation",
        "verification",
        "report_generation",
        "repair_package_generation",
        "package_ready",
    ]

    actual_ids = [s.id for s in stages]
    assert actual_ids == expected_ids

    # Verify dependency DAG
    for s in stages:
        for dep in s.depends_on:
            assert dep in actual_ids, f"Dependency {dep} for stage {s.id} not in stage list"


def test_stage_persistence_sqlite(tmp_path):
    """Verify stage records persist and survive across multiple store instances."""
    db_file = tmp_path / "test_pipeline.db"
    store1 = PipelinePersistenceStore(db_path=str(db_file))

    inc_id = f"TEST-INC-{uuid.uuid4().hex[:6]}"
    job_id = f"JOB-{uuid.uuid4().hex[:6]}"

    # Initialize stages
    records = store1.initialize_incident_stages(inc_id, job_id=job_id)
    assert len(records) == 18

    # Verify all required persistence fields exist
    rec0 = records[0]
    assert rec0.incident_id == inc_id
    assert rec0.job_id == job_id
    assert rec0.stage_id == "upload_accepted"
    assert rec0.status == "NOT_STARTED"
    assert rec0.retryability is True
    assert rec0.attempt_count == 0

    # Update stage with execution metrics
    rec0.status = "SUCCESS"
    rec0.started_at = "2026-10-29T10:00:00Z"
    rec0.completed_at = "2026-10-29T10:00:01Z"
    rec0.duration_ms = 1000.5
    rec0.input_references = ["bundle.zip"]
    rec0.output_references = ["art-001", "art-002"]
    rec0.warnings = ["Non-critical warning"]
    seq_id = store1.update_stage(rec0)
    assert seq_id > 0

    # Instantiate new store instance pointing to same SQLite database
    store2 = PipelinePersistenceStore(db_path=str(db_file))
    loaded = store2.get_stage(inc_id, "upload_accepted")
    assert loaded is not None
    assert loaded.status == "SUCCESS"
    assert loaded.duration_ms == 1000.5
    assert loaded.input_references == ["bundle.zip"]
    assert loaded.output_references == ["art-001", "art-002"]
    assert loaded.warnings == ["Non-critical warning"]


def test_monotonic_sequence_ids_and_events(tmp_path):
    """Verify event sequence IDs are strictly monotonic and orderable."""
    db_file = tmp_path / "test_events.db"
    store = PipelinePersistenceStore(db_path=str(db_file))

    inc_id = f"TEST-INC-{uuid.uuid4().hex[:6]}"
    store.initialize_incident_stages(inc_id)

    seq1 = store.record_event(inc_id, "EVENT_1", "stage_1", {"step": 1})
    seq2 = store.record_event(inc_id, "EVENT_2", "stage_2", {"step": 2})
    seq3 = store.record_event(inc_id, "EVENT_3", "stage_3", {"step": 3})

    assert seq1 < seq2 < seq3
    assert store.get_latest_sequence_id(inc_id) == seq3

    # Query events after seq1
    after_events = store.get_events(inc_id, after_sequence_id=seq1)
    assert len(after_events) == 2
    assert after_events[0]["sequence_id"] == seq2
    assert after_events[1]["sequence_id"] == seq3


def test_safe_stage_retry(tmp_path):
    """Verify retry safely resets stage to QUEUED and increments attempt count."""
    db_file = tmp_path / "test_retry.db"
    store = PipelinePersistenceStore(db_path=str(db_file))

    inc_id = f"TEST-INC-{uuid.uuid4().hex[:6]}"
    store.initialize_incident_stages(inc_id)

    stage = store.get_stage(inc_id, "verification")
    assert stage is not None
    stage.status = "FAILED"
    stage.error = "Invariant check failed"
    stage.error_code = "INVARIANT_VIOLATION"
    store.update_stage(stage)

    # Retry
    ok = store.reset_stage_for_retry(inc_id, "verification")
    assert ok is True

    updated = store.get_stage(inc_id, "verification")
    assert updated.status == "QUEUED"
    assert updated.error is None
    assert updated.error_code is None
    assert updated.attempt_count == 1


def test_cancellation_state_cascade(tmp_path):
    """Verify cancelling incident marks active stages CANCELLED and downstream BLOCKED."""
    db_file = tmp_path / "test_cancel.db"
    store = PipelinePersistenceStore(db_path=str(db_file))

    inc_id = f"TEST-INC-{uuid.uuid4().hex[:6]}"
    store.initialize_incident_stages(inc_id)

    # Set some stages
    s1 = store.get_stage(inc_id, "upload_accepted")
    s1.status = "SUCCESS"
    store.update_stage(s1)

    s2 = store.get_stage(inc_id, "archive_validated")
    s2.status = "RUNNING"
    store.update_stage(s2)

    store.cancel_incident_stages(inc_id, reason="Operator test abort")

    stages = store.get_stages(inc_id)
    stage_dict = {s.stage_id: s for s in stages}

    assert stage_dict["upload_accepted"].status == "SUCCESS"
    assert stage_dict["archive_validated"].status == "CANCELLED"
    assert stage_dict["archive_validated"].error == "Operator test abort"
    assert stage_dict["evidence_extracted"].status == "BLOCKED"


@pytest.mark.asyncio
async def test_api_events_with_sequence_id_and_reconciliation(test_user):
    """Verify /events API endpoint returns 18 stages, sequence ID, and historical events."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])

        # Create golden incident
        create_res = await client.post("/api/v1/incidents?golden=true")
        assert create_res.status_code == 200

        # Query events
        events_res = await client.get("/api/v1/incidents/CAU-0001/events")
        assert events_res.status_code == 200
        data = events_res.json()

        assert len(data["stages"]) == 18
        assert "sequence_id" in data
        assert "latest_sequence_id" in data
        current_seq = data["latest_sequence_id"]

        # Query events with after_sequence_id
        after_res = await client.get(f"/api/v1/incidents/CAU-0001/events?after_sequence_id={max(0, current_seq - 1)}")
        assert after_res.status_code == 200
        after_data = after_res.json()
        assert "events" in after_data

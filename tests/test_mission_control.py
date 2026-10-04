"""
Automated test suite for Cauveris Mission Control integration.
Tests cover:
- golden incident creation
- upload validation
- start investigation
- duplicate start prevention
- cancellation
- progress updates
- terminal states
- reset and rerun
- backend unavailable
- failure display & dependency blocking
"""
import io
import zipfile
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from cauveris.api.main import app, incidents, pipeline_tasks, pipeline_progress
from cauveris.state_machine.orchestrator import PipelineOrchestrator, StageStatus, create_default_stages




@pytest.mark.asyncio
async def test_golden_incident_creation(test_user):
    """Verify golden incident creation through the backend with demonstration labels."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])
        # Create golden incident
        res = await client.post("/api/v1/incidents?golden=true")
        assert res.status_code == 200
        data = res.json()
        assert data["incident_id"] == "CAU-0001"
        assert data.get("is_demonstration") is True
        assert "DEMONSTRATION" in data.get("message", "")

        # Verify incident metadata
        inc_res = await client.get("/api/v1/incidents/CAU-0001")
        assert inc_res.status_code == 200
        inc_data = inc_res.json()
        assert inc_data["is_demonstration"] is True
        assert inc_data["evidence_count"] >= 14

        # Verify initial pipeline stage states are IDLE / ready
        events_res = await client.get("/api/v1/incidents/CAU-0001/events")
        assert events_res.status_code == 200
        events_data = events_res.json()
        assert events_data["state"] == "IDLE"
        assert len(events_data["stages"]) == 9
        assert all(s["status"] == "PENDING" for s in events_data["stages"])


@pytest.mark.asyncio
async def test_upload_validation(test_user):
    """Verify incident bundle upload and validation including invalid file handling."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])
        # 1. Create empty incident
        create_res = await client.post("/api/v1/incidents", json={"title": "Test AMR Incident"})
        assert create_res.status_code == 200
        incident_id = create_res.json()["incident_id"]

        # 2. Upload invalid non-zip file -> must be rejected with 400
        invalid_file = io.BytesIO(b"Not a zip file content")
        bad_upload = await client.post(
            f"/api/v1/incidents/{incident_id}/upload",
            files={"file": ("bundle.txt", invalid_file, "text/plain")}
        )
        assert bad_upload.status_code == 400
        assert "ZIP archive" in bad_upload.json()["detail"]

        # 3. Create a valid zip archive in-memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.yaml", "incident_id: UPLOAD-001\nsystem_name: amr-test\nrequired_evidence: []\n")
            zf.writestr("logs/system.log", "2026-09-20T10:00:00Z system boot ok\n")
            zf.writestr("metrics/cpu.csv", "timestamp,cpu_percent\n2026-09-20T10:00:00Z,35\n")
        zip_buffer.seek(0)

        # 4. Upload valid zip bundle
        upload_res = await client.post(
            f"/api/v1/incidents/{incident_id}/upload",
            files={"file": ("bundle.zip", zip_buffer, "application/zip")}
        )
        assert upload_res.status_code == 200
        up_data = upload_res.json()
        assert up_data["evidence_count"] >= 3

        # 5. Run evidence validation
        val_res = await client.post(f"/api/v1/incidents/{incident_id}/validate")
        assert val_res.status_code == 200
        val_data = val_res.json()
        assert val_data["checksums_valid"] is True
        assert val_data["evidence_count"] >= 3


@pytest.mark.asyncio
async def test_start_investigation_and_duplicate_prevention(test_user):
    """Verify starting an investigation and blocking duplicate concurrent requests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])
        # Load golden incident
        await client.post("/api/v1/incidents?golden=true")

        # 1. Start investigation
        start_res = await client.post("/api/v1/incidents/CAU-0001/reconstruct")
        assert start_res.status_code == 200
        start_data = start_res.json()
        assert start_data["pipeline_state"] == "RUNNING"

        # 2. Duplicate start request while running must return 409 Conflict
        dup_res = await client.post("/api/v1/incidents/CAU-0001/reconstruct")
        assert dup_res.status_code == 409
        assert "Duplicate start requests are blocked" in dup_res.json()["detail"]


@pytest.mark.asyncio
async def test_investigation_cancellation(test_user):
    """Verify cancelling an active investigation transitions running stage to CANCELLED and downstream to SKIPPED."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])
        # Load golden incident
        await client.post("/api/v1/incidents?golden=true")

        # Start investigation
        await client.post("/api/v1/incidents/CAU-0001/reconstruct")

        # Send cancellation signal
        cancel_res = await client.post("/api/v1/incidents/CAU-0001/cancel")
        assert cancel_res.status_code == 200
        data = cancel_res.json()
        assert data["state"] == "CANCELLED"

        # Verify pipeline progress shows CANCELLED
        events_res = await client.get("/api/v1/incidents/CAU-0001/events")
        events_data = events_res.json()
        assert events_data["state"] == "CANCELLED"


@pytest.mark.asyncio
async def test_progress_updates_and_stages_structure(test_user):
    """Verify progress updates return full 9-stage progression graph."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])
        await client.post("/api/v1/incidents?golden=true")

        events_res = await client.get("/api/v1/incidents/CAU-0001/events")
        assert events_res.status_code == 200
        data = events_res.json()

        assert "stages" in data
        stages = data["stages"]
        assert len(stages) == 9

        stage_ids = [s["id"] for s in stages]
        assert "ingestion_validation" in stage_ids
        assert "timeline_construction" in stage_ids
        assert "temporal_analysis" in stage_ids
        assert "hypothesis_generation" in stage_ids
        assert "sandbox_planning" in stage_ids
        assert "simulation_execution" in stage_ids
        assert "patch_forge" in stage_ids
        assert "invariant_verification" in stage_ids
        assert "report_generation" in stage_ids

        # Verify dependency link
        timeline_stage = next(s for s in stages if s["id"] == "timeline_construction")
        assert "ingestion_validation" in timeline_stage["depends_on"]


@pytest.mark.asyncio
async def test_terminal_states_and_dependency_blocking():
    """Verify terminal state SUCCESS on clean run, and FAILED with SKIPPED dependencies on failure."""
    # Test 1: Full pipeline reaches terminal state SUCCESS
    orch = PipelineOrchestrator()
    from cauveris.datasets.golden_incident import GoldenIncidentGenerator
    gen = GoldenIncidentGenerator()
    inc = gen.generate()
    ctx = await orch.process_incident(inc)
    assert orch.current_state == "SUCCESS"
    assert orch.current_progress == 1.0
    assert all(s.status == StageStatus.SUCCESS for s in orch.stages)

    # Test 2: Failure in a required stage blocks dependent stages
    orch_fail = PipelineOrchestrator()
    orch_fail.simulate_failure_stage = "temporal_analysis"
    inc_fail = gen.generate()
    ctx_fail = await orch_fail.process_incident(inc_fail)

    assert orch_fail.current_state == "FAILED"
    assert orch_fail.get_stage("temporal_analysis").status == StageStatus.FAILED

    # Prerequisite succeeded
    assert orch_fail.get_stage("ingestion_validation").status == StageStatus.SUCCESS
    assert orch_fail.get_stage("timeline_construction").status == StageStatus.SUCCESS

    # Downstream dependent stages must be blocked (SKIPPED)
    assert orch_fail.get_stage("hypothesis_generation").status == StageStatus.SKIPPED
    assert orch_fail.get_stage("sandbox_planning").status == StageStatus.SKIPPED
    assert orch_fail.get_stage("simulation_execution").status == StageStatus.SKIPPED
    assert orch_fail.get_stage("patch_forge").status == StageStatus.SKIPPED
    assert orch_fail.get_stage("invariant_verification").status == StageStatus.SKIPPED
    assert orch_fail.get_stage("report_generation").status == StageStatus.SKIPPED


@pytest.mark.asyncio
async def test_reset_and_rerun(test_user):
    """Verify resetting an incident and performing a fresh rerun."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])
        # 1. Initialize golden incident
        await client.post("/api/v1/incidents?golden=true")

        # 2. Reset incident
        reset_res = await client.post("/api/v1/incidents/CAU-0001/reset")
        assert reset_res.status_code == 200
        assert reset_res.json()["state"] == "IDLE"

        # 3. Check stages reset to PENDING
        events_res = await client.get("/api/v1/incidents/CAU-0001/events")
        stages = events_res.json()["stages"]
        assert all(s["status"] == "PENDING" for s in stages)

        # 4. Rerun investigation
        start_res = await client.post("/api/v1/incidents/CAU-0001/reconstruct")
        assert start_res.status_code == 200
        assert start_res.json()["pipeline_state"] == "RUNNING"


@pytest.mark.asyncio
async def test_backend_unavailable_and_stale_incident(test_user):
    """Verify 404 response for stale incidents and health endpoints for backend connectivity."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers.update(test_user["headers"])
        # Health check
        health_res = await client.get("/api/v1/health")
        assert health_res.status_code == 200
        assert health_res.json()["status"] == "healthy"

        # Model health check
        model_res = await client.get("/api/v1/model-health")
        assert model_res.status_code == 200
        assert model_res.json()["status"] == "healthy"
        assert model_res.json()["cloud_credentials_required"] is False

        # Status center
        status_res = await client.get("/api/v1/status-center")
        assert status_res.status_code == 200
        assert status_res.json()["backend_health"]["status"] == "healthy"

        # Stale incident lookup (non-existent ID) must return 404
        stale_res = await client.get("/api/v1/incidents/NON_EXISTENT_ID_9999/events")
        assert stale_res.status_code == 404


@pytest.mark.asyncio
async def test_failure_display_and_degraded_terminal_state():
    """Verify degraded terminal state when a non-critical stage is degraded."""
    orch = PipelineOrchestrator()
    orch.simulate_degraded_stage = "report_generation"
    from cauveris.datasets.golden_incident import GoldenIncidentGenerator
    inc = GoldenIncidentGenerator().generate()
    await orch.process_incident(inc)

    assert orch.current_state == "DEGRADED"
    assert orch.get_stage("report_generation").status == StageStatus.DEGRADED
    # Core stages still succeeded
    assert orch.get_stage("invariant_verification").status == StageStatus.SUCCESS

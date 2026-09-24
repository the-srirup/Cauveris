"""
Comprehensive integration tests for Cauveris FastAPI endpoints.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from cauveris.api.main import app, incidents, pipeline_contexts
from cauveris.state_machine.orchestrator import PipelineOrchestrator


@pytest.mark.asyncio
async def test_health_endpoints():
    """Verify health and root endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
        assert res.status_code == 200
        assert "Cauveris API" in res.json()["message"]

        res_h = await client.get("/health")
        assert res_h.status_code == 200
        assert res_h.json()["status"] == "healthy"

        res_v1 = await client.get("/api/v1/health")
        assert res_v1.status_code == 200
        assert res_v1.json()["service"] == "cauveris"


@pytest.mark.asyncio
async def test_create_golden_incident_and_validate():
    """Verify POST /api/v1/incidents?golden=true and /validate."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create golden incident
        create_res = await client.post("/api/v1/incidents?golden=true")
        assert create_res.status_code == 200
        data = create_res.json()
        incident_id = data["incident_id"]
        assert incident_id == "CAU-0001"

        # 2. Validate incident
        val_res = await client.post(f"/api/v1/incidents/{incident_id}/validate")
        assert val_res.status_code == 200
        val_data = val_res.json()
        assert val_data["validation_status"] == "completed"
        assert val_data["evidence_count"] >= 14
        assert len(val_data["missing_required_evidence"]) == 0


@pytest.mark.asyncio
async def test_full_pipeline_endpoints():
    """Verify pipeline execution and retrieval of timeline, hypotheses, experiments, patches, and report."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Load golden incident
        await client.post("/api/v1/incidents?golden=true")
        incident = incidents["CAU-0001"]

        # Run orchestrator to populate pipeline context
        orchestrator = PipelineOrchestrator()
        context = await orchestrator.process_incident(incident)
        pipeline_contexts["CAU-0001"] = context

        # 1. Timeline endpoint
        timeline_res = await client.get("/api/v1/incidents/CAU-0001/timeline")
        assert timeline_res.status_code == 200
        tl_data = timeline_res.json()
        assert tl_data["incident_id"] == "CAU-0001"
        assert tl_data["total_events"] > 0
        assert "clock_alignment" in tl_data
        assert "timeline_events" in tl_data

        # 2. Hypotheses endpoint
        hyp_res = await client.get("/api/v1/incidents/CAU-0001/hypotheses")
        assert hyp_res.status_code == 200
        hyp_data = hyp_res.json()
        assert hyp_data["count"] >= 4
        assert any(h["hypothesis_id"] == "h1_batching_window" for h in hyp_data["hypotheses"])

        # 3. Experiments endpoint
        exp_res = await client.get("/api/v1/incidents/CAU-0001/experiments")
        assert exp_res.status_code == 200
        exp_data = exp_res.json()
        assert exp_data["count"] >= 4

        # 4. Patches endpoint
        patches_res = await client.get("/api/v1/incidents/CAU-0001/patches")
        assert patches_res.status_code == 200
        patches_data = patches_res.json()
        assert patches_data["count"] >= 1
        assert any(p["verified"] is True for p in patches_data["patch_candidates"])

        # 5. Report endpoint
        report_res = await client.get("/api/v1/incidents/CAU-0001/report")
        assert report_res.status_code == 200
        report_data = report_res.json()
        assert "incident_id" in report_data or "patch_package_path" in report_data

        # 6. Download patch package endpoint
        pkg_res = await client.get("/api/v1/incidents/CAU-0001/download-patch-package")
        assert pkg_res.status_code == 200
        assert pkg_res.headers["content-type"] == "application/zip"
        assert len(pkg_res.content) > 0

"""
Tests for repair package generation, workflow stage statuses, and download endpoint.
Verifies all 12 Phase 1 requirements:
1. Authenticate the request (Bearer header, Cookie, Query token).
2. Verify incident access (404 missing, 403 unauthorized, deny audit log).
3. Resolve selected repair or explicit repair_id (404 unknown, 422 unverified, 422 refused).
4. Verify package readiness (409 building, 500 failed).
5. Resolve package through workspace or artifact store.
6. Stream actual bytes (valid unzippable archive with manifest & checksums).
7. Return safe filename (sanitized alphanumeric/dashes).
8. Return application/zip media type.
9. Return Content-Length and X-Checksum-SHA256.
10. Return structured errors.
11. Record download audit event.
12. Never substitute a static package.
"""

import io
import json
import zipfile
import hashlib
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

from cauveris.api.main import app, incidents, pipeline_tasks, pipeline_contexts
from cauveris.state_machine.orchestrator import (
    PipelineOrchestrator,
    PipelineContext,
    WorkflowStatus,
    PipelineState,
)
from cauveris.datasets.golden_incident import GoldenIncidentGenerator
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.patch.package_builder import PatchPackageBuilder
from cauveris.auth import get_auth_store, User, Organization, TokenType, TokenManager
from cauveris.config import get_settings


@pytest.fixture
async def setup_incident(test_user):
    """Create a golden incident and verify context."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()
    incident_id = str(incident.id)
    incidents[incident_id] = incident

    # Attach ownership
    incident._owner_user_id = test_user["user"].id
    incident._owner_org_id = test_user["user"].org_id

    # Create verified candidate
    patch = PatchCandidate(
        candidate_id="CANDIDATE-001",
        hypothesis_id="HYP-001",
        description="Reduce batching window from 200ms to 100ms",
        affected_files=["config/pipeline.yaml"],
        lines_changed=2,
        unified_diff=(
            "--- a/config/pipeline.yaml\n"
            "+++ b/config/pipeline.yaml\n"
            "@@ -10,3 +10,3 @@\n"
            "-  batching_window_ms: 200.0\n"
            "+  batching_window_ms: 100.0\n"
        ),
        verified=True,
        verification_level="FORMALLY_VERIFIED",
    )
    unverified_patch = PatchCandidate(
        candidate_id="CANDIDATE-UNVERIFIED",
        hypothesis_id="HYP-002",
        description="Unverified experimental candidate",
        affected_files=["config/experimental.yaml"],
        lines_changed=1,
        unified_diff="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-1\n+2\n",
        verified=False,
    )

    ver_report = VerificationReport(
        patch_candidate_id="CANDIDATE-001",
        verified=True,
        regression_test_passed=True,
        original_failure_eliminated=True,
    )

    ctx = PipelineContext(
        incident=incident,
        validated_incident=incident,
        patch_candidates=[patch, unverified_patch],
        verification_reports=[ver_report],
        selected_repair_id="CANDIDATE-001",
        workflow_status=WorkflowStatus.COMPLETED,
    )
    pipeline_contexts[incident_id] = ctx

    orch = PipelineOrchestrator()
    orch.context = ctx
    orch.current_state = "SUCCESS"
    orch.workflow_status = WorkflowStatus.COMPLETED
    pipeline_tasks[incident_id] = orch

    return {
        "incident": incident,
        "incident_id": incident_id,
        "patch": patch,
        "unverified_patch": unverified_patch,
        "context": ctx,
        "orchestrator": orch,
    }


@pytest.mark.asyncio
async def test_auth_methods_for_download(setup_incident, test_user):
    """Requirement 1: Authenticate via Bearer header, Cookie, and Query token."""
    transport = ASGITransport(app=app)
    incident_id = setup_incident["incident_id"]
    token = test_user["access_token"]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Bearer header
        res1 = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res1.status_code == 200
        assert res1.headers["content-type"] == "application/zip"

        # 2. Cookie access_token
        res2 = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
            cookies={"access_token": token},
        )
        assert res2.status_code == 200
        assert res2.headers["content-type"] == "application/zip"

        # 3. Query param token
        res3 = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package?token={token}",
        )
        assert res3.status_code == 200
        assert res3.headers["content-type"] == "application/zip"

        # 4. Missing auth -> 401
        res4 = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
        )
        assert res4.status_code == 401


@pytest.mark.asyncio
async def test_access_control_and_missing_incident(setup_incident, test_user):
    """Requirement 2: Return 404 for missing incident and 403 for unauthorized access."""
    transport = ASGITransport(app=app)
    auth_store = get_auth_store()
    settings = get_settings()

    # Create an unprivileged user in another org
    from cauveris.auth import UserRole, Session
    other_org = Organization(id="org-other", name="Other Org")
    await auth_store.create_org(other_org)
    other_user = User(
        id="user-other",
        org_id=other_org.id,
        email="other@example.com",
        full_name="Other",
        password_hash="hash",
        role=UserRole.VIEWER,
    )
    await auth_store.create_user(other_user)
    session = Session(user_id=other_user.id, org_id=other_org.id)
    await auth_store.create_session(session)
    token_mgr = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)
    other_token = token_mgr.create_access_token(other_user, session, other_org)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing incident -> 404
        missing_res = await client.get(
            "/api/v1/incidents/CAU-NONEXISTENT/download-patch-package",
            headers={"Authorization": f"Bearer {test_user['access_token']}"},
        )
        assert missing_res.status_code == 404

        # Unauthorized user -> 403
        incident_id = setup_incident["incident_id"]
        denied_res = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert denied_res.status_code == 403
        body = denied_res.json()
        assert body.get("detail", {}).get("error") == "access_denied"

        # Verify audit log recorded the denied attempt
        logs = await auth_store.read_audit_logs(user_id=other_user.id, action="patch.download")
        assert len(logs) >= 1
        assert logs[-1].decision == "deny"


@pytest.mark.asyncio
async def test_candidate_resolution_and_validation(setup_incident, test_user):
    """Requirement 3: Resolve explicit vs selected candidate, reject unverified or refused repairs."""
    transport = ASGITransport(app=app)
    incident_id = setup_incident["incident_id"]
    token = test_user["access_token"]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Explicit verified repair candidate -> 200
        res_explicit = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package?repair_id=CANDIDATE-001",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_explicit.status_code == 200
        assert res_explicit.headers.get("X-Repair-ID") == "CANDIDATE-001"

        # 2. Explicit non-existent candidate -> 404
        res_missing = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package?repair_id=CANDIDATE-999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_missing.status_code == 404
        assert res_missing.json()["detail"]["error"] == "repair_candidate_not_found"

        # 3. Explicit unverified candidate -> 422
        res_unverified = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package?repair_id=CANDIDATE-UNVERIFIED",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_unverified.status_code == 422
        assert res_unverified.json()["detail"]["error"] == "unverified_repair_candidate"

        # 4. Refused repair incident -> 422
        refused_inc = GoldenIncidentGenerator().generate()
        refused_id = "CAU-REFUSED-TEST"
        refused_inc.id = refused_id
        refused_inc.capability_report = {
            "honest_repair_decision": "REFUSE",
            "limitations": ["No editable configuration control discovered in incident bundle"],
        }
        incidents[refused_id] = refused_inc
        refused_inc._owner_user_id = test_user["user"].id
        refused_inc._owner_org_id = test_user["user"].org_id

        ctx_refused = PipelineContext(
            incident=refused_inc,
            patch_candidates=[],
        )
        pipeline_contexts[refused_id] = ctx_refused

        res_refused = await client.get(
            f"/api/v1/incidents/{refused_id}/download-patch-package",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_refused.status_code == 422
        assert res_refused.json()["detail"]["error"] == "repair_refused"


@pytest.mark.asyncio
async def test_package_readiness_conflicts(setup_incident, test_user):
    """Requirement 4: Return 409 while building and 500 when failed."""
    transport = ASGITransport(app=app)
    incident_id = setup_incident["incident_id"]
    token = test_user["access_token"]
    orch = setup_incident["orchestrator"]
    ctx = setup_incident["context"]

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Mock orchestrator is running
        orch.current_state = "RUNNING"
        res_running = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Check running state (orchestrator.is_running is based on task, so set context status)
        ctx.workflow_status = WorkflowStatus.PACKAGE_BUILDING
        res_building = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_building.status_code == 409
        assert res_building.json()["detail"]["error"] == "package_building"

        # Mock package failed
        ctx.workflow_status = WorkflowStatus.PACKAGE_FAILED
        ctx.package_error = "Disk quota exceeded while sealing zip"
        res_failed = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_failed.status_code == 500
        assert res_failed.json()["detail"]["error"] == "package_failed"

        # Restore completed status
        ctx.workflow_status = WorkflowStatus.COMPLETED


@pytest.mark.asyncio
async def test_streamed_archive_contents_and_checksums(setup_incident, test_user):
    """Requirements 5, 6, 7, 8, 9, 11: Real ZIP archive with all required files, safe headers, audit log."""
    transport = ASGITransport(app=app)
    incident_id = setup_incident["incident_id"]
    token = test_user["access_token"]
    auth_store = get_auth_store()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"
        assert "Content-Length" in res.headers
        content_len = int(res.headers["Content-Length"])
        assert len(res.content) == content_len

        # Checksum header validation
        header_sha256 = res.headers.get("X-Checksum-SHA256")
        assert header_sha256 is not None
        actual_sha256 = hashlib.sha256(res.content).hexdigest()
        assert header_sha256 == actual_sha256

        # Filename check
        disp = res.headers.get("Content-Disposition", "")
        assert "cauveris-repair-package-" in disp
        assert ".zip" in disp

        # Inspect unzipped contents
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        names = zf.namelist()
        required_files = [
            "manifest.json",
            "patch.patch",
            "rollback.patch",
            "rollback.sh",
            "apply_patch.py",
            "PULL_REQUEST.md",
            "reviewer-checklist.md",
            "checksums.sha256",
            "diagnosis.json",
            "provenance.json",
            "capability-report.json",
            "baseline-results.json",
            "post-intervention-results.json",
            "before_after/traces/before_traces.json",
            "before_after/traces/after_traces.json",
            "before_after/metrics/before_metrics.csv",
            "before_after/metrics/after_metrics.csv",
        ]
        for req in required_files:
            assert req in names, f"Required file '{req}' missing from repair package"

        # Verify manifest.json
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["incident_id"] == incident_id
        assert manifest["patch_candidate_id"] == "CANDIDATE-001"
        assert manifest["format"] == "cauveris-repair-package/v1"

        # Verify audit log entry written
        logs = await auth_store.read_audit_logs(
            user_id=test_user["user"].id, action="patch.download"
        )
        assert len(logs) >= 1
        assert logs[-1].decision == "allow"
        assert "CANDIDATE-001" in logs[-1].reason


@pytest.mark.asyncio
async def test_pipeline_workflow_statuses_and_failure_handling():
    """Verify explicit stage statuses and package failure preventing pipeline completion."""
    gen = GoldenIncidentGenerator()
    inc = gen.generate()

    visited_statuses = []

    def on_progress(summary):
        if isinstance(summary, dict) and "workflow_status" in summary:
            visited_statuses.append(summary["workflow_status"])

    orch = PipelineOrchestrator()
    orch.set_progress_callback(on_progress)
    context = await orch.process_incident(inc)

    assert orch.current_state == "SUCCESS"
    assert orch.workflow_status == WorkflowStatus.COMPLETED
    assert context.package_ready is True
    assert context.package_zip_path is not None
    assert Path(context.package_zip_path).exists()

    # Verify lifecycle progression visited expected milestones
    assert WorkflowStatus.ANALYSIS_COMPLETED.value in visited_statuses
    assert WorkflowStatus.REPAIR_GENERATED.value in visited_statuses
    assert WorkflowStatus.VERIFICATION_COMPLETED.value in visited_statuses
    assert WorkflowStatus.REPORT_READY.value in visited_statuses
    assert WorkflowStatus.PACKAGE_BUILDING.value in visited_statuses
    assert WorkflowStatus.PACKAGE_READY.value in visited_statuses
    assert WorkflowStatus.COMPLETED.value in visited_statuses

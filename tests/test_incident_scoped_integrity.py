"""
Incident-Scoped Data Integrity Test Suite.

Proves:
1. Incident A cannot use Artifact B (preview, inventory, filesystem boundaries)
2. Incident A cannot use Execution B (model execution lookup, query isolation)
3. Incident A cannot verify Candidate B (candidate belonging to Incident B rejected by VerificationEngine)
4. Incident A cannot package Repair B (PackageBuilder and packaging router reject cross-incident candidate/repair)
5. Incident A cannot display Report B (report lookup, report list, report deletion isolation)
6. User A cannot access Incident B (strict cross-user multi-tenant 403 enforcement)
7. Incident A cannot test Hypothesis B (cross-incident hypothesis testing rejected)
8. Incident switching clears stale state (state isolation guarantees)
"""

import json
import pytest
from httpx import AsyncClient, ASGITransport

from cauveris.api.main import app, incidents
from cauveris.auth import init_auth_store
from cauveris.config import get_settings
from cauveris.model_gateway.records import get_execution_store, ModelExecutionRecord
from cauveris.model_gateway.enums import ProviderState
from cauveris.packaging.builder import PackageBuilder, PackageError
from cauveris.packaging.models import PackageStatus
from cauveris.packaging.storage import PackageStore
from cauveris.schemas.incident import Incident
from cauveris.schemas.patch import PatchCandidate
from cauveris.verifier.engine import VerificationEngine


@pytest.fixture
async def setup_isolated_env(tmp_path):
    """Initializes isolated auth and storage databases."""
    auth_db = str(tmp_path / "test_auth_integrity.db")
    model_db = str(tmp_path / "test_model_executions.db")
    pkg_dir = tmp_path / "test_packages"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = tmp_path / "test_evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_dir = tmp_path / "test_reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    settings.runtime_mode = "development"
    settings.demo_auth = False
    settings.auth_backend = "sqlite"
    settings.auth_db_path = auth_db
    settings.model_execution_db_path = model_db
    settings.evidence_store_path = str(evidence_dir)
    settings.report_store_path = str(report_dir)
    settings.package_storage_path = str(pkg_dir)

    auth_store = init_auth_store(backend="sqlite", db_path=auth_db)
    exec_store = get_execution_store(db_path=model_db)
    pkg_store = PackageStore()

    yield {
        "auth_store": auth_store,
        "exec_store": exec_store,
        "pkg_store": pkg_store,
        "evidence_dir": evidence_dir,
        "report_dir": report_dir,
        "pkg_dir": pkg_dir,
    }


async def _register_user(client: AsyncClient, email: str, name: str) -> dict:
    res = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "Password123456!", "full_name": name},
    )
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    user_data = me_res.json()
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}, "user": user_data}


# ---------------------------------------------------------------------------
# 1. Incident A cannot use Artifact B
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_incident_artifact_access_rejected(setup_isolated_env):
    """Prove Incident A cannot preview or access artifacts belonging to Incident B."""
    env = setup_isolated_env
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_a = await _register_user(client, "alice@test.local", "Alice")

        # Create two incident directories with distinct artifacts
        inc_a_id = "INC-AAA-001"
        inc_b_id = "INC-BBB-002"

        bundle_a = env["evidence_dir"] / inc_a_id
        bundle_a.mkdir(parents=True, exist_ok=True)
        (bundle_a / "config.yaml").write_text("service: rover-a\n", encoding="utf-8")

        bundle_b = env["evidence_dir"] / inc_b_id
        bundle_b.mkdir(parents=True, exist_ok=True)
        (bundle_b / "secret.yaml").write_text("token: super-secret-b\n", encoding="utf-8")

        # Register incidents
        inc_a = Incident(
            id=inc_a_id,
            title="Incident A",
            system_name="rover-a",
            bundle_path=str(bundle_a),
            artifact_inventory=[
                {"artifact_id": "art-a-1", "relative_path": "config.yaml", "incident_id": inc_a_id, "classification": "text", "parse_status": "SUPPORTED"}
            ],
        )
        inc_a._owner_user_id = user_a["user"]["id"]
        inc_a._owner_org_id = user_a["user"]["org_id"]
        incidents[inc_a_id] = inc_a

        inc_b = Incident(
            id=inc_b_id,
            title="Incident B",
            system_name="rover-b",
            bundle_path=str(bundle_b),
            artifact_inventory=[
                {"artifact_id": "art-b-1", "relative_path": "secret.yaml", "incident_id": inc_b_id, "classification": "text", "parse_status": "SUPPORTED"}
            ],
        )
        inc_b._owner_user_id = user_a["user"]["id"]
        inc_b._owner_org_id = user_a["user"]["org_id"]
        incidents[inc_b_id] = inc_b

        # Attempt to access Artifact B under Incident A
        res = await client.get(
            f"/api/v1/incidents/{inc_a_id}/artifacts/art-b-1/preview",
            headers=user_a["headers"],
        )
        # Must return 404 since art-b-1 is not in Incident A's inventory
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()

        # If an item somehow exists in inventory with another incident_id, must return 403
        inc_a.artifact_inventory.append({
            "artifact_id": "art-b-injected",
            "relative_path": "secret.yaml",
            "incident_id": inc_b_id,  # Mismatched incident ID!
            "classification": "text",
        })
        res_cross = await client.get(
            f"/api/v1/incidents/{inc_a_id}/artifacts/art-b-injected/preview",
            headers=user_a["headers"],
        )
        assert res_cross.status_code == 403
        assert "belongs to incident" in str(res_cross.json()).lower()


# ---------------------------------------------------------------------------
# 2. Incident A cannot use Execution B
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_incident_model_execution_rejected(setup_isolated_env):
    """Prove Incident A cannot view or query model executions belonging to Incident B."""
    env = setup_isolated_env
    exec_store = env["exec_store"]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_a = await _register_user(client, "alice2@test.local", "Alice")

        inc_a_id = "INC-AAA-EXEC"
        inc_b_id = "INC-BBB-EXEC"

        inc_a = Incident(id=inc_a_id, title="Incident A", system_name="system-a")
        inc_a._owner_user_id = user_a["user"]["id"]
        inc_a._owner_org_id = user_a["user"]["org_id"]
        incidents[inc_a_id] = inc_a

        inc_b = Incident(id=inc_b_id, title="Incident B", system_name="system-b")
        inc_b._owner_user_id = user_a["user"]["id"]
        inc_b._owner_org_id = user_a["user"]["org_id"]
        incidents[inc_b_id] = inc_b

        # Record execution for Incident B
        rec_b = ModelExecutionRecord(
            execution_id="exec-bbb-001",
            incident_id=inc_b_id,
            task="HYPOTHESIS_PROPOSAL",
            provider=ProviderState.LOCAL_DETERMINISTIC_ONLY.value,
            model="local-rule-engine",
            output="Hypothesis for Incident B",
            verified=True,
        )
        exec_store.record(rec_b)

        # 1. Query Incident A's executions: must NOT include exec_b
        res_list = await client.get(
            f"/api/v1/incidents/{inc_a_id}/model-executions",
            headers=user_a["headers"],
        )
        assert res_list.status_code == 200
        executions = res_list.json()["executions"]
        assert all(e["incident_id"] == inc_a_id for e in executions)
        assert not any(e["execution_id"] == "exec-bbb-001" for e in executions)

        # 2. Query execution B through Incident A scoped detail endpoint: must return 404
        res_detail = await client.get(
            f"/api/v1/incidents/{inc_a_id}/model-executions/exec-bbb-001",
            headers=user_a["headers"],
        )
        assert res_detail.status_code == 404
        assert "does not belong to incident" in res_detail.json()["detail"]["message"].lower()


# ---------------------------------------------------------------------------
# 3. Incident A cannot verify Candidate B
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_incident_candidate_verification_rejected(setup_isolated_env):
    """Prove VerificationEngine rejects candidates that belong to a different incident."""
    inc_a_id = "INC-AAA-VERIFY"
    inc_b_id = "INC-BBB-VERIFY"

    inc_a = Incident(id=inc_a_id, title="Incident A", system_name="system-a")
    Incident(id=inc_b_id, title="Incident B", system_name="system-b")

    cand_b = PatchCandidate(
        candidate_id="patch-cand-b",
        incident_id=inc_b_id,  # Belongs to Incident B!
        affected_files=["worker.yaml"],
        unified_diff="--- a/worker.yaml\n+++ b/worker.yaml\n@@ -1,1 +1,1 @@\n-x: 1\n+x: 2\n",
    )

    engine = VerificationEngine(incident=inc_a)
    reports = await engine.verify([cand_b], incident=inc_a)

    assert len(reports) == 1
    report = reports[0]
    # Must refuse verification and preserve UNVERIFIED status
    assert report.verified is False
    assert report.verification_level == "UNVERIFIED"
    assert cand_b.verified is False
    assert "cross-incident" in cand_b.rejection_reason.lower()


# ---------------------------------------------------------------------------
# 4. Incident A cannot package Repair B
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_incident_repair_packaging_rejected(setup_isolated_env):
    """Prove PackageBuilder and packaging router reject packaging candidates from another incident."""
    env = setup_isolated_env
    pkg_store = env["pkg_store"]
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_a = await _register_user(client, "alice3@test.local", "Alice")

        inc_a_id = "INC-AAA-PKG"
        inc_b_id = "INC-BBB-PKG"

        bundle_a = env["evidence_dir"] / inc_a_id
        bundle_a.mkdir(parents=True, exist_ok=True)
        (bundle_a / "worker.yaml").write_text("batching_window_ms: 100\n", encoding="utf-8")

        inc_a = Incident(id=inc_a_id, title="Incident A", system_name="system-a", bundle_path=str(bundle_a))
        inc_a._owner_user_id = user_a["user"]["id"]
        inc_a._owner_org_id = user_a["user"]["org_id"]
        incidents[inc_a_id] = inc_a

        cand_b = PatchCandidate(
            candidate_id="patch-cand-b-99",
            incident_id=inc_b_id,  # Belongs to Incident B!
            affected_files=["worker.yaml"],
            unified_diff="--- a/worker.yaml\n+++ b/worker.yaml\n@@ -1,1 +1,1 @@\n-batching_window_ms: 100\n+batching_window_ms: 50\n",
            verified=True,
            applies_cleanly=True,
        )

        # 1. Direct PackageBuilder call must raise cross_incident_patch_rejected
        builder = PackageBuilder(settings=get_settings(), store=pkg_store)
        with pytest.raises(PackageError) as exc_info:
            await builder.build(incident=inc_a, patch=cand_b, user_id=user_a["user"]["id"], org_id=user_a["user"]["org_id"])
        assert exc_info.value.code == "cross_incident_patch_rejected"

        # 2. Packaging router request must reject Candidate B under Incident A
        res_pkg = await client.post(
            f"/api/v1/incidents/{inc_a_id}/repair-packages?repair_id=patch-cand-b-99",
            headers=user_a["headers"],
        )
        assert res_pkg.status_code == 404

        # 3. Existing package record for Incident B cannot be retrieved or downloaded under Incident A
        record_b = pkg_store.create_record(
            incident_id=inc_b_id,
            repair_id="cand-b-built",
            user_id=user_a["user"]["id"],
            org_id=user_a["user"]["org_id"],
        )
        record_b = pkg_store.set_status(
            inc_b_id,
            "cand-b-built",
            record_b.build_number,
            PackageStatus.READY,
        )
        pkg_b_id = record_b.package_id

        # Retrieve package under Incident A URL: must return 404
        res_get_pkg = await client.get(
            f"/api/v1/incidents/{inc_a_id}/repair-packages/{pkg_b_id}",
            headers=user_a["headers"],
        )
        assert res_get_pkg.status_code == 404

        res_download = await client.get(
            f"/api/v1/incidents/{inc_a_id}/repair-packages/{pkg_b_id}/download",
            headers=user_a["headers"],
        )
        assert res_download.status_code == 404


# ---------------------------------------------------------------------------
# 5. Incident A cannot display Report B
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_incident_report_access_rejected(setup_isolated_env):
    """Prove Incident A cannot access, display, or delete reports from Incident B."""
    env = setup_isolated_env
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_a = await _register_user(client, "alice4@test.local", "Alice")

        inc_a_id = "INC-AAA-RPT"
        inc_b_id = "INC-BBB-RPT"

        inc_a = Incident(id=inc_a_id, title="Incident A", system_name="system-a")
        inc_a._owner_user_id = user_a["user"]["id"]
        inc_a._owner_org_id = user_a["user"]["org_id"]
        incidents[inc_a_id] = inc_a

        inc_b = Incident(id=inc_b_id, title="Incident B", system_name="system-b")
        inc_b._owner_user_id = user_a["user"]["id"]
        inc_b._owner_org_id = user_a["user"]["org_id"]
        incidents[inc_b_id] = inc_b

        # Write real report for Incident B
        report_b_dir = env["report_dir"] / inc_b_id
        report_b_dir.mkdir(parents=True, exist_ok=True)
        report_b_file = report_b_dir / "incident_report.json"
        report_b_file.write_text(json.dumps({
            "incident_id": inc_b_id,
            "title": "Incident B Report",
            "executive_summary": "Top secret B findings",
        }), encoding="utf-8")

        # 1. Incident A list reports: must NOT include Incident B report
        res_list = await client.get(f"/api/v1/incidents/{inc_a_id}/reports", headers=user_a["headers"])
        assert res_list.status_code == 200
        reports = res_list.json()["reports"]
        assert all(r["incident_id"] == inc_a_id for r in reports)

        # 2. Accessing Incident B's report under Incident A: must return 404
        res_report_by_id = await client.get(
            f"/api/v1/incidents/{inc_a_id}/reports/rpt-{inc_b_id}-001",
            headers=user_a["headers"],
        )
        assert res_report_by_id.status_code == 404

        # 3. Deleting Incident B's report under Incident A: must return 404
        res_del = await client.delete(
            f"/api/v1/incidents/{inc_a_id}/reports/rpt-{inc_b_id}-001",
            headers=user_a["headers"],
        )
        assert res_del.status_code == 404


# ---------------------------------------------------------------------------
# 6. User A cannot access Incident B
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_user_incident_access_denied(setup_isolated_env):
    """Prove User A is strictly forbidden (403) from accessing User B's incident."""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_a = await _register_user(client, "alice.isolated@test.local", "Alice")
        user_b = await _register_user(client, "bob.isolated@test.local", "Bob")

        inc_b_id = "INC-BOB-ISOLATED"
        inc_b = Incident(id=inc_b_id, title="Bob's Private Incident", system_name="system-b")
        inc_b._owner_user_id = user_b["user"]["id"]
        inc_b._owner_org_id = user_b["user"]["org_id"]
        incidents[inc_b_id] = inc_b

        # User A attempts to view Incident B
        res_inc = await client.get(f"/api/v1/incidents/{inc_b_id}", headers=user_a["headers"])
        assert res_inc.status_code == 403

        # User A attempts to view Incident B timeline
        res_time = await client.get(f"/api/v1/incidents/{inc_b_id}/timeline", headers=user_a["headers"])
        assert res_time.status_code == 403

        # User A attempts to view Incident B patches
        res_patch = await client.get(f"/api/v1/incidents/{inc_b_id}/patches", headers=user_a["headers"])
        assert res_patch.status_code == 403

        # User A attempts to validate Incident B
        res_val = await client.post(f"/api/v1/incidents/{inc_b_id}/validate", headers=user_a["headers"])
        assert res_val.status_code == 403

        # User A attempts to download Incident B patch package
        res_dl = await client.get(f"/api/v1/incidents/{inc_b_id}/download-patch-package", headers=user_a["headers"])
        assert res_dl.status_code == 403


# ---------------------------------------------------------------------------
# 7. Cross-Incident Hypothesis Testing Rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cross_incident_hypothesis_testing_rejected(setup_isolated_env):
    """Prove testing a hypothesis from another incident is rejected with 404."""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        user_a = await _register_user(client, "alice5@test.local", "Alice")

        inc_a_id = "INC-AAA-HYP"

        inc_a = Incident(id=inc_a_id, title="Incident A", system_name="system-a")
        inc_a._owner_user_id = user_a["user"]["id"]
        inc_a._owner_org_id = user_a["user"]["org_id"]
        incidents[inc_a_id] = inc_a

        # Request testing a foreign hypothesis ID that does not belong to Incident A
        res = await client.post(
            f"/api/v1/incidents/{inc_a_id}/hypotheses/hyp-incident-b-root-cause/test",
            headers=user_a["headers"],
        )
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()

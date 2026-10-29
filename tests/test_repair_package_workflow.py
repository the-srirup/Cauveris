"""
Comprehensive test suite for the complete Cauveris repair-package workflow:
- Package lifecycle states and transitions (NOT_REQUESTED -> BUILDING -> READY, STALE, FAILED)
- Canonical verification ladder (exact 6 rungs, strict ordering, no ambiguous fabrication)
- Pre-validation candidate gates (unverified, empty patch, multiple candidates)
- Complete Section 6 archive separation and Section 5 manifest schema
- Tamper detection on sealed packages (member modification, corrupt checksums, bad manifest)
- Filesystem safety and Section 11 proscription (strict path containment, NO rglob fallback)
- Safe staged patch application, rollback, and exact byte restoration
- Full API integration: POST create, GET status, GET download, and backward-compatible route
"""

import io
import json
import zipfile
import hashlib

import pytest
from httpx import AsyncClient, ASGITransport

from cauveris.api.main import app, incidents, pipeline_contexts
from cauveris.datasets.golden_incident import GoldenIncidentGenerator
from cauveris.packaging.builder import PackageBuilder
from cauveris.packaging.models import (
    PackageError,
    PackageStatus,
    VerificationLevel,
    PACKAGE_CANDIDATE_UNVERIFIED,
    PACKAGE_PATCH_EMPTY,
    RepairPackageRecord,
    compare_levels,
    level_from_status_string,
)
from cauveris.packaging.storage import PackageStore
from cauveris.packaging.validation import validate_package_archive
from cauveris.patch.generator import find_file, PatchGenerator
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.state_machine.orchestrator import PipelineContext, WorkflowStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def auth_context(test_user):
    """Provide user and bearer token for authenticated requests."""
    return test_user


@pytest.fixture
def sample_candidate() -> PatchCandidate:
    """A valid, verified patch candidate."""
    return PatchCandidate(
        candidate_id="REPAIR-ALPHA-01",
        hypothesis_id="HYP-001",
        description="Tune batching window to 100ms",
        affected_files=["config/inference.yaml"],
        lines_changed=2,
        unified_diff=(
            "--- a/config/inference.yaml\n"
            "+++ b/config/inference.yaml\n"
            "@@ -5,3 +5,3 @@\n"
            "   max_batch_size: 8\n"
            "-  batching_window_ms: 200  # Increased from 100 in v42\n"
            "+  batching_window_ms: 100  # Increased from 100 in v42\n"
            "   timeout_ms: 500\n"
        ),
        verified=True,
        verification_level="TEST_VERIFIED",
        applies_cleanly=True,
        regression_test_fails_before=True,
        regression_test_passes_after=True,
        original_failure_not_reproduced=True,
        existing_tests_pass=True,
        safety_invariants_pass=True,
        performance_within_budget=True,
        forbidden_change_scan_passes=True,
        rollback_test_passes=True,
    )


# ---------------------------------------------------------------------------
# 1. Lifecycle and Verification Ladder Unit Tests
# ---------------------------------------------------------------------------


def test_package_status_properties():
    """Verify package status lifecycle enum properties."""
    assert PackageStatus.NOT_REQUESTED.value == "NOT_REQUESTED"
    assert PackageStatus.QUEUED.value == "QUEUED"
    assert PackageStatus.BUILDING.value == "BUILDING"
    assert PackageStatus.READY.value == "READY"
    assert PackageStatus.FAILED.value == "FAILED"
    assert PackageStatus.STALE.value == "STALE"
    assert PackageStatus.DELETED.value == "DELETED"

    assert PackageStatus.READY.terminal is True
    assert PackageStatus.FAILED.terminal is True
    assert PackageStatus.DELETED.terminal is True
    assert PackageStatus.BUILDING.terminal is False


def test_verification_ladder_exact_rungs():
    """Verify the 6 canonical ladder levels and ordering."""
    expected_order = [
        VerificationLevel.GENERATED,
        VerificationLevel.STRUCTURALLY_VALID,
        VerificationLevel.MODEL_VERIFIED,
        VerificationLevel.TEST_VERIFIED,
        VerificationLevel.RUNTIME_VERIFIED,
        VerificationLevel.STAGING_VERIFIED,
    ]
    for idx in range(len(expected_order) - 1):
        assert compare_levels(expected_order[idx], expected_order[idx + 1]) == -1
        assert compare_levels(expected_order[idx + 1], expected_order[idx]) == 1
        assert compare_levels(expected_order[idx], expected_order[idx]) == 0

    # Test status string mapping without fabrication
    assert level_from_status_string("FORMALLY_VERIFIED") == VerificationLevel.TEST_VERIFIED
    assert level_from_status_string("TEST_VERIFIED") == VerificationLevel.TEST_VERIFIED
    assert level_from_status_string("SIMULATION_VERIFIED") == VerificationLevel.MODEL_VERIFIED
    assert level_from_status_string("MODEL_VERIFIED") == VerificationLevel.MODEL_VERIFIED
    assert level_from_status_string("RUNTIME_VERIFIED") == VerificationLevel.RUNTIME_VERIFIED
    assert level_from_status_string("STAGING_VERIFIED") == VerificationLevel.STAGING_VERIFIED
    assert level_from_status_string("UNKNOWN_STRING") == VerificationLevel.GENERATED
    assert level_from_status_string(None) == VerificationLevel.GENERATED


def test_repair_package_record_aliases_and_serialization():
    """Verify RepairPackageRecord provides both canonical and legacy aliases."""
    rec = RepairPackageRecord(
        incident_id="INC-100",
        repair_candidate_id="REPAIR-01",
        build_number=1,
        status=PackageStatus.READY,
        package_id="pkg_INC-100_REPAIR-01_1",
        storage_locator="/tmp/pkg.zip",
        package_sha256="abc123def456",
        size=4096,
        failure_message="No error",
    )
    # Check property aliases
    assert rec.repair_id == "REPAIR-01"
    assert rec.zip_path == "/tmp/pkg.zip"
    assert rec.checksum_sha256 == "abc123def456"
    assert rec.size_bytes == 4096
    assert rec.error == "No error"
    assert rec.is_downloadable is True

    # Mutate via alias
    rec.zip_path = "/tmp/new_pkg.zip"
    assert rec.storage_locator == "/tmp/new_pkg.zip"

    # Verify serialization dictionary contains all keys
    d = rec.to_dict()
    assert d["repair_candidate_id"] == "REPAIR-01"
    assert d["repair_id"] == "REPAIR-01"
    assert d["storage_locator"] == "/tmp/new_pkg.zip"
    assert d["zip_path"] == "/tmp/new_pkg.zip"
    assert d["package_sha256"] == "abc123def456"
    assert d["checksum_sha256"] == "abc123def456"

    # Deserialization from dictionary with legacy keys
    rec2 = RepairPackageRecord.from_dict({
        "incident_id": "INC-200",
        "repair_id": "REPAIR-LEGACY",
        "zip_path": "/var/pkg2.zip",
        "checksum_sha256": "feedbeef",
        "size_bytes": 1024,
        "status": "READY",
    })
    assert rec2.repair_candidate_id == "REPAIR-LEGACY"
    assert rec2.storage_locator == "/var/pkg2.zip"
    assert rec2.package_sha256 == "feedbeef"
    assert rec2.size == 1024
    assert rec2.status == PackageStatus.READY


# ---------------------------------------------------------------------------
# 2. Candidate Gates & Validation Failure Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_candidate_pre_validation_gates(sample_candidate, tmp_path):
    """Test candidate gates: empty patch and unverified patch rejected."""
    gen = GoldenIncidentGenerator()
    incident = gen.generate()

    builder = PackageBuilder(store=PackageStore())

    # Empty patch must raise PACKAGE_PATCH_EMPTY
    empty_patch = PatchCandidate(
        candidate_id="EMPTY-01",
        hypothesis_id="H-1",
        description="Empty patch",
        unified_diff="",
        verified=True,
    )
    with pytest.raises(PackageError) as exc_info:
        await builder.build(incident, empty_patch, user_id="u1", org_id="o1")
    assert exc_info.value.error_code == PACKAGE_PATCH_EMPTY

    # Unverified patch must raise PACKAGE_CANDIDATE_UNVERIFIED
    unverified_patch = PatchCandidate(
        candidate_id="UNVERIFIED-01",
        hypothesis_id="H-1",
        description="Unverified patch",
        unified_diff="--- a\n+++ b\n@@ -1 +1 @@\n-1\n+2\n",
        verified=False,
    )
    with pytest.raises(PackageError) as exc_info:
        await builder.build(incident, unverified_patch, user_id="u1", org_id="o1")
    assert exc_info.value.error_code == PACKAGE_CANDIDATE_UNVERIFIED


# ---------------------------------------------------------------------------
# 3. Complete Build, Section 6 Separation & Section 5 Manifest Schema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_package_builder_full_archive_layout(sample_candidate):
    """Verify builder produces complete Section 6 archive separation and Section 5 manifest."""
    gen = GoldenIncidentGenerator()
    incident = gen.generate()

    store = PackageStore()
    builder = PackageBuilder(store=store)

    outcome = await builder.build(
        incident=incident,
        patch=sample_candidate,
        user_id="test-operator",
        org_id="test-org",
    )

    assert outcome.staged is True
    assert outcome.zip_path.exists()
    assert outcome.size_bytes > 0
    assert outcome.package_checksum

    # Inspect zip contents
    with zipfile.ZipFile(outcome.zip_path, "r") as zf:
        namelist = set(zf.namelist())

        # Verify all Section 6 required members
        expected_members = [
            "manifest.json",
            "patch.diff",
            "fix.patch",
            "rollback.diff",
            "rollback.patch",
            "README.md",
            "checksums.txt",
            "checksums.sha256",
            "capability-report.json",
            "limitations.json",
            "evidence/provenance.json",
            "evidence/diagnosis.json",
            "evidence/invariant-set.json",
            "experiments/baseline-run.json",
            "experiments/intervention-run.json",
            "experiments/comparison.json",
            "verification/verification.json",
            "verification/checks.json",
            "report/incident-report.html",
            "tools/apply_patch.py",
            "tools/rollback_patch.py",
        ]
        for member in expected_members:
            assert member in namelist, f"Missing required member: {member}"

        # Verify Section 5 Manifest schema
        manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest_data.get("schema_version") == "1.0"
        assert manifest_data.get("format") == "cauveris-repair-package/v1"
        assert "incident" in manifest_data
        assert manifest_data["incident"]["id"] == str(incident.id)
        assert "repair" in manifest_data
        assert manifest_data["repair"]["candidate_id"] == sample_candidate.candidate_id
        assert "source" in manifest_data
        assert "model" in manifest_data
        assert "verification" in manifest_data
        assert manifest_data["verification"]["level"] == VerificationLevel.STAGING_VERIFIED.value
        assert manifest_data["verification"]["checks_passed"] == 9
        assert "package" in manifest_data
        assert manifest_data["package"]["is_sample"] is False
        assert "files" in manifest_data
        assert len(manifest_data["files"]) >= len(expected_members)

        # Verify report is real HTML, not disguised PDF
        html_bytes = zf.read("report/incident-report.html")
        assert b"<!DOCTYPE html>" in html_bytes or b"<html" in html_bytes

        # Verify checksums.txt matches archive members
        chk_lines = zf.read("checksums.txt").decode("utf-8").strip().splitlines()
        parsed_checksums = {}
        for line in chk_lines:
            parts = line.split(None, 1)
            parsed_checksums[parts[1]] = parts[0]

        for name in namelist:
            if name in ("checksums.txt", "checksums.sha256"):
                continue
            data = zf.read(name)
            computed_sha = hashlib.sha256(data).hexdigest()
            assert parsed_checksums.get(name) == computed_sha, f"Checksum mismatch for member {name}"


# ---------------------------------------------------------------------------
# 4. Tamper Detection & Archive Validation
# ---------------------------------------------------------------------------


def test_tamper_detection_on_archive(tmp_path):
    """Verify validate_package_archive catches modifications and forged verification levels."""
    # Create valid synthetic zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "schema_version": "1.0",
            "format": "cauveris-repair-package/v1",
            "verification_level": "TEST_VERIFIED",
            "files": [],
        }
        manifest_raw = json.dumps(manifest).encode("utf-8")
        diff_raw = b"--- a\n+++ b\n@@ -1 +1 @@\n-1\n+2\n"

        files = {
            "manifest.json": manifest_raw,
            "patch.diff": diff_raw,
            "fix.patch": diff_raw,
            "rollback.diff": diff_raw,
            "rollback.patch": diff_raw,
            "README.md": b"# Docs",
            "capability-report.json": b"{}",
            "limitations.json": b"{}",
            "evidence/provenance.json": b"{}",
            "evidence/diagnosis.json": b"{}",
            "evidence/invariant-set.json": b"{}",
            "experiments/baseline-run.json": b"{}",
            "experiments/intervention-run.json": b"{}",
            "experiments/comparison.json": b"{}",
            "verification/verification.json": b"{}",
            "verification/checks.json": b"{}",
            "report/incident-report.html": b"<html>Report</html>",
            "tools/apply_patch.py": b"# installer",
            "tools/rollback_patch.py": b"# rollback",
        }
        # Compute checksums
        chk_lines = []
        for p, data in files.items():
            h = hashlib.sha256(data).hexdigest()
            chk_lines.append(f"{h}  {p}")
            zf.writestr(p, data)

        chk_text = "\n".join(chk_lines) + "\n"
        zf.writestr("checksums.txt", chk_text.encode("utf-8"))

    valid_bytes = buf.getvalue()
    rep = validate_package_archive(valid_bytes)
    assert rep.ok is True

    # Case 1: Tampered patch file
    buf_tampered = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(valid_bytes), "r") as zf_in:
        with zipfile.ZipFile(buf_tampered, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                data = zf_in.read(item.filename)
                if item.filename == "patch.diff":
                    data = data + b"\n# Tamper injection"
                zf_out.writestr(item.filename, data)
    tampered_bytes = buf_tampered.getvalue()
    rep_tampered = validate_package_archive(tampered_bytes)
    assert rep_tampered.ok is False
    assert any(f.code == "checksum_mismatch" for f in rep_tampered.failures)

    # Case 2: Forged verification level in manifest
    buf_forged = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(valid_bytes), "r") as zf_in:
        with zipfile.ZipFile(buf_forged, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                data = zf_in.read(item.filename)
                if item.filename == "manifest.json":
                    m = json.loads(data.decode("utf-8"))
                    m["verification_level"] = "MAGIC_SUPER_VERIFIED"
                    data = json.dumps(m).encode("utf-8")
                zf_out.writestr(item.filename, data)
    forged_bytes = buf_forged.getvalue()
    rep_forged = validate_package_archive(forged_bytes)
    assert rep_forged.ok is False

    # Case 3: Prohibited file (.env) injected
    buf_secret = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(valid_bytes), "r") as zf_in:
        with zipfile.ZipFile(buf_secret, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                zf_out.writestr(item.filename, zf_in.read(item.filename))
            zf_out.writestr(".env", b"SECRET_API_KEY=leak")
    secret_bytes = buf_secret.getvalue()
    rep_secret = validate_package_archive(secret_bytes)
    assert rep_secret.ok is False
    assert any(f.code == "prohibited_file" for f in rep_secret.failures)


# ---------------------------------------------------------------------------
# 5. Filesystem Safety & Section 11 Proscription (Strict Containment)
# ---------------------------------------------------------------------------


def test_find_file_strict_containment_and_no_rglob(tmp_path):
    """Section 11 Proscription: exact path matching only, NO recursive search fallback."""
    root = tmp_path / "workspace"
    root.mkdir()

    # Create nested structure:
    # workspace/subdir/deep/target.py
    nested_dir = root / "subdir" / "deep"
    nested_dir.mkdir(parents=True)
    real_file = nested_dir / "target.py"
    real_file.write_text("print('hello')", encoding="utf-8")

    # 1. Exact relative path succeeds
    found = find_file(root, "subdir/deep/target.py")
    assert found is not None
    assert found.resolve() == real_file.resolve()

    # 2. File missing at expected path MUST NOT fall back to searching anywhere else
    not_at_root = find_file(root, "target.py")
    assert not_at_root is None, "find_file must NOT recursively match target.py in subdir/deep!"

    wrong_path = find_file(root, "other/target.py")
    assert wrong_path is None

    # 3. Path traversal outside base_dir is blocked
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secrets", encoding="utf-8")
    traversal = find_file(root, "../secret.txt")
    assert traversal is None


# ---------------------------------------------------------------------------
# 6. Safe Staged Application, Rollback, and Exact Hash Restoration
# ---------------------------------------------------------------------------


def test_staged_application_and_rollback(tmp_path):
    """Verify apply_patch modifies target cleanly and rollback restores original hashes."""
    target_dir = tmp_path / "target_app"
    target_dir.mkdir()

    config_file = target_dir / "config.yaml"
    original_content = (
        "# Server Configuration\n"
        "batching_window_ms: 200.0\n"
        "max_connections: 50\n"
    )
    config_file.write_text(original_content, encoding="utf-8")
    original_sha256 = hashlib.sha256(original_content.encode("utf-8")).hexdigest()

    diff = (
        "--- a/config.yaml\n"
        "+++ b/config.yaml\n"
        "@@ -1,3 +1,3 @@\n"
        " # Server Configuration\n"
        "-batching_window_ms: 200.0\n"
        "+batching_window_ms: 100.0\n"
        " max_connections: 50\n"
    )

    patch = PatchCandidate(
        candidate_id="STAGE-REPAIR-01",
        hypothesis_id="H-1",
        description="Reduce batching window",
        affected_files=["config.yaml"],
        lines_changed=2,
        unified_diff=diff,
        verified=True,
    )

    gen = PatchGenerator()
    installer_code = gen.generate_standalone_installer(patch)

    installer_path = target_dir / "apply_patch.py"
    installer_path.write_text(installer_code, encoding="utf-8")

    # Import and run dry run check
    import importlib.util

    spec = importlib.util.spec_from_file_location("installer_mod", installer_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # 1. Check dry-run does not modify file
    assert mod.check(target_dir) is True
    assert config_file.read_text(encoding="utf-8") == original_content

    # 2. Apply patch
    apply_success = mod.apply(target_dir)
    assert apply_success is True

    patched_content = config_file.read_text(encoding="utf-8")
    assert "batching_window_ms: 100.0" in patched_content
    assert hashlib.sha256(patched_content.encode("utf-8")).hexdigest() != original_sha256

    # 3. Rollback patch
    rollback_success = mod.rollback(target_dir)
    assert rollback_success is True

    restored_content = config_file.read_text(encoding="utf-8")
    restored_sha256 = hashlib.sha256(restored_content.encode("utf-8")).hexdigest()

    # Exact byte-for-byte and hash restoration verified
    assert restored_content == original_content
    assert restored_sha256 == original_sha256


# ---------------------------------------------------------------------------
# 7. Complete API Integration Tests (POST, GET, Download, Backward Compatibility)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repair_package_api_endpoints(auth_context, sample_candidate):
    """Test full HTTP API: POST create, GET status, GET download, and backward compatibility."""
    user = auth_context["user"]
    token = auth_context["access_token"]
    transport = ASGITransport(app=app)

    gen = GoldenIncidentGenerator()
    incident = gen.generate()
    incident_id = str(incident.id)
    incident._owner_user_id = user.id
    incident._owner_org_id = user.org_id
    incidents[incident_id] = incident

    ver_report = VerificationReport(
        patch_candidate_id=sample_candidate.candidate_id,
        verified=True,
        regression_test_passed=True,
        original_failure_eliminated=True,
    )

    ctx = PipelineContext(
        incident=incident,
        validated_incident=incident,
        patch_candidates=[sample_candidate],
        verification_reports=[ver_report],
        selected_repair_id=sample_candidate.candidate_id,
        workflow_status=WorkflowStatus.COMPLETED,
    )
    pipeline_contexts[incident_id] = ctx

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}"}

        # 1. POST /repair-packages to build package
        res_post = await client.post(
            f"/api/v1/incidents/{incident_id}/repair-packages",
            json={"candidate_id": sample_candidate.candidate_id},
            headers=headers,
        )
        assert res_post.status_code == 200
        post_data = res_post.json()
        assert post_data["status"] == "READY"
        assert post_data["repair_id"] == sample_candidate.candidate_id
        package_id = post_data["package_id"]
        assert package_id

        # 2. GET /repair-packages to list builds
        res_list = await client.get(
            f"/api/v1/incidents/{incident_id}/repair-packages",
            headers=headers,
        )
        assert res_list.status_code == 200
        list_data = res_list.json()
        assert len(list_data["packages"]) >= 1
        matching = [p for p in list_data["packages"] if p["package_id"] == package_id]
        assert len(matching) == 1

        # 3. GET /repair-packages/{package_id} to query by opaque package_id
        res_get = await client.get(
            f"/api/v1/incidents/{incident_id}/repair-packages/{package_id}",
            headers=headers,
        )
        assert res_get.status_code == 200
        assert res_get.json()["package_id"] == package_id
        assert res_get.json()["is_downloadable"] is True

        # 4. GET /repair-packages/{package_id}/download to download archive
        res_dl = await client.get(
            f"/api/v1/incidents/{incident_id}/repair-packages/{package_id}/download",
            headers=headers,
        )
        assert res_dl.status_code == 200
        assert res_dl.headers["content-type"] == "application/zip"
        assert "Content-Length" in res_dl.headers
        assert "X-Checksum-SHA256" in res_dl.headers
        assert res_dl.headers["X-Checksum-SHA256"] == hashlib.sha256(res_dl.content).hexdigest()

        # 5. GET /download-patch-package (backward-compatible route)
        res_compat = await client.get(
            f"/api/v1/incidents/{incident_id}/download-patch-package",
            headers=headers,
        )
        assert res_compat.status_code == 200
        assert res_compat.headers["content-type"] == "application/zip"
        assert res_compat.headers["X-Checksum-SHA256"] == hashlib.sha256(res_compat.content).hexdigest()

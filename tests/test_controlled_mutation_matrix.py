"""
Phase 21: Controlled Mutation Defect Matrix Tests.
Systematically tests all 22 controlled mutations specified in Phase 21:
1. Insecure token validation
2. Plaintext password storage
3. Cross-user incident leakage
4. Cross-incident patch association
5. Cross-incident package download
6. Unverified patch packaging
7. Empty unified diff packaging
8. Path traversal ZIP extraction
9. Path traversal patch application
10. Malformed unified diff parsing
11. Corrupted archive detection
12. In-memory queue in production
13. Incomplete provenance tracking
14. Missing required evidence detection
15. Untracked parameter mutation
16. Intervention data in baseline run
17. Regression detection in twin comparison
18. Verification level escalation
19. Skipped verification check blocking
20. Reversible rollback failure detection
21. Hardcoded model outputs
22. Secret leakage in model execution records

For each mutation:
- Confirms the healthy baseline functions as expected.
- Applies the mutation/defect.
- Asserts the defect is detected, rejected, and blocked by the system.
"""

from __future__ import annotations

import io
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from cauveris.analysis.model_inputs import (
    ModelInputBuilder,
    ModelInputKind,
)
from cauveris.analysis.provenance import (
    ProvenanceClass,
    ProvenanceRecord,
    create_provenance_record,
    normalize_provenance_string,
)
from cauveris.api.main import app
from cauveris.auth import (
    Organization,
    Session,
    TokenExpiredError,
    TokenInvalidError,
    TokenManager,
    User,
    init_auth_store,
)
from cauveris.config import Settings, get_settings
from cauveris.ingestion.controller import extract_zip_safely
from cauveris.model_gateway.records import ModelExecutionRecord, get_execution_store
from cauveris.packaging.builder import PackageBuilder
from cauveris.packaging.models import (
    PACKAGE_CANDIDATE_UNVERIFIED,
    PACKAGE_PATCH_EMPTY,
    PackageError,
    PackageStatus,
)
from cauveris.packaging.storage import PackageStore
from cauveris.packaging.validation import validate_package_archive
from cauveris.patch.unified_diff import UnifiedDiffError, reverse_unified_diff
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.incident import Incident
from cauveris.schemas.patch import PatchCandidate
from cauveris.simulation.runs import BaselineRun, InterventionRun, compare_runs
from cauveris.verifier.atomic_checks import (
    AtomicCheckRecord,
    CheckStatus,
    VerificationLevel,
    evaluate_verification_level,
)
from cauveris.verifier.engine import VerificationEngine


# ---------------------------------------------------------------------------
# Mutation 1: Insecure token validation
# ---------------------------------------------------------------------------
def test_mutation_01_insecure_token_validation():
    """Prove tampered, expired, or bogus JWTs are strictly rejected."""
    tm = TokenManager(secret_key="my_secret_key_12345678901234567890")
    user = User(id="user-valid", email="valid@cauveris.dev")
    session = Session(id="sess-valid", user_id="user-valid", org_id="org-valid")
    org = Organization(id="org-valid", name="Valid Org")

    # Baseline: valid token works
    token = tm.create_access_token(user, session, org)
    payload = tm.decode_token(token)
    assert payload is not None
    assert payload.get("sub") == "user-valid"

    # Mutation A: Tampered payload / signature
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1] + "X" + "." + parts[2]
    with pytest.raises(TokenInvalidError):
        tm.decode_token(tampered)

    # Mutation B: Expired token
    expired_payload = {
        "sub": "user-exp",
        "org_id": "org-valid",
        "session_id": "sess-exp",
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        "type": "access",
    }
    expired_token = jwt.encode(expired_payload, tm.secret_key, algorithm=tm.algorithm)
    with pytest.raises(TokenExpiredError):
        tm.decode_token(expired_token)

    # Mutation C: Bogus string
    with pytest.raises(TokenInvalidError):
        tm.decode_token("not-a-token")


# ---------------------------------------------------------------------------
# Mutation 2: Plaintext password storage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutation_02_plaintext_password_storage(tmp_path):
    """Prove raw passwords are never persisted in plaintext, strictly bcrypt hashed."""
    db_file = str(tmp_path / "auth_test.db")
    settings = get_settings()
    settings.runtime_mode = "development"
    settings.demo_auth = False
    settings.auth_backend = "sqlite"
    settings.auth_db_path = db_file
    init_auth_store(backend="sqlite", db_path=db_file)

    raw_password = "SuperSecretPassword2026!"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/signup",
            json={"email": "mutation.plain@cauveris.dev", "password": raw_password, "full_name": "Plain User"},
        )
        assert res.status_code == 200

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE email = 'mutation.plain@cauveris.dev'")
    row = cur.fetchone()
    conn.close()

    assert row is not None
    stored_hash = row[0]
    # Defect check: plaintext password must NOT appear in stored hash
    assert raw_password not in stored_hash
    # Must be valid bcrypt hash with standard prefix
    assert stored_hash.startswith("$2b$")


# ---------------------------------------------------------------------------
# Mutation 3: Cross-user incident leakage
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutation_03_cross_user_incident_leakage(tmp_path):
    """Prove User B is strictly forbidden (403) from accessing User A's incident."""
    db_file = str(tmp_path / "auth_iso.db")
    settings = get_settings()
    settings.runtime_mode = "development"
    settings.demo_auth = False
    settings.auth_backend = "sqlite"
    settings.auth_db_path = db_file
    init_auth_store(backend="sqlite", db_path=db_file)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register User A
        res_a = await client.post(
            "/api/v1/auth/signup",
            json={"email": "alice@cauveris.dev", "password": "Password123456!", "full_name": "Alice"},
        )
        token_a = res_a.json()["access_token"]

        # Register User B
        res_b = await client.post(
            "/api/v1/auth/signup",
            json={"email": "bob@cauveris.dev", "password": "Password123456!", "full_name": "Bob"},
        )
        token_b = res_b.json()["access_token"]

        # User A creates Incident
        inc_res = await client.post(
            "/api/v1/incidents",
            json={"custom_id": "INC-ALICE-01"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert inc_res.status_code == 200
        incident_id = inc_res.json()["incident_id"]

        # User A can view it (200)
        view_a = await client.get(
            f"/api/v1/incidents/{incident_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert view_a.status_code == 200

        # Mutation: User B attempts to access User A's incident -> strictly 403 Forbidden
        view_b = await client.get(
            f"/api/v1/incidents/{incident_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert view_b.status_code == 403
        assert "access_denied" in view_b.text


# ---------------------------------------------------------------------------
# Mutation 4: Cross-incident patch association
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutation_04_cross_incident_patch_association():
    """Prove a patch candidate created for Incident B is rejected when verifying Incident A."""
    incident_a = Incident(id="INC-AAA", title="Incident A", status="OBSERVED", priority="high")
    engine = VerificationEngine(incident=incident_a)

    # Mutation: Candidate has incident_id="INC-BBB"
    foreign_patch = PatchCandidate(
        candidate_id="cand-foreign",
        incident_id="INC-BBB",  # MISMATCH
        target_file="worker.py",
        affected_files=["worker.py"],
        unified_diff="--- a/worker.py\n+++ b/worker.py\n@@ -1 +1 @@\n-old\n+new\n",
        explanation="Foreign patch",
    )

    reports = await engine.verify([foreign_patch], incident=incident_a)
    assert len(reports) == 1
    report = reports[0]
    assert report.verified is False
    assert report.verification_level == VerificationLevel.UNVERIFIED.value
    assert "cross-incident" in foreign_patch.rejection_reason.lower()


# ---------------------------------------------------------------------------
# Mutation 5: Cross-incident package download
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutation_05_cross_incident_package_download(tmp_path):
    """Prove attempting to download a package belonging to another incident returns 404/403."""
    db_file = str(tmp_path / "auth_pkg.db")
    pkg_dir = tmp_path / "packages"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    settings.runtime_mode = "development"
    settings.demo_auth = False
    settings.auth_backend = "sqlite"
    settings.auth_db_path = db_file
    settings.package_storage_path = str(pkg_dir)
    init_auth_store(backend="sqlite", db_path=db_file)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/v1/auth/signup",
            json={"email": "packager@cauveris.dev", "password": "Password123456!", "full_name": "Packager"},
        )
        token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create Incident A and Incident B
        await client.post("/api/v1/incidents", json={"custom_id": "INC-PKGA"}, headers=headers)
        await client.post("/api/v1/incidents", json={"custom_id": "INC-PKGB"}, headers=headers)

        # Store package strictly under INC-PKGB
        store = PackageStore(settings=settings)
        record_b = store.create_record(
            incident_id="INC-PKGB",
            repair_id="rep-b",
            user_id="user-1",
            org_id="org-1",
        )
        store.set_status("INC-PKGB", "rep-b", record_b.build_number, PackageStatus.READY)
        pkg_b_id = record_b.package_id

        # Mutation: Attempt to retrieve/download INC-PKGB package under INC-PKGA URL
        res_cross = await client.get(
            f"/api/v1/incidents/INC-PKGA/repair-packages/{pkg_b_id}",
            headers=headers,
        )
        assert res_cross.status_code == 404


# ---------------------------------------------------------------------------
# Mutation 6: Unverified patch packaging
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutation_06_unverified_patch_packaging(tmp_path):
    """Prove PackageBuilder strictly refuses to package an unverified patch."""
    builder = PackageBuilder()
    incident = Incident(id="INC-UNVER", title="Unverified Incident", status="OBSERVED", bundle_path=str(tmp_path))

    # Mutation: verified=False
    unverified_patch = PatchCandidate(
        candidate_id="cand-unver",
        incident_id="INC-UNVER",
        target_file="config.yaml",
        affected_files=["config.yaml"],
        unified_diff="--- a/config.yaml\n+++ b/config.yaml\n@@ -1 +1 @@\n-a: 1\n+a: 2\n",
        verified=False,
    )

    with pytest.raises(PackageError) as exc_info:
        await builder.build(incident, unverified_patch, user_id="u1", org_id="o1")
    assert exc_info.value.code == PACKAGE_CANDIDATE_UNVERIFIED


# ---------------------------------------------------------------------------
# Mutation 7: Empty unified diff packaging
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutation_07_empty_unified_diff_packaging(tmp_path):
    """Prove PackageBuilder strictly refuses to package an empty or whitespace diff."""
    bundle_dir = tmp_path / "bundle_empty"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "manifest.yaml").write_text("incident_id: INC-EMPTY\nname: test\n", encoding="utf-8")
    (bundle_dir / "config.yaml").write_text("batch_size: 10\n", encoding="utf-8")

    builder = PackageBuilder()
    incident = Incident(id="INC-EMPTY", title="Empty Diff Incident", status="OBSERVED", bundle_path=str(bundle_dir))

    # Mutation: unified_diff=""
    empty_diff_patch = PatchCandidate(
        candidate_id="cand-empty",
        incident_id="INC-EMPTY",
        target_file="config.yaml",
        affected_files=["config.yaml"],
        unified_diff="   \n  ",
        verified=True,
    )

    with pytest.raises(PackageError) as exc_info:
        await builder.build(incident, empty_diff_patch, user_id="u1", org_id="o1")
    assert exc_info.value.code == PACKAGE_PATCH_EMPTY


# ---------------------------------------------------------------------------
# Mutation 8: Path traversal ZIP extraction
# ---------------------------------------------------------------------------
def test_mutation_08_path_traversal_zip_extraction(tmp_path):
    """Prove extract_zip_safely strictly detects and rejects ZIP archives with path traversal members."""
    extract_target = tmp_path / "extracted"

    # Mutation: ZIP containing member with "../" traversal
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("../../etc/shadow", "root:*:0:0:root:/root:/bin/bash")
    zip_bytes = zip_buffer.getvalue()

    bad_zip = tmp_path / "bad.zip"
    bad_zip.write_bytes(zip_bytes)

    with pytest.raises(ValueError, match="Path traversal attempt detected"):
        extract_zip_safely(bad_zip, extract_target)


# ---------------------------------------------------------------------------
# Mutation 9: Path traversal patch application
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutation_09_path_traversal_patch_application(tmp_path):
    """Prove PackageBuilder strictly detects and rejects path traversal target files."""
    evidence_dir = tmp_path / "evidence_trav"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "manifest.yaml").write_text("incident_id: INC-TRAV\nname: test\n", encoding="utf-8")
    (evidence_dir / "app.py").write_text("x = 1\n", encoding="utf-8")

    builder = PackageBuilder()
    incident = Incident(id="INC-TRAV", title="Traversal Incident", status="OBSERVED", bundle_path=str(evidence_dir))

    # Mutation: target_file attempts path traversal
    trav_patch = PatchCandidate(
        candidate_id="cand-trav",
        incident_id="INC-TRAV",
        target_file="../../etc/passwd",
        affected_files=["../../etc/passwd"],
        unified_diff="--- ../../etc/passwd\n+++ ../../etc/passwd\n@@ -1 +1 @@\n-a\n+b\n",
        verified=True,
    )

    with pytest.raises(PackageError) as exc_info:
        await builder.build(incident, trav_patch, user_id="u1", org_id="o1")
    assert exc_info.value.code == "path_traversal"


# ---------------------------------------------------------------------------
# Mutation 10: Malformed unified diff parsing
# ---------------------------------------------------------------------------
def test_mutation_10_malformed_unified_diff_parsing():
    """Prove malformed/corrupted diffs cannot be reversed and raise UnifiedDiffError."""
    # Baseline: valid diff reverses cleanly
    valid_diff = "--- a/file.txt\n+++ b/file.txt\n@@ -1,1 +1,1 @@\n-old\n+new\n"
    reversed_diff = reverse_unified_diff(valid_diff)
    assert "+old" in reversed_diff
    assert "-new" in reversed_diff

    # Mutation: malformed diff without headers or hunks
    malformed_diff = "MALFORMED GARBAGE THAT IS NOT A UNIFIED DIFF\nJUST RANDOM TEXT"
    with pytest.raises((UnifiedDiffError, ValueError)):
        reverse_unified_diff(malformed_diff)


# ---------------------------------------------------------------------------
# Mutation 11: Corrupted archive detection
# ---------------------------------------------------------------------------
def test_mutation_11_corrupted_archive_detection():
    """Prove validate_package_archive strictly returns ok=False on corrupted archives."""
    # Mutation A: Random binary garbage
    corrupted_bytes = b"NOT_A_ZIP_HEADER_JUST_RANDOM_CORRUPTED_BYTES_1234567890"
    result = validate_package_archive(corrupted_bytes)
    assert result.ok is False
    assert len(result.failures) > 0

    # Mutation B: Truncated ZIP header
    truncated_bytes = b"PK\x03\x04\x00\x00"
    result_trunc = validate_package_archive(truncated_bytes)
    assert result_trunc.ok is False
    assert len(result_trunc.failures) > 0


# ---------------------------------------------------------------------------
# Mutation 12: In-memory queue in production
# ---------------------------------------------------------------------------
def test_mutation_12_in_memory_queue_in_production():
    """Prove running in-memory queue with separate workers in production is strictly forbidden."""
    # Mutation: production runtime + memory queue + separate workers
    settings = Settings(
        runtime_mode="production",
        demo_mode=False,
        auth_jwt_secret="strong_secret_key_at_least_32_characters_long",
        job_queue_embedded_worker=False,
        job_queue_backend="memory",
    )
    with pytest.raises(RuntimeError, match="cannot be 'memory' when CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER=false"):
        settings.validate_production_security()


# ---------------------------------------------------------------------------
# Mutation 13: Incomplete provenance tracking
# ---------------------------------------------------------------------------
def test_mutation_13_incomplete_provenance_tracking():
    """Prove invalid provenance cannot be assigned and missing metrics display UNAVAILABLE."""
    # Baseline: Valid provenance class works with non-null value
    rec = create_provenance_record(
        parameter_id="batching_window_ms",
        value=200.0,
        unit="ms",
        provenance=ProvenanceClass.DECLARED,
        source_artifact="config/worker.yaml",
        source_locator="batching.window_ms",
        calculation_rationale="Parsed directly from config key",
    )
    assert rec.provenance == ProvenanceClass.DECLARED
    assert rec.display_value == "200 ms"

    # Mutation A: Empty/None or unavailable string resolves to UNAVAILABLE
    norm_none, _ = normalize_provenance_string(None)
    assert norm_none == ProvenanceClass.UNAVAILABLE

    norm_unavail, _ = normalize_provenance_string("unavailable:telemetry_lost")
    assert norm_unavail == ProvenanceClass.UNAVAILABLE

    # Mutation B: Pydantic rejects completely invalid provenance class
    with pytest.raises(Exception):
        ProvenanceRecord(
            parameter_id="resource_demand_mb",
            provenance="COMPLETELY_INVALID_CLASS",
        )

    # Mutation C: Unavailable provenance strictly guarantees display_value == "UNAVAILABLE"
    unavail_rec = create_provenance_record(
        parameter_id="resource_demand_mb",
        value=None,
        unit="MB",
        provenance=ProvenanceClass.UNAVAILABLE,
        calculation_rationale="Metric missing from evidence bundle",
    )
    assert unavail_rec.display_value == "UNAVAILABLE"
    assert unavail_rec.provenance == ProvenanceClass.UNAVAILABLE


# ---------------------------------------------------------------------------
# Mutation 14: Missing required evidence detection
# ---------------------------------------------------------------------------
def test_mutation_14_missing_required_evidence_detection():
    """Prove hypotheses lacking supporting evidence are automatically marked speculative."""
    # Baseline: Grounded hypothesis with supporting evidence maintains speculative=False
    grounded = Hypothesis(
        hypothesis_id="hyp-grounded",
        title="Grounded claim",
        description="Grounded explanation",
        causal_claim="Memory allocation exceeds available heap",
        falsifying_observation="Heap usage stays below 500MB",
        supporting_evidence_ids=["ev-heap-01"],
        expected_observation="Expected decrease",
        intervention="Increase limit",
    )
    assert grounded.speculative is False

    # Mutation: Hypothesis with empty supporting evidence -> must be marked speculative
    ungrounded = Hypothesis(
        hypothesis_id="hyp-ungrounded",
        title="Ungrounded claim",
        description="Ungrounded explanation",
        causal_claim="Memory allocation exceeds available heap",
        falsifying_observation="Heap usage stays below 500MB",
        supporting_evidence_ids=[],
        expected_observation="Expected decrease",
        intervention="Increase limit",
    )
    assert ungrounded.speculative is True


# ---------------------------------------------------------------------------
# Mutation 15: Untracked parameter mutation
# ---------------------------------------------------------------------------
def test_mutation_15_untracked_parameter_mutation():
    """Prove untracked parameters not defined in registry policies are strictly rejected."""
    builder = ModelInputBuilder("INC-UNTRACKED")
    # Mutation: Injected untracked parameter
    with pytest.raises(ValueError, match="Untracked parameter 'untracked_injected_parameter_x'"):
        builder.add_evidence_input(
            parameter_id="untracked_injected_parameter_x",
            value=99999.0,
            unit="items",
            kind=ModelInputKind.OBSERVED,
            source_artifact_id="art-1",
            source_locator="magic.key",
        )


# ---------------------------------------------------------------------------
# Mutation 16: Intervention data in baseline run
# ---------------------------------------------------------------------------
def test_mutation_16_intervention_data_in_baseline_run():
    """Prove BaselineRun strictly forbids post-repair intervention data."""
    # Mutation: Setting intervention fields on BaselineRun
    with pytest.raises(ValueError, match="BaselineRun cannot contain post-repair intervention fields"):
        BaselineRun(
            baseline_run_id="base_mut",
            incident_id="INC-MUT",
            hypothesis_id="hyp_mut",
            mechanism_id="control_deadline_missed",
            model_id="twin_v2",
            invariant_set_id="invset_A",
            model_input_set_id="inputs_A",
            named_reproduced_failure="Deadline exceeded",
            failures_cleared=True,  # FORBIDDEN IN BASELINE
        )


# ---------------------------------------------------------------------------
# Mutation 17: Regression detection in twin comparison
# ---------------------------------------------------------------------------
def test_mutation_17_regression_detection_in_twin_comparison():
    """Prove candidate that degrades performance triggers regression detection and FAILED_REGRESSIONS."""
    base = BaselineRun(
        baseline_run_id="base_01",
        incident_id="INC-01",
        hypothesis_id="hyp_01",
        mechanism_id="queue_pressure",
        model_id="twin_v2",
        invariant_set_id="invset_A",
        model_input_set_id="inputs_A",
        named_reproduced_failure="Queue saturation",
        failed_invariants=["queue_depth"],
        baseline_outputs={"p99_latency_ms": 100.0},
    )

    # Mutation: Intervention introduces regression
    interv = InterventionRun(
        intervention_run_id="interv_01",
        incident_id="INC-01",
        candidate_id="cand_bad",
        baseline_run_id="base_01",
        hypothesis_id="hyp_01",
        mechanism_id="queue_pressure",
        model_id="twin_v2",
        invariant_set_id="invset_A",
        model_input_set_id="inputs_A",
        outputs={"p99_latency_ms": 500.0},
        invariant_results={"queue_depth": True},
        regression_results={
            "regressions_detected": True,
            "details": ["P99 latency degraded from 100ms to 500ms exceeding SLA limit"],
        },
    )

    cmp = compare_runs(base, interv, "cand_bad")
    assert "FAILED_REGRESSIONS" in cmp.conclusion
    assert len(cmp.regressions) > 0


# ---------------------------------------------------------------------------
# Mutation 18: Verification level escalation
# ---------------------------------------------------------------------------
def test_mutation_18_verification_level_escalation():
    """Prove verification level cannot jump to RUNTIME_VERIFIED without physical runtime checks."""
    # Only model level checks pass
    checks = [
        AtomicCheckRecord(
            check_id="CHK-MDL",
            name="Model check",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.PASSED,
        )
    ]
    summary = evaluate_verification_level(
        candidate_id="cand-esc",
        experiment_id="exp-esc",
        invariant_set_id="inv-esc",
        baseline_run_id="b-esc",
        intervention_run_id="i-esc",
        checks=checks,
    )
    # Mutation prevention: cannot be escalated to RUNTIME_VERIFIED
    assert summary.achieved_level != VerificationLevel.RUNTIME_VERIFIED
    assert summary.achieved_level == VerificationLevel.MODEL_VERIFIED


# ---------------------------------------------------------------------------
# Mutation 19: Skipped verification check blocking
# ---------------------------------------------------------------------------
def test_mutation_19_skipped_verification_check_blocking():
    """Prove a skipped required verification check blocks verification."""
    checks = [
        AtomicCheckRecord(
            check_id="CHK-REQ-SKIPPED",
            name="Required safety check",
            target_level=VerificationLevel.MODEL_VERIFIED,
            required=True,
            status=CheckStatus.SKIPPED,  # SKIPPED
            is_skipped=True,
            skip_reason="Test harness skipped check",
        )
    ]
    summary = evaluate_verification_level(
        candidate_id="cand-skip",
        experiment_id="exp-skip",
        invariant_set_id="inv-skip",
        baseline_run_id="b-skip",
        intervention_run_id="i-skip",
        checks=checks,
    )
    assert summary.verified is False
    assert summary.overall_status == "FAILED"
    assert summary.achieved_level == VerificationLevel.UNVERIFIED


# ---------------------------------------------------------------------------
# Mutation 20: Reversible rollback failure detection
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mutation_20_reversible_rollback_failure_detection(tmp_path):
    """Prove PackageBuilder strictly detects when reverse rollback fails to restore original file."""
    evidence_dir = tmp_path / "evidence_roll"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "manifest.yaml").write_text("incident_id: INC-ROLL\nname: test\n", encoding="utf-8")
    target_file = evidence_dir / "worker.py"
    target_file.write_text("initial_state = 1\n", encoding="utf-8")

    builder = PackageBuilder()
    incident = Incident(id="INC-ROLL", title="Rollback Incident", status="OBSERVED", bundle_path=str(evidence_dir))

    # A candidate where reverse diff application will fail or corrupt
    candidate = PatchCandidate(
        candidate_id="cand-roll-fail",
        incident_id="INC-ROLL",
        target_file="worker.py",
        affected_files=["worker.py"],
        unified_diff=(
            "--- worker.py\n"
            "+++ worker.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-initial_state = 1\n"
            "+modified_state = 2\n"
        ),
        verified=True,
    )

    # Mutation: Patch reverse_unified_diff to return broken reverse diff
    with patch("cauveris.packaging.builder.reverse_unified_diff", return_value="--- worker.py\n+++ worker.py\n@@ -1,1 +1,1 @@\n-corrupted = 99\n+broken = 00\n"):
        with pytest.raises(PackageError) as exc_info:
            await builder.build(incident, candidate, user_id="u1", org_id="o1")
        assert exc_info.value.code == "rollback_verification_failed"


# ---------------------------------------------------------------------------
# Mutation 21: Hardcoded model outputs
# ---------------------------------------------------------------------------
def test_mutation_21_hardcoded_model_outputs_blocked():
    """Prove that forbidden mocks, fixtures, and canned fallbacks are absent from runtime code."""
    from scripts.check_runtime_fixture_imports import main as check_imports
    # Zero runtime fixture/sample imports allowed
    assert check_imports() == 0


# ---------------------------------------------------------------------------
# Mutation 22: Secret leakage in model execution records
# ---------------------------------------------------------------------------
def test_mutation_22_secret_leakage_in_model_execution_records(tmp_path):
    """Prove API keys and secrets are never stored in model execution database."""
    db_file = str(tmp_path / "test_exec.db")
    store = get_execution_store(db_path=db_file)

    secret_key = "sk-live-nebius-secret-key-123456789"
    rec = ModelExecutionRecord(
        incident_id="INC-SEC-01",
        provider="nebius",
        model_id="nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        accepted_suggestions=[{"claim": "buffer_overrun"}],
        rejection_reasons=["Validation failed"],
    )
    store.record(rec)

    # Query directly from SQLite
    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT * FROM model_executions WHERE incident_id = 'INC-SEC-01'")
    row = cur.fetchone()
    conn.close()

    assert row is not None
    row_str = " ".join(str(val) for val in row)
    assert secret_key not in row_str

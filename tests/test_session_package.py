"""
Tests for ``cauveris-session/v1`` session packages.

A session package is the unit of work an operator saves and later resumes.
These tests pin the three things that matter:

1. a session round-trips — evidence, pipeline history, report and repair
   packages all come back exactly as they were captured;
2. a tampered or hostile archive is rejected, and nothing is written;
3. the import never fabricates what the archive did not contain, and the
   archive never leaks across users.
"""

import io
import json
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from cauveris.api.main import app, incidents
from cauveris.config import get_settings
from cauveris.sessions.models import (
    SESSION_CHECKSUMS_PATH,
    SESSION_MANIFEST_PATH,
    SessionChecksumError,
    SessionFormatError,
)
from cauveris.sessions.restore import SessionRestorer
from cauveris.state_machine.persistence import PipelinePersistenceStore


@pytest.fixture
async def session_env(tmp_path):
    """
    Point the evidence, report and pipeline stores at a scratch directory.

    The pipeline store is a process-wide singleton pointed at the real
    ``data/pipeline_stages.db``.  Left alone, a session test appends to the
    developer's live database — and a test that counts events would then read
    a number that grows with every run.  Resetting the singleton makes the
    session suite hermetic.
    """
    settings = get_settings()
    original_evidence = settings.evidence_store_path
    original_report = settings.report_store_path
    original_pipeline = settings.pipeline_db_path

    evidence_dir = tmp_path / "evidence"
    report_dir = tmp_path / "reports"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    settings.evidence_store_path = str(evidence_dir)
    settings.report_store_path = str(report_dir)
    settings.pipeline_db_path = str(tmp_path / "pipeline.db")
    PipelinePersistenceStore._instance = None

    yield {
        "evidence_dir": evidence_dir,
        "report_dir": report_dir,
    }

    settings.evidence_store_path = original_evidence
    settings.report_store_path = original_report
    settings.pipeline_db_path = original_pipeline
    PipelinePersistenceStore._instance = None


async def _create_incident(client: AsyncClient, headers, **overrides):
    """Create an incident through the API and return its id."""
    payload = {
        "title": "Session round-trip incident",
        "description": "Exercise the session package format.",
        "system_name": "warehouse-amr-07",
        "severity": "high",
        "category": "control",
        "environment": "warehouse",
        "tags": ["thermal"],
    }
    payload.update(overrides)
    res = await client.post("/api/v1/incidents", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    return res.json()["incident_id"]


def _seed_evidence(evidence_dir: Path, incident_id: str) -> Path:
    """Write a small evidence bundle and point the incident at it."""
    bundle = evidence_dir / incident_id
    (bundle / "logs").mkdir(parents=True, exist_ok=True)
    (bundle / "config.yaml").write_text("service: rover\n", encoding="utf-8")
    (bundle / "logs" / "telemetry.csv").write_text(
        "t,pressure\n0,101\n1,99\n", encoding="utf-8"
    )
    return bundle


def _seed_report(report_dir: Path, incident_id: str) -> Path:
    """Write an incident report and return its path."""
    report_path = report_dir / incident_id / "incident_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"incident_id": incident_id, "summary": "Root cause: coolant loop."}),
        encoding="utf-8",
    )
    return report_path


def _seed_pipeline(incident_id: str):
    """Initialize stages and record a couple of events."""
    store = PipelinePersistenceStore.get_instance()
    store.initialize_incident_stages(incident_id, overwrite=True)
    store.update_stage(
        type(store.get_stages(incident_id)[0])(
            incident_id=incident_id,
            stage_id=store.get_stages(incident_id)[0].stage_id,
            name=store.get_stages(incident_id)[0].name,
            status="SUCCESS",
            duration_ms=12.5,
            attempt_count=1,
        )
    )
    store.record_event(incident_id, "STAGE_STARTED", store.get_stages(incident_id)[0].stage_id, {})
    store.record_event(incident_id, "STAGE_COMPLETED", store.get_stages(incident_id)[0].stage_id, {})
    return store


# ---------------------------------------------------------------------------
# building
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_creates_a_session_package(session_env, test_user):
    """Building a session returns the manifest and writes an archive."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        incident_id = await _create_incident(client, test_user["headers"])

        res = await client.post(
            f"/api/v1/sessions/{incident_id}", headers=test_user["headers"]
        )
        assert res.status_code == 202, res.text
        body = res.json()
        assert body["status"] == "READY"
        assert body["incident_id"] == incident_id
        assert body["session_sha256"]
        assert body["size"] > 0

        manifest = body["manifest"]
        assert manifest["format"] == "cauveris-session/v1"
        assert manifest["incident_id"] == incident_id
        # The wizard's triage metadata travels inside the session.
        assert manifest["severity"] == "high"
        assert manifest["category"] == "control"
        assert manifest["environment"] == "warehouse"
        assert manifest["tags"] == ["thermal"]
        # Nothing was reported for this incident, so nothing is claimed.
        assert manifest["report_present"] is False
        assert "report" in body["missing"]

        # The archive really is on disk and really is a zip.
        listing = await client.get(
            f"/api/v1/sessions/{incident_id}", headers=test_user["headers"]
        )
        assert listing.status_code == 200, listing.text
        assert listing.json()["count"] == 1

        download = await client.get(
            f"/api/v1/sessions/{incident_id}/download", headers=test_user["headers"]
        )
        assert download.status_code == 200, download.text
        assert download.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
            names = set(zf.namelist())
        assert SESSION_MANIFEST_PATH in names
        assert SESSION_CHECKSUMS_PATH in names
        assert "session/pipeline/stages.json" in names
        assert "session/pipeline/events.json" in names


@pytest.mark.asyncio
async def test_build_captures_evidence_pipeline_and_report(session_env, test_user):
    """A session with a full workspace carries all of it."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        incident_id = await _create_incident(client, test_user["headers"])

        bundle = _seed_evidence(session_env["evidence_dir"], incident_id)
        incidents[incident_id].bundle_path = str(bundle)
        _seed_report(session_env["report_dir"], incident_id)
        _seed_pipeline(incident_id)

        res = await client.post(
            f"/api/v1/sessions/{incident_id}", headers=test_user["headers"]
        )
        assert res.status_code == 202, res.text
        manifest = res.json()["manifest"]
        assert manifest["report_present"] is True
        assert manifest["evidence_file_count"] == 2
        assert manifest["stage_count"] > 0
        assert manifest["event_count"] >= 2
        assert "missing" not in res.json() or "report" not in res.json()["missing"]


# ---------------------------------------------------------------------------
# round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_round_trip_restores_the_workspace(session_env, test_user):
    """Export then import: evidence, pipeline history and report all return."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        incident_id = await _create_incident(client, test_user["headers"])
        bundle = _seed_evidence(session_env["evidence_dir"], incident_id)
        incidents[incident_id].bundle_path = str(bundle)
        _seed_report(session_env["report_dir"], incident_id)
        store = _seed_pipeline(incident_id)
        stage_count = len(store.get_stages(incident_id))
        event_count = len(store.get_events(incident_id, limit=10_000))

        build = await client.post(
            f"/api/v1/sessions/{incident_id}", headers=test_user["headers"]
        )
        assert build.status_code == 202, build.text

        download = await client.get(
            f"/api/v1/sessions/{incident_id}/download", headers=test_user["headers"]
        )
        assert download.status_code == 200, download.text

        res = await client.post(
            "/api/v1/sessions/import",
            headers=test_user["headers"],
            files={"file": ("session.zip", download.content, "application/zip")},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "IMPORTED"

        restored_id = body["incident_id"]
        assert restored_id != incident_id, "the restored incident gets a fresh id"
        assert body["source_incident_id"] == incident_id
        assert "evidence" in body["restored"]
        assert "report" in body["restored"]
        assert "pipeline_history" in body["restored"]
        assert body["report_present"] is True
        assert body["stage_count"] == stage_count
        assert body["event_count"] == event_count
        assert body["evidence_file_count"] == 2
        assert body["title"] == "Session round-trip incident"

        # The restored incident exists in the console and keeps the operator's
        # triage metadata.
        restored = incidents[restored_id]
        assert restored.severity == "high"
        assert restored.category == "control"
        assert restored.tags == ["thermal"]

        # Its evidence is on disk in the evidence store.
        restored_bundle = session_env["evidence_dir"] / restored_id
        assert (restored_bundle / "config.yaml").is_file()
        assert (restored_bundle / "logs" / "telemetry.csv").is_file()

        # Its report is in the report store.
        assert (
            session_env["report_dir"] / restored_id / "incident_report.json"
        ).is_file()

        # Its pipeline history is queryable again.
        restored_store = PipelinePersistenceStore.get_instance()
        assert len(restored_store.get_stages(restored_id)) == stage_count
        assert len(restored_store.get_events(restored_id, limit=10_000)) == event_count


@pytest.mark.asyncio
async def test_import_without_a_report_says_so_and_fabricates_nothing(
    session_env, test_user
):
    """A session with no report comes back with no report — and says so."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        incident_id = await _create_incident(client, test_user["headers"])
        bundle = _seed_evidence(session_env["evidence_dir"], incident_id)
        incidents[incident_id].bundle_path = str(bundle)

        build = await client.post(
            f"/api/v1/sessions/{incident_id}", headers=test_user["headers"]
        )
        assert build.status_code == 202, build.text
        assert "report" in build.json()["missing"]

        download = await client.get(
            f"/api/v1/sessions/{incident_id}/download", headers=test_user["headers"]
        )
        res = await client.post(
            "/api/v1/sessions/import",
            headers=test_user["headers"],
            files={"file": ("session.zip", download.content, "application/zip")},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["report_present"] is False
        assert "report" in body["missing"]
        assert "report" not in body["restored"]

        restored_id = body["incident_id"]
        assert not (
            session_env["report_dir"] / restored_id / "incident_report.json"
        ).exists()
        # The report endpoint must 404 rather than serve an empty report.
        report = await client.get(
            f"/api/v1/incidents/{restored_id}/reports/001",
            headers=test_user["headers"],
        )
        assert report.status_code == 404, report.text


# ---------------------------------------------------------------------------
# hostile archives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_rejects_a_tampered_member(session_env, test_user):
    """A member whose bytes were changed after the checksum was recorded."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        incident_id = await _create_incident(client, test_user["headers"])
        bundle = _seed_evidence(session_env["evidence_dir"], incident_id)
        incidents[incident_id].bundle_path = str(bundle)

        build = await client.post(
            f"/api/v1/sessions/{incident_id}", headers=test_user["headers"]
        )
        assert build.status_code == 202, build.text
        download = await client.get(
            f"/api/v1/sessions/{incident_id}/download", headers=test_user["headers"]
        )

        # Rewrite the archive with a modified evidence member but the original
        # manifest and checksum table.
        source = zipfile.ZipFile(io.BytesIO(download.content))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for name in source.namelist():
                data = source.read(name)
                if name == "artifacts/config.yaml":
                    data = b"service: tampered\n"
                out.writestr(name, data)
        tampered = buffer.getvalue()

        before = set(p.name for p in session_env["evidence_dir"].iterdir())
        res = await client.post(
            "/api/v1/sessions/import",
            headers=test_user["headers"],
            files={"file": ("session.zip", tampered, "application/zip")},
        )
        assert res.status_code == 422, res.text
        assert res.json()["detail"]["error"] == "session_checksum_mismatch"

        # Nothing was written.
        after = set(p.name for p in session_env["evidence_dir"].iterdir())
        assert after == before


@pytest.mark.asyncio
async def test_import_rejects_path_traversal(session_env, test_user):
    """A member that climbs out of the extraction directory is refused."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(SESSION_MANIFEST_PATH, "format: cauveris-session/v1\n")
        zf.writestr("../../etc/passwd", "root:x:0:0\n")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/sessions/import",
            headers=test_user["headers"],
            files={"file": ("session.zip", buffer.getvalue(), "application/zip")},
        )
        assert res.status_code == 422, res.text
        assert res.json()["detail"]["error"] == "session_archive_rejected"


@pytest.mark.asyncio
async def test_import_rejects_a_foreign_archive(session_env, test_user):
    """An archive that is not a session package is refused with a clear error."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("hello.txt", "not a session package")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/sessions/import",
            headers=test_user["headers"],
            files={"file": ("other.zip", buffer.getvalue(), "application/zip")},
        )
        assert res.status_code == 422, res.text
        assert res.json()["detail"]["error"] == "session_invalid_format"


@pytest.mark.asyncio
async def test_import_requires_a_zip(session_env, test_user):
    """A non-zip upload is refused before anything is written."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/sessions/import",
            headers=test_user["headers"],
            files={"file": ("session.tar", b"not a zip", "application/x-tar")},
        )
        assert res.status_code == 422, res.text
        assert res.json()["detail"]["error"] == "session_import_requires_a_zip_archive"


# ---------------------------------------------------------------------------
# ownership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_user_cannot_download_a_session_package(session_env, test_user):
    """A session archive is owner-scoped exactly like a repair package."""
    from cauveris.auth import (
        Organization,
        Session,
        TokenManager,
        User,
        UserRole,
        get_auth_store,
    )
    import uuid

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        incident_id = await _create_incident(client, test_user["headers"])
        build = await client.post(
            f"/api/v1/sessions/{incident_id}", headers=test_user["headers"]
        )
        assert build.status_code == 202, build.text

        # A second user in the same organisation.
        auth_store = get_auth_store()
        settings = get_settings()
        token_manager = TokenManager(settings.auth_jwt_secret, settings.auth_jwt_algorithm)
        org = await auth_store.create_org(
            Organization(name="Other Org", slug=f"other-{uuid.uuid4().hex[:8]}")
        )
        other = User(
            email=f"other-{uuid.uuid4().hex[:8]}@cauveris.local",
            full_name="Other User",
            role=UserRole.ENGINEER,
            org_id=org.id,
            is_active=True,
        )
        other.set_password("test123456")
        other = await auth_store.create_user(other)
        other_session = Session(
            user_id=other.id, org_id=org.id, ip_address="127.0.0.1", user_agent="test"
        )
        other_session.access_token = token_manager.create_access_token(
            other, other_session, org
        )
        other_session.refresh_token = token_manager.create_refresh_token(other_session)
        other_session = await auth_store.create_session(other_session)
        other_headers = {"Authorization": f"Bearer {other_session.access_token}"}

        denied = await client.get(
            f"/api/v1/sessions/{incident_id}/download", headers=other_headers
        )
        assert denied.status_code == 403, denied.text
        assert denied.json()["detail"]["error"] == "access_denied"

        listed = await client.get(
            f"/api/v1/sessions/{incident_id}", headers=other_headers
        )
        assert listed.status_code == 403, listed.text


# ---------------------------------------------------------------------------
# unit-level guarantees
# ---------------------------------------------------------------------------


def test_restore_rejects_a_missing_declared_member(tmp_path, session_env):
    """The manifest's files table is authoritative."""
    from cauveris.sessions.manifest import build_session_manifest, manifest_to_yaml

    manifest = build_session_manifest(
        "INC-1", [("session/pipeline/stages.json", b"{}")]
    )
    staging = tmp_path / "staged"
    (staging / "session" / "pipeline").mkdir(parents=True)
    (staging / SESSION_MANIFEST_PATH).write_bytes(manifest_to_yaml(manifest))

    restorer = SessionRestorer()
    with pytest.raises(SessionChecksumError):
        restorer._verify_checksums(staging, manifest)


def test_restore_rejects_a_wrong_format(tmp_path):
    """A manifest that declares another format is refused."""
    from cauveris.sessions.manifest import parse_manifest

    with pytest.raises(SessionFormatError):
        parse_manifest(b"format: something-else/v9\n")


def test_restored_event_log_matches_the_original_exactly(tmp_path):
    """
    The restored log is the original log, not the original log plus extras.

    Creating the canonical stage skeleton must not append a synthetic
    PIPELINE_INITIALIZED event on top of the imported history — otherwise a
    resumed investigation would report events that never happened.
    """
    store = PipelinePersistenceStore(db_path=str(tmp_path / "pipeline.db"))
    store.initialize_incident_stages("INC-SRC", overwrite=True, record_event=False)
    store.record_event("INC-SRC", "STAGE_STARTED", "one", {})
    store.record_event("INC-SRC", "STAGE_COMPLETED", "one", {})
    original = store.get_events("INC-SRC", limit=10_000)
    assert len(original) == 2

    store.import_stages(
        "INC-DST", [record.to_dict() for record in store.get_stages("INC-SRC")]
    )
    store.import_events("INC-DST", original)
    restored = store.get_events("INC-DST", limit=10_000)

    assert len(restored) == len(original)
    assert [e["event_type"] for e in restored] == [e["event_type"] for e in original]
    assert [e["stage_id"] for e in restored] == [e["stage_id"] for e in original]
    #: The archive's own numbering travels along as provenance.
    assert [e["payload"].get("source_sequence_id") for e in restored] == [
        e["sequence_id"] for e in original
    ]


def test_importing_a_session_does_not_steal_the_source_incidents_log(tmp_path):
    """
    A restore copies the log; it must not move it.

    ``sequence_id`` is the global primary key of ``pipeline_events``.  If the
    restore reused the source incident's ids, the source would lose its own
    history — importing a session package would silently erase the evidence
    trail of the investigation it came from.
    """
    store = PipelinePersistenceStore(db_path=str(tmp_path / "pipeline.db"))
    store.initialize_incident_stages("INC-SRC", overwrite=True, record_event=False)
    store.record_event("INC-SRC", "STAGE_STARTED", "one", {})
    store.record_event("INC-SRC", "STAGE_COMPLETED", "one", {})

    store.import_events("INC-DST", store.get_events("INC-SRC", limit=10_000))

    assert len(store.get_events("INC-SRC", limit=10_000)) == 2, (
        "the source incident lost its event log to the import"
    )
    assert len(store.get_events("INC-DST", limit=10_000)) == 2


def test_importing_a_session_twice_does_not_duplicate_events(tmp_path):
    """Re-importing the same log replaces it rather than doubling it."""
    store = PipelinePersistenceStore(db_path=str(tmp_path / "pipeline.db"))
    store.initialize_incident_stages("INC-SRC", overwrite=True, record_event=False)
    store.record_event("INC-SRC", "STAGE_STARTED", "one", {})

    events = store.get_events("INC-SRC", limit=10_000)
    store.import_events("INC-DST", events)
    store.import_events("INC-DST", events)

    assert len(store.get_events("INC-DST", limit=10_000)) == 1


def test_session_manifest_round_trips(session_env):
    """The manifest survives a serialization round-trip."""
    from cauveris.sessions.manifest import (
        build_session_manifest,
        manifest_to_yaml,
        parse_manifest,
    )

    manifest = build_session_manifest(
        "INC-9",
        [("artifacts/a.txt", b"hello")],
        title="Round trip",
        severity="critical",
        tags=["a", "b"],
        pipeline_state="RUNNING",
        active_stage_id="stage-3",
        report_present=True,
        session_id="ses-abc",
    )
    restored = parse_manifest(manifest_to_yaml(manifest))
    assert restored.incident_id == "INC-9"
    assert restored.title == "Round trip"
    assert restored.severity == "critical"
    assert restored.tags == ["a", "b"]
    assert restored.pipeline_state == "RUNNING"
    assert restored.active_stage_id == "stage-3"
    assert restored.report_present is True
    assert restored.session_id == "ses-abc"
    assert restored.files[0].path == "artifacts/a.txt"
    assert restored.files[0].sha256 == manifest.files[0].sha256

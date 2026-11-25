"""
Tests for operator-declared incident metadata and the custom_id defect.

The workspace creation wizard collects severity / category / environment /
tags / intake_method.  These tests pin the contract that the backend really
keeps what it is asked, that a hostile ``custom_id`` is rejected rather than
becoming a store path segment, and that the metadata survives a round-trip
through the incident manifest.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from cauveris.api.main import app, incidents
from cauveris.schemas.incident import Incident


@pytest.mark.asyncio
async def test_create_incident_keeps_operator_metadata(test_user):
    """Every metadata field the wizard asks for is persisted on the incident."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/incidents",
            headers=test_user["headers"],
            json={
                "title": "Fleet thermal anomaly",
                "description": "Coolant loop pressure dropped during shift B.",
                "system_name": "warehouse-amr-07",
                "severity": "high",
                "category": "control",
                "environment": "warehouse",
                "tags": ["thermal", "coolant-loop"],
                "intake_method": "manual",
            },
        )
        assert res.status_code == 200, res.text
        incident_id = res.json()["incident_id"]

        incident = incidents[incident_id]
        assert incident.title == "Fleet thermal anomaly"
        assert incident.severity == "high"
        assert incident.category == "control"
        assert incident.environment == "warehouse"
        assert incident.tags == ["thermal", "coolant-loop"]
        assert incident.intake_method == "manual"

        # The metadata must also live in the manifest, because the manifest is
        # what a session package serializes and what survives a restart.
        assert incident.manifest["severity"] == "high"
        assert incident.manifest["category"] == "control"
        assert incident.manifest["environment"] == "warehouse"
        assert incident.manifest["tags"] == ["thermal", "coolant-loop"]
        assert incident.manifest["intake_method"] == "manual"

        # And it must be visible through the read endpoint.
        detail = await client.get(
            f"/api/v1/incidents/{incident_id}", headers=test_user["headers"]
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["severity"] == "high"
        assert body["category"] == "control"
        assert body["environment"] == "warehouse"
        assert body["tags"] == ["thermal", "coolant-loop"]
        assert body["intake_method"] == "manual"


@pytest.mark.asyncio
async def test_list_incidents_exposes_metadata(test_user):
    """The launcher's "Open Recent" table needs the triage metadata."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/incidents",
            headers=test_user["headers"],
            json={
                "title": "Causal constellation check",
                "severity": "medium",
                "category": "detection",
                "tags": ["tri"],
            },
        )
        res = await client.get("/api/v1/incidents", headers=test_user["headers"])
        assert res.status_code == 200, res.text
        rows = res.json()["incidents"]
        assert rows, "expected at least one incident"
        row = next(r for r in rows if r["title"] == "Causal constellation check")
        assert row["severity"] == "medium"
        assert row["category"] == "detection"
        assert row["tags"] == ["tri"]


@pytest.mark.asyncio
async def test_custom_id_rejects_free_form_labels(test_user):
    """The old creation form sent ``custom_id: formData.tags``.

    The server used ``custom_id`` as the incident id, so an incident created
    with tags ``"memory-leak, oom"`` got an id of ``"memory-leak, oom"`` — a
    string that then became a path segment in the evidence and report stores.
    That must now be rejected with a 422.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/incidents",
            headers=test_user["headers"],
            json={"title": "Tagged incident", "custom_id": "memory-leak, oom"},
        )
        assert res.status_code == 422, res.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_id",
    [
        "../escape",
        "with/slash",
        "with\\backslash",
        "spaces are out",
        "x" * 65,
    ],
)
async def test_custom_id_rejects_unsafe_values(test_user, bad_id):
    """An explicit id becomes a store directory name, so it is constrained."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/incidents",
            headers=test_user["headers"],
            json={"title": "Bad id", "custom_id": bad_id},
        )
        assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_custom_id_is_used_verbatim_when_valid(test_user):
    """A conforming id is still honoured — it is an explicit override."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/incidents",
            headers=test_user["headers"],
            json={"title": "Explicit id", "custom_id": "CAU-0042"},
        )
        assert res.status_code == 200, res.text
        assert res.json()["incident_id"] == "CAU-0042"
        assert "CAU-0042" in incidents


@pytest.mark.asyncio
async def test_tags_never_become_the_incident_id(test_user):
    """Regression guard: tags stay labels and the id stays a uuid."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/incidents",
            headers=test_user["headers"],
            json={"title": "Tagged", "tags": ["memory-leak", "oom"]},
        )
        assert res.status_code == 200, res.text
        incident_id = res.json()["incident_id"]
        assert "memory-leak" not in incident_id
        assert "," not in incident_id
        assert incidents[incident_id].tags == ["memory-leak", "oom"]


@pytest.mark.asyncio
async def test_unknown_enumerated_values_are_rejected(test_user):
    """An unrecognized severity is a 422, not a silently stored string."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/incidents",
            headers=test_user["headers"],
            json={"title": "Bad severity", "severity": "catastrophic"},
        )
        assert res.status_code == 422, res.text


@pytest.mark.asyncio
async def test_enumerated_values_are_case_normalized(test_user):
    """The wizard sends lowercase, but a hand-written client may not."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/incidents",
            headers=test_user["headers"],
            json={"title": "Shouty", "severity": "HIGH", "environment": "Warehouse"},
        )
        assert res.status_code == 200, res.text
        incident_id = res.json()["incident_id"]
        assert incidents[incident_id].severity == "high"
        assert incidents[incident_id].environment == "warehouse"


def test_metadata_snapshot_round_trips():
    """The snapshot contract used by the sidecar and the session manifest."""
    incident = Incident(
        id="INC-X",
        title="T",
        severity="low",
        category="navigation",
        environment="lab",
        tags=["a", "b"],
        intake_method="archive",
    )
    snapshot = incident.metadata_snapshot()
    assert snapshot["severity"] == "low"
    assert snapshot["tags"] == ["a", "b"]
    # Empty values are omitted so the sidecar never carries a pile of Nones.
    assert "approximate_time" not in snapshot

    restored = Incident(id="INC-Y", title="T")
    restored.apply_metadata_snapshot(snapshot)
    assert restored.severity == "low"
    assert restored.category == "navigation"
    assert restored.environment == "lab"
    assert restored.tags == ["a", "b"]
    assert restored.intake_method == "archive"


def test_metadata_snapshot_omits_empty_tags():
    incident = Incident(id="INC-X", title="T", tags=[])
    assert "tags" not in incident.metadata_snapshot()


def test_apply_metadata_to_manifest_does_not_overwrite_shipped_values():
    """A shipped manifest wins where it defines the same key."""
    incident = Incident(id="INC-X", title="T", severity="high")
    incident.manifest = {"severity": "critical"}
    incident.apply_metadata_to_manifest()
    assert incident.manifest["severity"] == "critical"

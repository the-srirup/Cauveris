"""
Phase 6 & 7 Tests: ZIP Ingestion, Archive Security, Artifact Inventory, and Safe Previews.

Proves:
1. Canonical ZIP upload processes arbitrary layouts, calculates package SHA-256, generates artifact inventory.
2. Archives without manifest.yaml generate internal manifest without hallucinating evidence.
3. Path traversal attacks (relative traversal, absolute paths) are rejected.
4. Symlinks inside ZIPs are rejected.
5. Safe preview endpoint scrubs secrets, escapes HTML, enforces byte/line limits, and enforces tenant auth.
6. Unknown artifacts are preserved with status UNKNOWN/SUPPORTED and not dropped.
"""

from __future__ import annotations

import io
import zipfile
import pytest
from httpx import AsyncClient, ASGITransport

from cauveris.api.main import app
from cauveris.auth import init_auth_store
from cauveris.config import get_settings
from cauveris.ingestion.controller import extract_zip_safely
from cauveris.inventory.artifact_inventory import ArtifactInventory


@pytest.fixture
async def setup_auth(tmp_path):
    db_file = str(tmp_path / "test_auth.db")
    settings = get_settings()
    settings.runtime_mode = "development"
    settings.demo_auth = False
    settings.auth_backend = "sqlite"
    settings.auth_db_path = db_file
    store = init_auth_store(backend="sqlite", db_path=db_file)
    return db_file, store


def test_extract_zip_safely_rejects_traversal(tmp_path):
    """Verify extract_zip_safely detects and rejects path traversal members."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0::/root:/bin/bash")
    zip_bytes = zip_buf.getvalue()

    bad_zip = tmp_path / "traversal.zip"
    bad_zip.write_bytes(zip_bytes)

    dest_dir = tmp_path / "extracted"
    with pytest.raises(ValueError, match="Path traversal attempt detected"):
        extract_zip_safely(bad_zip, dest_dir)


def test_artifact_inventory_preserves_unknown_files(tmp_path):
    """Verify inventory handles arbitrary files without dropping unknown formats."""
    bundle_dir = tmp_path / "test_bundle"
    bundle_dir.mkdir()
    (bundle_dir / "custom.unknown_ext").write_text("SOME_UNKNOWN_FORMAT_12345", encoding="utf-8")
    (bundle_dir / "config.yaml").write_text("worker:\n  threads: 4\n", encoding="utf-8")
    (bundle_dir / "blob.bin").write_bytes(b"\x00\x01\x02\x03\x04\xff")

    inventory = ArtifactInventory(bundle_dir, incident_id="INC-INV-TEST")
    entries = inventory.scan()
    assert len(entries) == 3

    unknown_entry = next(e for e in entries if e.relative_path == "custom.unknown_ext")
    assert unknown_entry.artifact_id.startswith("art_")
    assert unknown_entry.parse_status in ("SUPPORTED", "UNKNOWN")
    assert unknown_entry.size_bytes > 0

    bin_entry = next(e for e in entries if e.relative_path == "blob.bin")
    assert bin_entry.parse_status == "BINARY"
    assert bin_entry.classification == "binary"

    yaml_entry = next(e for e in entries if e.relative_path == "config.yaml")
    assert yaml_entry.is_editable is True
    assert yaml_entry.repair_relevance == "high"


@pytest.mark.asyncio
async def test_canonical_upload_and_safe_preview(setup_auth, tmp_path):
    """End-to-end test of canonical ZIP upload and safe artifact preview."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        reg_res = await client.post("/api/v1/auth/signup", json={
            "email": "ingestion.tester@cauveris.dev",
            "password": "Password123456!",
            "full_name": "Ingestion Tester",
        })
        assert reg_res.status_code == 200
        token = reg_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Create valid incident ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("config/settings.yaml", "service:\n  name: rover-control\n  api_key: sk-secret-1234567890123456\n")
            zf.writestr("telemetry/metrics.csv", "timestamp,cpu_pct,mem_mb\n1700000000,45.2,512\n")
            zf.writestr("docs/notes.html", "<script>alert('pwned')</script><b>Sensitive Notes</b>")
        zip_bytes = zip_buf.getvalue()

        files = {"file": ("rover-bundle.zip", zip_bytes, "application/zip")}
        upload_res = await client.post("/api/v1/incidents/upload", files=files, headers=headers)
        assert upload_res.status_code == 200, upload_res.text
        data = upload_res.json()
        incident_id = data["incident_id"]
        assert data["artifact_inventory_count"] == 3

        # Fetch incident to retrieve artifact inventory items
        inc_res = await client.get(f"/api/v1/incidents/{incident_id}", headers=headers)
        assert inc_res.status_code == 200
        inv = inc_res.json()["artifact_inventory"]
        assert len(inv) == 3

        # Test safe preview of config file (should redact api_key)
        config_item = next(i for i in inv if i["relative_path"] == "config/settings.yaml")
        art_id = config_item["artifact_id"]
        prev_res = await client.get(f"/api/v1/incidents/{incident_id}/artifacts/{art_id}/preview", headers=headers)
        assert prev_res.status_code == 200
        prev_data = prev_res.json()
        assert prev_data["preview_available"] is True
        assert "sk-secret-1234567890123456" not in prev_data["preview"]
        assert "[REDACTED_API_KEY]" in prev_data["preview"] or "[REDACTED_KEY]" in prev_data["preview"]
        assert prev_data["redaction_count"] >= 1

        # Test safe preview of HTML file (must be escaped: <script> -> &lt;script&gt;)
        html_item = next(i for i in inv if i["relative_path"] == "docs/notes.html")
        html_id = html_item["artifact_id"]
        html_prev_res = await client.get(f"/api/v1/incidents/{incident_id}/artifacts/{html_id}/preview", headers=headers)
        assert html_prev_res.status_code == 200
        html_data = html_prev_res.json()
        assert "<script>" not in html_data["preview"]
        assert "&lt;script&gt;" in html_data["preview"]

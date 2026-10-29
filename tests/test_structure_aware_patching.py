"""
Tests for Structure-Aware Patching across YAML, JSON, TOML, INI, Env, Java Properties,
XML, Source Code, Checksum Recording, Clean Application, and Patch Selection.
"""

import hashlib
import pytest
from httpx import ASGITransport, AsyncClient

from cauveris.patch.config_locators import (
    YAMLConfigPlugin,
    JSONConfigPlugin,
    TOMLConfigPlugin,
    INIConfigPlugin,
    EnvFileConfigPlugin,
    JavaPropertiesConfigPlugin,
    XMLConfigPlugin,
    SourceCodeConfigPlugin,
)
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.incident import Incident
from cauveris.patch.generator import PatchGenerator
from cauveris.api.main import app, pipeline_contexts, incidents, PipelineContext
from cauveris.schemas.patch import PatchCandidate


def test_yaml_preserves_comments_and_format(tmp_path):
    plugin = YAMLConfigPlugin()
    yaml_file = tmp_path / "worker.yaml"
    yaml_content = """# Header comment
worker:
  # Internal comment
  batching_window_ms: 200 # inline comment
  workers: 1
"""
    yaml_file.write_text(yaml_content, encoding="utf-8")
    assert plugin.can_handle(yaml_file, yaml_content) is True

    loc = plugin.locate_parameter(yaml_file, ["batching_window_ms"])
    assert loc is not None
    key, val = loc
    assert val == 200

    edited = plugin.edit_parameter(yaml_file, key, 50)
    assert "# Header comment" in edited
    assert "# Internal comment" in edited
    assert "batching_window_ms: 50" in edited
    assert "workers: 1" in edited


def test_json_preserves_types_and_format(tmp_path):
    plugin = JSONConfigPlugin()
    json_file = tmp_path / "config.json"
    json_content = """{\n  "batching_window_ms": 200,\n  "enabled": true\n}"""
    json_file.write_text(json_content, encoding="utf-8")
    assert plugin.can_handle(json_file, json_content) is True

    loc = plugin.locate_parameter(json_file, ["batching_window_ms"])
    assert loc is not None
    key, val = loc
    assert val == 200

    edited = plugin.edit_parameter(json_file, key, 40)
    assert '"batching_window_ms": 40' in edited
    assert '"enabled": true' in edited


def test_toml_preserves_sections_and_comments(tmp_path):
    plugin = TOMLConfigPlugin()
    toml_file = tmp_path / "robot.toml"
    toml_content = """# Top level TOML comment
[inference]
# Batch window comment
batching_window_ms = 200 # Inline comment
workers = 4
"""
    toml_file.write_text(toml_content, encoding="utf-8")
    assert plugin.can_handle(toml_file, toml_content) is True

    loc = plugin.locate_parameter(toml_file, ["batching_window_ms"])
    assert loc is not None
    key, val = loc
    assert val == 200

    edited = plugin.edit_parameter(toml_file, key, 25)
    assert "[inference]" in edited
    assert "# Batch window comment" in edited
    assert "batching_window_ms = 25" in edited
    assert "workers = 4" in edited


def test_ini_preserves_sections(tmp_path):
    plugin = INIConfigPlugin()
    ini_file = tmp_path / "server.ini"
    ini_content = """[server]
# Timeout config
request_timeout_ms = 500
workers = 2
"""
    ini_file.write_text(ini_content, encoding="utf-8")
    assert plugin.can_handle(ini_file, ini_content) is True

    loc = plugin.locate_parameter(ini_file, ["request_timeout_ms"])
    assert loc is not None
    key, val = loc

    edited = plugin.edit_parameter(ini_file, key, 1000)
    assert "[server]" in edited
    assert "request_timeout_ms = 1000" in edited or "request_timeout_ms=1000" in edited


def test_env_file_preserves_comments(tmp_path):
    plugin = EnvFileConfigPlugin()
    env_file = tmp_path / ".env"
    env_content = """# Environment configuration
BATCHING_WINDOW_MS=200 # timeout in ms
WORKERS=1
"""
    env_file.write_text(env_content, encoding="utf-8")
    assert plugin.can_handle(env_file, env_content) is True

    loc = plugin.locate_parameter(env_file, ["batching_window_ms"])
    assert loc is not None
    key, val = loc

    edited = plugin.edit_parameter(env_file, key, "50")
    assert "# Environment configuration" in edited
    assert "BATCHING_WINDOW_MS=50" in edited


def test_java_properties_plugin(tmp_path):
    plugin = JavaPropertiesConfigPlugin()
    prop_file = tmp_path / "app.properties"
    prop_content = """# Database pool
db.pool.size=10
db.timeout=5000
"""
    prop_file.write_text(prop_content, encoding="utf-8")
    assert plugin.can_handle(prop_file, prop_content) is True

    loc = plugin.locate_parameter(prop_file, ["db_pool_size", "pool.size"])
    assert loc is not None
    key, val = loc

    edited = plugin.edit_parameter(prop_file, key, "25")
    assert "# Database pool" in edited
    assert "db.pool.size=25" in edited


def test_xml_plugin_tag_and_attribute(tmp_path):
    plugin = XMLConfigPlugin()
    xml_file = tmp_path / "config.xml"
    xml_content = """<configuration>
  <batchingWindowMs>200</batchingWindowMs>
</configuration>"""
    xml_file.write_text(xml_content, encoding="utf-8")
    assert plugin.can_handle(xml_file, xml_content) is True

    loc = plugin.locate_parameter(xml_file, ["batchingWindowMs"])
    assert loc is not None
    key, val = loc
    assert val == "200"

    edited = plugin.edit_parameter(xml_file, key, "75")
    assert "<batchingWindowMs>75</batchingWindowMs>" in edited


def test_source_code_scalar_replacement(tmp_path):
    plugin = SourceCodeConfigPlugin()
    py_file = tmp_path / "worker.py"
    py_content = """class Worker:
    def __init__(self):
        self.batching_window_ms = 200.0
        self.workers = 1
"""
    py_file.write_text(py_content, encoding="utf-8")
    assert plugin.can_handle(py_file, py_content) is True

    loc = plugin.locate_parameter(py_file, ["batching_window_ms"])
    assert loc is not None
    name, val = loc
    assert val == 200.0

    edited = plugin.edit_parameter(py_file, name, 60.0)
    assert "self.batching_window_ms = 60" in edited
    assert "self.workers = 1" in edited


@pytest.mark.asyncio
async def test_patch_generator_checksums_and_application(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    cfg_dir = bundle / "config"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "worker.yaml"
    initial_content = "batching_window_ms: 200\n"
    cfg_file.write_text(initial_content, encoding="utf-8")
    manifest = bundle / "manifest.yaml"
    manifest.write_text("incident_id: INC-PATCH-01\n", encoding="utf-8")

    incident = Incident(
        id="INC-PATCH-01",
        title="Patch test incident",
        bundle_path=str(bundle),
    )

    exp = Experiment(
        experiment_id="exp-01",
        hypothesis_id="h_batching",
        incident_id="INC-PATCH-01",
        branch_name="branch_01",
        intervention="Reduce batching window to 50 ms",
        proposed_changes=[
            {
                "parameter": "batching_window_ms",
                "target_value": 50,
                "file": "config/worker.yaml",
                "config_key": "batching_window_ms",
            }
        ],
        status="COMPLETED",
        reproduction_rate=0.0,
    )

    forge = PatchGenerator(bundle_root=bundle, incident=incident)
    patches = await forge.generate([exp], incident=incident)

    assert len(patches) == 1
    p = patches[0]
    assert p.candidate_id == "patch-exp-01"
    assert p.incident_id == "INC-PATCH-01"
    assert p.hypothesis_id == "h_batching"
    assert p.target_file == "config/worker.yaml"
    assert p.applied_cleanly is True
    assert p.applies_cleanly is True
    assert p.lines_changed > 0
    assert p.unified_diff.strip() != ""

    # Verify checksums
    expected_before = hashlib.sha256(initial_content.encode("utf-8")).hexdigest()
    assert p.before_hash == expected_before
    assert p.after_hash is not None
    assert p.after_hash != p.before_hash
    assert "config/worker.yaml" in p.file_checksums
    assert p.file_checksums["config/worker.yaml"]["before"] == expected_before


@pytest.mark.asyncio
async def test_patch_selection_endpoint(test_user):
    headers = test_user["headers"]
    user_id = test_user["user"].id
    org_id = test_user["org"].id

    incident_id = "INC-SELECT-01"
    inc = Incident(id=incident_id, title="Test Incident")
    inc._owner_user_id = user_id
    inc._owner_org_id = org_id
    incidents[incident_id] = inc
    ctx = PipelineContext(incident=inc)
    cand1 = PatchCandidate(
        candidate_id="patch-cand-1",
        incident_id=incident_id,
        unified_diff="--- a/cfg\n+++ b/cfg\n@@ -1 +1 @@\n-200\n+50\n",
        affected_files=["cfg.yaml"],
        target_file="cfg.yaml",
        is_selected=False,
    )
    cand2 = PatchCandidate(
        candidate_id="patch-cand-2",
        incident_id=incident_id,
        unified_diff="--- a/cfg\n+++ b/cfg\n@@ -1 +1 @@\n-200\n+25\n",
        affected_files=["cfg.yaml"],
        target_file="cfg.yaml",
        is_selected=False,
    )
    ctx.patch_candidates = [cand1, cand2]
    pipeline_contexts[incident_id] = ctx

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Fetch specific candidate
        res = await ac.get(f"/api/v1/incidents/{incident_id}/patches/patch-cand-1", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["patch_candidate"]["candidate_id"] == "patch-cand-1"
        assert data["patch_candidate"]["is_selected"] is False

        # 2. Select cand2
        sel_res = await ac.post(f"/api/v1/incidents/{incident_id}/patches/patch-cand-2/select", headers=headers)
        assert sel_res.status_code == 200
        sel_data = sel_res.json()
        assert sel_data["selected_candidate_id"] == "patch-cand-2"
        assert sel_data["is_selected"] is True

        # 3. Verify cand2 is selected and cand1 is not
        list_res = await ac.get(f"/api/v1/incidents/{incident_id}/patches", headers=headers)
        assert list_res.status_code == 200
        list_data = list_res.json()
        candidates = list_data["patch_candidates"]
        cand1_entry = next(c for c in candidates if c["candidate_id"] == "patch-cand-1")
        cand2_entry = next(c for c in candidates if c["candidate_id"] == "patch-cand-2")
        assert cand1_entry["is_selected"] is False
        assert cand2_entry["is_selected"] is True

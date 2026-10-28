"""
Tests for Config Locators and Safe Patching across 7 configuration formats:
- YAML
- JSON
- TOML
- INI/CFG
- Environment files (.env)
- XML
- Java Properties

Verifies comments, structure, key order, and unrelated content are preserved.
No blind regex replacement.
"""

from pathlib import Path
import pytest
from cauveris.patch.config_locators import (
    ConfigLocatorRegistry,
    YAMLConfigPlugin,
    JSONConfigPlugin,
    TOMLConfigPlugin,
    INIConfigPlugin,
    EnvFileConfigPlugin,
    XMLConfigPlugin,
    JavaPropertiesConfigPlugin,
)


def test_yaml_config_patching(tmp_path: Path):
    yaml_path = tmp_path / "service.yaml"
    content = """# Primary Service Config
version: "3.8"
settings:
  batching_window_ms: 200 # important delay comment
  workers: 4
other_flag: true
"""
    yaml_path.write_text(content, encoding="utf-8")
    registry = ConfigLocatorRegistry()
    res = registry.find_and_edit(yaml_path, ["batching_window_ms", "batch_window"], 50)
    assert res is not None
    fmt, key, old_val, new_content = res
    assert fmt == "yaml"
    assert "batching_window_ms: 50" in new_content
    assert "# important delay comment" in new_content
    assert "other_flag: true" in new_content


def test_json_config_patching(tmp_path: Path):
    json_path = tmp_path / "config.json"
    content = '{\n  "service": "api",\n  "timeout_ms": 1000,\n  "enabled": true\n}'
    json_path.write_text(content, encoding="utf-8")
    registry = ConfigLocatorRegistry()
    res = registry.find_and_edit(json_path, ["timeout_ms", "timeout"], 2500)
    assert res is not None
    fmt, key, old_val, new_content = res
    assert fmt == "json"
    assert '"timeout_ms": 2500' in new_content
    assert '"service": "api"' in new_content


def test_toml_config_patching(tmp_path: Path):
    toml_path = tmp_path / "config.toml"
    content = """# Application TOML
[server]
port = 8080
timeout_seconds = 30 # keep alive timeout
debug = false
"""
    toml_path.write_text(content, encoding="utf-8")
    registry = ConfigLocatorRegistry()
    res = registry.find_and_edit(toml_path, ["timeout_seconds", "timeout"], 60)
    assert res is not None
    fmt, key, old_val, new_content = res
    assert fmt == "toml"
    assert "timeout_seconds = 60" in new_content
    assert "# keep alive timeout" in new_content
    assert "port = 8080" in new_content


def test_ini_config_patching(tmp_path: Path):
    ini_path = tmp_path / "app.ini"
    content = """[agent]
# Worker pool settings
workers = 4
max_memory_mb = 1024
"""
    ini_path.write_text(content, encoding="utf-8")
    registry = ConfigLocatorRegistry()
    res = registry.find_and_edit(ini_path, ["workers", "worker_count"], 8)
    assert res is not None
    fmt, key, old_val, new_content = res
    assert fmt == "ini"
    assert "workers = 8" in new_content or "workers=8" in new_content
    assert "max_memory_mb = 1024" in new_content


def test_env_file_patching(tmp_path: Path):
    env_path = tmp_path / ".env"
    content = """# Environment Variables
PORT=5000
TIMEOUT_MS=300 # request deadline
CACHE_ENABLED=true
"""
    env_path.write_text(content, encoding="utf-8")
    registry = ConfigLocatorRegistry()
    res = registry.find_and_edit(env_path, ["timeout_ms", "timeout"], 500)
    assert res is not None
    fmt, key, old_val, new_content = res
    assert fmt == "env"
    assert "TIMEOUT_MS=500" in new_content
    assert "# request deadline" in new_content
    assert "PORT=5000" in new_content


def test_xml_config_patching(tmp_path: Path):
    xml_path = tmp_path / "config.xml"
    content = """<?xml version="1.0"?>
<appSettings>
  <!-- Connection parameters -->
  <timeout>120</timeout>
  <poolSize>10</poolSize>
</appSettings>
"""
    xml_path.write_text(content, encoding="utf-8")
    registry = ConfigLocatorRegistry()
    res = registry.find_and_edit(xml_path, ["timeout"], 300)
    assert res is not None
    fmt, key, old_val, new_content = res
    assert fmt == "xml"
    assert "<timeout>300</timeout>" in new_content
    assert "<poolSize>10</poolSize>" in new_content
    assert "<!-- Connection parameters -->" in new_content


def test_java_properties_patching(tmp_path: Path):
    prop_path = tmp_path / "application.properties"
    content = """# Database and thread config
server.workers = 16
db.timeout = 5000
"""
    prop_path.write_text(content, encoding="utf-8")
    registry = ConfigLocatorRegistry()
    res = registry.find_and_edit(prop_path, ["workers", "server.workers"], 32)
    assert res is not None
    fmt, key, old_val, new_content = res
    assert fmt == "java_properties"
    assert "server.workers = 32" in new_content
    assert "db.timeout = 5000" in new_content

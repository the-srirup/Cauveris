"""
Tests for Artifact Inventory and Safe Content-Based Type Detection.
Ensures no uploaded files are executed during detection and all files appear in inventory.
"""

import json
from pathlib import Path

from cauveris.inventory.artifact_inventory import (
    ArtifactInventory,
    ContentTypeDetector,
)


def test_content_type_detection_various_formats(tmp_path: Path):
    # 1. JSON
    json_file = tmp_path / "sample.unknown_ext"
    json_file.write_text(json.dumps({"key": "value", "timeout": 120}), encoding="utf-8")
    det_type, mime, enc = ContentTypeDetector.detect(json_file)
    assert det_type == "json"
    assert mime == "application/json"

    # 2. JSONL
    jsonl_file = tmp_path / "stream.dat"
    jsonl_file.write_text('{"event": 1}\n{"event": 2}\n', encoding="utf-8")
    det_type, mime, enc = ContentTypeDetector.detect(jsonl_file)
    assert det_type == "jsonl"
    assert mime == "application/x-jsonlines"

    # 3. YAML
    yaml_file = tmp_path / "config.unknown"
    yaml_file.write_text("worker_count: 8\nqueue_depth: 100\n", encoding="utf-8")
    det_type, mime, enc = ContentTypeDetector.detect(yaml_file)
    assert det_type == "yaml"
    assert mime == "text/yaml"

    # 4. Kubernetes YAML
    k8s_file = tmp_path / "deploy.txt"
    k8s_file.write_text("apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: worker\n", encoding="utf-8")
    det_type, mime, enc = ContentTypeDetector.detect(k8s_file)
    assert det_type == "yaml/kubernetes"

    # 5. XML
    xml_file = tmp_path / "app_config.bin"
    xml_file.write_text("<configuration><timeout_ms>500</timeout_ms></configuration>", encoding="utf-8")
    det_type, mime, enc = ContentTypeDetector.detect(xml_file)
    assert det_type == "xml"

    # 6. INI
    ini_file = tmp_path / "custom.conf"
    ini_file.write_text("[server]\nworkers = 4\ntimeout = 30\n", encoding="utf-8")
    det_type, mime, enc = ContentTypeDetector.detect(ini_file)
    assert det_type == "ini"

    # 7. CSV
    csv_file = tmp_path / "metrics.dat"
    csv_file.write_text("timestamp,latency,cpu\n100,25.5,80.2\n101,26.0,81.0\n", encoding="utf-8")
    det_type, mime, enc = ContentTypeDetector.detect(csv_file)
    assert det_type in ("csv", "metric/csv")

    # 8. Plain log
    log_file = tmp_path / "sys.out"
    log_file.write_text("[INFO] 2026-10-27 Worker started\n[ERROR] Connection failed\n", encoding="utf-8")
    det_type, mime, enc = ContentTypeDetector.detect(log_file)
    assert det_type == "log"

    # 9. Binary file
    bin_file = tmp_path / "blob.data"
    bin_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\x00\x00random_bytes")
    det_type, mime, enc = ContentTypeDetector.detect(bin_file)
    assert det_type == "binary"
    assert mime == "application/octet-stream"


def test_artifact_inventory_scanner_inventories_unknown_artifacts(tmp_path: Path):
    bundle = tmp_path / "arbitrary_bundle"
    bundle.mkdir()

    # Create various files including completely unknown ones
    (bundle / "known.json").write_text('{"a": 1}', encoding="utf-8")
    (bundle / "weird_name.bin").write_bytes(b"\x00\xff\xee\xdd\x00")
    (bundle / "service.log").write_text("ERROR OOMKilled process", encoding="utf-8")

    inventory = ArtifactInventory(bundle)
    entries = inventory.scan()

    assert len(entries) == 3
    rel_paths = {e.relative_path for e in entries}
    assert "known.json" in rel_paths
    assert "weird_name.bin" in rel_paths
    assert "service.log" in rel_paths

    bin_entry = next(e for e in entries if e.relative_path == "weird_name.bin")
    assert bin_entry.parse_status in ("skipped_binary", "BINARY")
    assert bin_entry.is_editable is False
    assert bin_entry.contributes_to_diagnosis is False
    assert len(bin_entry.checksum_sha256) == 64


def test_jsonl_artifacts_are_parsed_as_jsonl_not_json(tmp_path: Path):
    """A JSONL file must not be handed to the single-document JSON parser.

    ``metric/jsonl`` starts with ``metric/json``, so a prefix test that does
    not distinguish the two subtypes routed every JSONL file through
    ``json.load()``.  That always fails on a multi-line document, and the
    inventory then reported the file as unparsable.
    """
    bundle = tmp_path / "jsonl_bundle"
    bundle.mkdir()

    (bundle / "stream.jsonl").write_text(
        '{"event": 1, "latency_ms": 10}\n{"event": 2, "latency_ms": 20}\n',
        encoding="utf-8",
    )
    (bundle / "records.ndjson").write_text(
        '{"ts": "2026-10-20T10:00:00Z", "level": "error"}\n'
        '{"ts": "2026-10-20T10:00:01Z", "level": "info"}\n',
        encoding="utf-8",
    )

    # The detector classifies metric-bearing JSONL under the metric subtype.
    (bundle / "telemetry.jsonl").write_text(
        '{"timestamp": 1, "latency_ms": 30, "value": 1}\n'
        '{"timestamp": 2, "latency_ms": 40, "value": 2}\n',
        encoding="utf-8",
    )

    entries = {e.relative_path: e for e in ArtifactInventory(bundle).scan()}

    for name in ("stream.jsonl", "records.ndjson", "telemetry.jsonl"):
        entry = entries[name]
        assert entry.parse_status in ("parsed", "SUPPORTED"), f"{name}: {entry.warnings}"
        assert entry.parser_selected == "jsonlines"
        assert entry.record_count == 2
        assert entry.contributes_to_diagnosis is True

    # A single-document JSON file is still parsed as JSON.
    (bundle / "config.json").write_text('{"a": 1, "b": 2}', encoding="utf-8")
    entries = {e.relative_path: e for e in ArtifactInventory(bundle).scan()}
    assert entries["config.json"].parser_selected == "json"
    assert entries["config.json"].parse_status in ("parsed", "SUPPORTED")

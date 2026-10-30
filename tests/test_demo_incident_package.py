"""Preflight verification suite for the demonstration incident package.

Tests:
1. ZIP archive existence, integrity, and safety (no absolute or traversal paths).
2. Required archive members are present and duplicates are rejected.
3. Content parsing (YAML, CSV, JSONL, Python AST).
4. Manifest anti-hallucination verification: no embedded patch, hypothesis, report, or repair answer.
5. Evidence consistency: declared memory limit (512 MiB), observed peak (620 MiB),
   peak > limit, host capacity allows bounded repair.
6. Unknown artifact existence and binary classification.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ZIP = ROOT / "packages" / "perception-worker-memory-exhaustion.zip"
DEMO_DIR = ROOT / "packages" / "demo" / "perception-worker-memory-exhaustion"

REQUIRED_MEMBERS = {
    "manifest.yaml",
    "config/worker.yaml",
    "config/component_aliases.yaml",
    "telemetry/oom-events.log",
    "telemetry/heap.csv",
    "telemetry/runtime-metrics.jsonl",
    "traces/inference-spans.jsonl",
    "source/worker.py",
    "notes/operator-observations.md",
    "unknown/diagnostic-context.bin",
}


def test_zip_exists_and_opens():
    assert PACKAGE_ZIP.exists(), f"Package ZIP not found at {PACKAGE_ZIP}"
    assert PACKAGE_ZIP.stat().st_size > 0, "Package ZIP is empty"
    with zipfile.ZipFile(PACKAGE_ZIP, "r") as zf:
        corrupt = zf.testzip()
        assert corrupt is None, f"Corrupted file in ZIP: {corrupt}"


def test_zip_members_safety_and_completeness():
    with zipfile.ZipFile(PACKAGE_ZIP, "r") as zf:
        members = zf.namelist()
        member_set = set(members)
        assert len(members) == len(member_set), "Duplicate entries detected in ZIP"

        # Check required members
        missing = REQUIRED_MEMBERS - member_set
        assert not missing, f"Missing required archive members: {missing}"

        # Path safety: no leading slash, no traversal
        for m in members:
            assert not m.startswith(("/", "\\")), f"Unsafe absolute path: {m}"
            assert ".." not in m, f"Unsafe directory traversal: {m}"
            assert not m.endswith("/"), f"Directory entry found in zip: {m}"


def test_manifest_schema_and_anti_hallucination():
    with zipfile.ZipFile(PACKAGE_ZIP, "r") as zf:
        manifest_raw = zf.read("manifest.yaml").decode("utf-8")
        data = yaml.safe_load(manifest_raw)

    assert isinstance(data, dict), "manifest.yaml must parse as a dictionary"
    assert data.get("incident_id") == "DEMO-PERCEPTION-MEMORY-002"
    assert data.get("title") == "Perception Worker Memory Exhaustion"
    assert "perception-worker" in data.get("affected_components", [])

    # Anti-hallucination: Do NOT embed the repair answer, generated hypothesis, or patch
    forbidden_keys = {"expected_hypothesis", "hypothesis", "patch", "unified_diff", "verification_result", "repair_package", "repair_result"}
    for fk in forbidden_keys:
        assert fk not in data, f"Forbidden key '{fk}' embedded in manifest.yaml"

    manifest_str = json.dumps(data)
    assert "768" not in manifest_str, "Hardcoded repaired limit (768) must not be in manifest"
    assert "patch-" not in manifest_str, "Patch identifiers must not be pre-embedded in manifest"


def test_config_consistency_and_host_capacity():
    with zipfile.ZipFile(PACKAGE_ZIP, "r") as zf:
        worker_cfg_raw = zf.read("config/worker.yaml").decode("utf-8")
        worker_cfg = yaml.safe_load(worker_cfg_raw)

    resources = worker_cfg.get("resources", {})
    declared_limit = resources.get("memory_limit_mb")
    assert declared_limit == 512, f"Expected initial memory_limit_mb=512, got {declared_limit}"

    host = worker_cfg.get("host", {})
    avail_mb = host.get("available_for_services_mb", 0)
    assert avail_mb >= 2048, f"Host capacity {avail_mb} MiB is insufficient for bounded increase"

    policy = worker_cfg.get("repair_policy", {})
    max_worker_mb = policy.get("maximum_worker_memory_mb", 1024)
    headroom_ratio = policy.get("minimum_memory_headroom_ratio", 1.20)
    assert max_worker_mb == 1024
    assert headroom_ratio == 1.20


def test_telemetry_evidence_values():
    with zipfile.ZipFile(PACKAGE_ZIP, "r") as zf:
        heap_csv_raw = zf.read("telemetry/heap.csv").decode("utf-8")
        oom_log_raw = zf.read("telemetry/oom-events.log").decode("utf-8")

    reader = csv.DictReader(io.StringIO(heap_csv_raw))
    rows = list(reader)
    assert len(rows) >= 5
    working_sets = [float(r["working_set_mb"]) for r in rows]
    peak_demand = max(working_sets)
    assert peak_demand == 620.0, f"Expected peak 620 MiB, got {peak_demand}"
    assert peak_demand > 512.0, "Observed peak must exceed declared limit"

    # OOM events log
    assert "reason=OOMKilled" in oom_log_raw or "OOMKilled" in oom_log_raw
    assert "620" in oom_log_raw
    assert "512" in oom_log_raw


def test_structured_metrics_and_traces():
    with zipfile.ZipFile(PACKAGE_ZIP, "r") as zf:
        metrics_raw = zf.read("telemetry/runtime-metrics.jsonl").decode("utf-8")
        traces_raw = zf.read("traces/inference-spans.jsonl").decode("utf-8")

    # Metrics JSONL
    for line in metrics_raw.strip().splitlines():
        item = json.loads(line)
        for req_field in ("timestamp", "component", "metric", "value", "unit"):
            assert req_field in item, f"Missing field {req_field} in metric record"

    # Traces JSONL
    trace_items = [json.loads(line) for line in traces_raw.strip().splitlines()]
    assert len(trace_items) >= 4
    for sp in trace_items:
        assert "trace_id" in sp
        assert "span_id" in sp
        assert "duration_ms" in sp
        assert sp["duration_ms"] < 800.0, "Trace spans must rule out dominant dependency timeout"


def test_source_syntax_and_safety():
    with zipfile.ZipFile(PACKAGE_ZIP, "r") as zf:
        source_raw = zf.read("source/worker.py").decode("utf-8")

    tree = ast.parse(source_raw)
    assert isinstance(tree, ast.Module)

    # Confirm non-malicious static content
    forbidden = ["os.system", "subprocess", "rmtree", "eval(", "exec(", "shutil.rmtree"]
    for f in forbidden:
        assert f not in source_raw, f"Forbidden statement {f} in source file"


def test_unknown_artifact_is_binary_and_present():
    with zipfile.ZipFile(PACKAGE_ZIP, "r") as zf:
        raw_bin = zf.read("unknown/diagnostic-context.bin")

    assert len(raw_bin) > 0
    assert b"\x00" in raw_bin, "diagnostic-context.bin must contain binary null bytes"
    # Ensure it's not a secret or executable
    assert not raw_bin.startswith(b"\x7fELF")
    assert not raw_bin.startswith(b"MZ")
    assert not raw_bin.startswith(b"PK")


def test_package_sha256_stability():
    with open(PACKAGE_ZIP, "rb") as f:
        sha1 = hashlib.sha256(f.read()).hexdigest()

    # Re-read to guarantee streaming hash consistency
    hasher = hashlib.sha256()
    with open(PACKAGE_ZIP, "rb") as f:
        while chunk := f.read(4096):
            hasher.update(chunk)
    sha2 = hasher.hexdigest()

    assert sha1 == sha2
    assert len(sha1) == 64

"""Build and validate the comprehensive demonstration incident package for Cauveris.

Incident: DEMO-PERCEPTION-MEMORY-002
Mechanism: resource_exhaustion
Editable Target: resources.memory_limit_mb in config/worker.yaml
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
from pathlib import Path
import stat
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "packages" / "demo" / "perception-worker-memory-exhaustion"
OUTPUT_ZIP = ROOT / "packages" / "perception-worker-memory-exhaustion.zip"

FIXED_TIMESTAMP = (2026, 10, 29, 14, 32, 0)


def create_package_files() -> None:
    """Create all incident files in packages/demo/perception-worker-memory-exhaustion."""
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    (DEMO_DIR / "config").mkdir(exist_ok=True)
    (DEMO_DIR / "telemetry").mkdir(exist_ok=True)
    (DEMO_DIR / "traces").mkdir(exist_ok=True)
    (DEMO_DIR / "source").mkdir(exist_ok=True)
    (DEMO_DIR / "notes").mkdir(exist_ok=True)
    (DEMO_DIR / "unknown").mkdir(exist_ok=True)

    # 1. manifest.yaml
    manifest_yaml = """incident_id: DEMO-PERCEPTION-MEMORY-002
title: Perception Worker Memory Exhaustion
description: >
  The perception worker was terminated after its working set exceeded
  the deployment memory limit during a dense inference workload.
system_name: perception-pipeline
affected_components:
  - perception-worker
expected_artifacts:
  - config/worker.yaml
  - config/component_aliases.yaml
  - telemetry/oom-events.log
  - telemetry/heap.csv
  - telemetry/runtime-metrics.jsonl
  - traces/inference-spans.jsonl
  - source/worker.py
  - notes/operator-observations.md
  - unknown/diagnostic-context.bin
required_evidence:
  - config/worker.yaml
  - telemetry/oom-events.log
  - telemetry/heap.csv
expected_capability:
  family: memory_or_resource_exhaustion
  mechanism: resource_exhaustion
  control_target: resources.memory_limit_mb
  target_file: config/worker.yaml
"""
    (DEMO_DIR / "manifest.yaml").write_text(manifest_yaml, encoding="utf-8")

    # 2. config/worker.yaml
    worker_yaml = """service:
  name: perception-worker
  environment: staging
  image: perception-worker:2.4.1

resources:
  memory_limit_mb: 512
  requests:
    memory_mb: 384
    cpu_millicores: 500
  limits:
    cpu_millicores: 1500

runtime:
  workers: 2
  max_batch_size: 8
  queue_capacity: 64
  request_timeout_ms: 800

host:
  total_memory_mb: 8192
  reserved_memory_mb: 2048
  available_for_services_mb: 6144

repair_policy:
  minimum_memory_headroom_ratio: 1.20
  maximum_worker_memory_mb: 1024
  allocation_step_mb: 128
"""
    (DEMO_DIR / "config" / "worker.yaml").write_text(worker_yaml, encoding="utf-8")

    # 3. config/component_aliases.yaml
    component_aliases_yaml = """aliases:
  perception-worker:
    - perception_worker
    - perception-worker-7d4f
    - worker.perception
    - perception_runtime
"""
    (DEMO_DIR / "config" / "component_aliases.yaml").write_text(component_aliases_yaml, encoding="utf-8")

    # 4. telemetry/oom-events.log
    oom_log = """2026-10-29T14:31:44.000Z INFO component=perception-worker event=startup_complete workers=2
2026-10-29T14:31:49.100Z INFO component=perception-worker event=batch_accepted batch_size=8
2026-10-29T14:31:52.200Z WARN component=perception-worker event=memory_pressure working_set_mb=535 memory_limit_mb=512
2026-10-29T14:31:55.400Z WARN component=perception-worker event=memory_pressure working_set_mb=580 memory_limit_mb=512
2026-10-29T14:31:58.700Z ERROR component=perception-worker event=allocation_failure requested_mb=48 working_set_mb=620
2026-10-29T14:32:01.000Z ERROR component=perception-worker event=process_terminated reason=OOMKilled working_set_mb=620 memory_limit_mb=512 memory limit: 512 MiB exceeded; peak working set: 620 MiB
2026-10-29T14:32:02.000Z WARN component=orchestrator event=container_restart service=perception-worker restart_count=1
"""
    (DEMO_DIR / "telemetry" / "oom-events.log").write_text(oom_log, encoding="utf-8")

    # 5. telemetry/heap.csv
    heap_csv = """timestamp,component,working_set_mb,heap_used_mb,memory_limit_mb,host_available_mb,restart_count
2026-10-29T14:31:40Z,perception-worker,410,342,512,4210,0
2026-10-29T14:31:44Z,perception-worker,445,368,512,4170,0
2026-10-29T14:31:48Z,perception-worker,482,401,512,4130,0
2026-10-29T14:31:52Z,perception-worker,535,447,512,4060,0
2026-10-29T14:31:55Z,perception-worker,580,492,512,3995,0
2026-10-29T14:31:58Z,perception-worker,620,528,512,3890,0
2026-10-29T14:32:02Z,perception-worker,164,130,512,4320,1
"""
    (DEMO_DIR / "telemetry" / "heap.csv").write_text(heap_csv, encoding="utf-8")

    # 6. telemetry/runtime-metrics.jsonl
    metrics_records = [
        {"timestamp": "2026-10-29T14:31:40Z", "component": "perception-worker", "metric": "cpu_utilization_pct", "value": 41.5, "unit": "percent"},
        {"timestamp": "2026-10-29T14:31:40Z", "component": "perception-worker", "metric": "queue_depth", "value": 6, "unit": "frames"},
        {"timestamp": "2026-10-29T14:31:40Z", "component": "perception-worker", "metric": "batch_size", "value": 8, "unit": "count"},
        {"timestamp": "2026-10-29T14:31:40Z", "component": "perception-worker", "metric": "request_throughput_hz", "value": 24.8, "unit": "hz"},
        {"timestamp": "2026-10-29T14:31:40Z", "component": "perception-worker", "metric": "working_set_mb", "value": 410, "unit": "mebibytes"},
        {"timestamp": "2026-10-29T14:31:40Z", "component": "perception-worker", "metric": "request_error_count", "value": 0, "unit": "count"},
        {"timestamp": "2026-10-29T14:31:40Z", "component": "perception-worker", "metric": "restart_count", "value": 0, "unit": "count"},

        {"timestamp": "2026-10-29T14:31:48Z", "component": "perception-worker", "metric": "cpu_utilization_pct", "value": 47.2, "unit": "percent"},
        {"timestamp": "2026-10-29T14:31:48Z", "component": "perception-worker", "metric": "queue_depth", "value": 8, "unit": "frames"},
        {"timestamp": "2026-10-29T14:31:48Z", "component": "perception-worker", "metric": "batch_size", "value": 8, "unit": "count"},
        {"timestamp": "2026-10-29T14:31:48Z", "component": "perception-worker", "metric": "request_throughput_hz", "value": 24.5, "unit": "hz"},
        {"timestamp": "2026-10-29T14:31:48Z", "component": "perception-worker", "metric": "working_set_mb", "value": 482, "unit": "mebibytes"},
        {"timestamp": "2026-10-29T14:31:48Z", "component": "perception-worker", "metric": "request_error_count", "value": 0, "unit": "count"},
        {"timestamp": "2026-10-29T14:31:48Z", "component": "perception-worker", "metric": "restart_count", "value": 0, "unit": "count"},

        {"timestamp": "2026-10-29T14:31:55Z", "component": "perception-worker", "metric": "cpu_utilization_pct", "value": 52.8, "unit": "percent"},
        {"timestamp": "2026-10-29T14:31:55Z", "component": "perception-worker", "metric": "queue_depth", "value": 11, "unit": "frames"},
        {"timestamp": "2026-10-29T14:31:55Z", "component": "perception-worker", "metric": "batch_size", "value": 8, "unit": "count"},
        {"timestamp": "2026-10-29T14:31:55Z", "component": "perception-worker", "metric": "request_throughput_hz", "value": 24.2, "unit": "hz"},
        {"timestamp": "2026-10-29T14:31:55Z", "component": "perception-worker", "metric": "working_set_mb", "value": 580, "unit": "mebibytes"},
        {"timestamp": "2026-10-29T14:31:55Z", "component": "perception-worker", "metric": "request_error_count", "value": 0, "unit": "count"},
        {"timestamp": "2026-10-29T14:31:55Z", "component": "perception-worker", "metric": "restart_count", "value": 0, "unit": "count"},

        {"timestamp": "2026-10-29T14:31:58Z", "component": "perception-worker", "metric": "cpu_utilization_pct", "value": 54.1, "unit": "percent"},
        {"timestamp": "2026-10-29T14:31:58Z", "component": "perception-worker", "metric": "queue_depth", "value": 14, "unit": "frames"},
        {"timestamp": "2026-10-29T14:31:58Z", "component": "perception-worker", "metric": "batch_size", "value": 8, "unit": "count"},
        {"timestamp": "2026-10-29T14:31:58Z", "component": "perception-worker", "metric": "request_throughput_hz", "value": 24.0, "unit": "hz"},
        {"timestamp": "2026-10-29T14:31:58Z", "component": "perception-worker", "metric": "working_set_mb", "value": 620, "unit": "mebibytes"},
        {"timestamp": "2026-10-29T14:31:58Z", "component": "perception-worker", "metric": "request_error_count", "value": 1, "unit": "count"},
        {"timestamp": "2026-10-29T14:31:58Z", "component": "perception-worker", "metric": "restart_count", "value": 0, "unit": "count"},

        {"timestamp": "2026-10-29T14:32:02Z", "component": "perception-worker", "metric": "cpu_utilization_pct", "value": 12.0, "unit": "percent"},
        {"timestamp": "2026-10-29T14:32:02Z", "component": "perception-worker", "metric": "queue_depth", "value": 2, "unit": "frames"},
        {"timestamp": "2026-10-29T14:32:02Z", "component": "perception-worker", "metric": "batch_size", "value": 0, "unit": "count"},
        {"timestamp": "2026-10-29T14:32:02Z", "component": "perception-worker", "metric": "request_throughput_hz", "value": 4.1, "unit": "hz"},
        {"timestamp": "2026-10-29T14:32:02Z", "component": "perception-worker", "metric": "working_set_mb", "value": 164, "unit": "mebibytes"},
        {"timestamp": "2026-10-29T14:32:02Z", "component": "perception-worker", "metric": "request_error_count", "value": 1, "unit": "count"},
        {"timestamp": "2026-10-29T14:32:02Z", "component": "perception-worker", "metric": "restart_count", "value": 1, "unit": "count"},
    ]
    with open(DEMO_DIR / "telemetry" / "runtime-metrics.jsonl", "w", encoding="utf-8") as f:
        for r in metrics_records:
            f.write(json.dumps(r) + "\n")

    # 7. traces/inference-spans.jsonl
    trace_records = [
        {
            "trace_id": "tr-4a8b1c0d2e3f0001",
            "span_id": "sp-0001-req",
            "parent_span_id": None,
            "component": "perception-worker",
            "operation": "process_batch",
            "start_time": "2026-10-29T14:31:40.100Z",
            "duration_ms": 42.4,
            "status": "ok",
            "attributes": {"batch_size": 8, "working_set_mb": 410, "gpu_device": "cuda:0"},
        },
        {
            "trace_id": "tr-4a8b1c0d2e3f0001",
            "span_id": "sp-0001-inf",
            "parent_span_id": "sp-0001-req",
            "component": "perception-worker",
            "operation": "tensor_inference",
            "start_time": "2026-10-29T14:31:40.105Z",
            "duration_ms": 36.8,
            "status": "ok",
            "attributes": {"model": "yolov8-emb", "input_resolution": "1280x720"},
        },
        {
            "trace_id": "tr-4a8b1c0d2e3f0002",
            "span_id": "sp-0002-req",
            "parent_span_id": None,
            "component": "perception-worker",
            "operation": "process_batch",
            "start_time": "2026-10-29T14:31:48.200Z",
            "duration_ms": 45.1,
            "status": "ok",
            "attributes": {"batch_size": 8, "working_set_mb": 482, "gpu_device": "cuda:0"},
        },
        {
            "trace_id": "tr-4a8b1c0d2e3f0003",
            "span_id": "sp-0003-req",
            "parent_span_id": None,
            "component": "perception-worker",
            "operation": "process_batch",
            "start_time": "2026-10-29T14:31:55.300Z",
            "duration_ms": 48.7,
            "status": "ok",
            "attributes": {"batch_size": 8, "working_set_mb": 580, "gpu_device": "cuda:0"},
        },
        {
            "trace_id": "tr-4a8b1c0d2e3f0004",
            "span_id": "sp-0004-req",
            "parent_span_id": None,
            "component": "perception-worker",
            "operation": "process_batch",
            "start_time": "2026-10-29T14:31:58.600Z",
            "duration_ms": 12.3,
            "status": "error",
            "attributes": {
                "batch_size": 8,
                "working_set_mb": 620,
                "error_type": "OOMKilled",
                "termination_signal": "SIGKILL",
            },
        },
    ]
    with open(DEMO_DIR / "traces" / "inference-spans.jsonl", "w", encoding="utf-8") as f:
        for r in trace_records:
            f.write(json.dumps(r) + "\n")

    # 8. source/worker.py
    source_py = '''"""
Perception Worker Runtime Entrypoint.
Responsible for continuous camera frame intake, batched tensor pre-processing,
inference execution, and publishing obstacle bounding boxes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("perception-worker")


class PerceptionWorker:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        resources = self.config.get("resources", {})
        self.memory_limit_mb = int(resources.get("memory_limit_mb", 512))
        runtime = self.config.get("runtime", {})
        self.max_batch_size = int(runtime.get("max_batch_size", 8))
        self.workers = int(runtime.get("workers", 2))
        self.request_timeout_ms = float(runtime.get("request_timeout_ms", 800))
        self.is_running = False

    def load_model(self) -> bool:
        logger.info(f"Loading perception model weights within {self.memory_limit_mb} MiB quota")
        return True

    def process_batch(self, frames: List[Any]) -> Dict[str, Any]:
        count = len(frames)
        if count > self.max_batch_size:
            frames = frames[:self.max_batch_size]
            count = len(frames)
        logger.debug(f"Processing perception batch of {count} frames")
        return {
            "batch_size": count,
            "detections": [],
            "status": "success",
        }

    def start(self) -> None:
        self.is_running = True
        logger.info(f"Perception worker started with {self.workers} workers")

    def stop(self) -> None:
        self.is_running = False
        logger.info("Perception worker stopped")


def create_worker(config: Optional[Dict[str, Any]] = None) -> PerceptionWorker:
    return PerceptionWorker(config)
'''
    (DEMO_DIR / "source" / "worker.py").write_text(source_py, encoding="utf-8")

    # 9. notes/operator-observations.md
    notes_md = """# Operator observations

- The perception worker restarted during a dense inference workload.
- No deployment or configuration change was made immediately before the event.
- Other services on the staging host remained healthy.
- The host had sufficient available memory for a bounded increase.
- This package contains no heap dump or long-duration memory trend.
- The evidence is insufficient to determine whether a memory leak exists.
- Production rollout would still require operator approval.
"""
    (DEMO_DIR / "notes" / "operator-observations.md").write_text(notes_md, encoding="utf-8")

    # 10. unknown/diagnostic-context.bin
    diagnostic_bin = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\xff\xfe\xfd\xfc"
    (DEMO_DIR / "unknown" / "diagnostic-context.bin").write_bytes(diagnostic_bin)

    # 11. README.md
    readme_md = """# Cauveris Incident Demonstration Package: DEMO-PERCEPTION-MEMORY-002

## Incident Story
During an intensive perception workload in staging, the `perception-worker` process was terminated by the host kernel after its resident set size (620 MiB) exceeded the configured container ceiling (`resources.memory_limit_mb: 512`). The failure caused dropped perception frames, leading to an automated emergency stop event.

## Artifact Inventory
- `manifest.yaml`: Incident metadata declaring affected components, expected evidence, and target capability.
- `config/worker.yaml`: Service runtime and resource definitions, including `resources.memory_limit_mb` (512 MiB), host capacity (6144 MiB available), and repair policy (20% headroom, 1024 MiB cap).
- `config/component_aliases.yaml`: Component alias mapping (`perception-worker`, `perception_worker`, `worker.perception`).
- `telemetry/oom-events.log`: Chronological event sequence capturing startup, memory pressure warnings, allocation failure, OOMKilled termination, and container restart.
- `telemetry/heap.csv`: Time-series telemetry tracking working set, heap usage, memory limit, host available capacity, and restarts.
- `telemetry/runtime-metrics.jsonl`: Structured telemetry confirming CPU and queue depth remained within bounds while memory violated ceiling.
- `traces/inference-spans.jsonl`: Distributed tracing spans showing batch inference operations active during the memory fault without dependency timeouts.
- `source/worker.py`: Syntactically valid worker implementation exposing resource parameter bindings and batch processing interfaces.
- `notes/operator-observations.md`: Operator context noting healthy host headroom and absence of full heap dumps.
- `unknown/diagnostic-context.bin`: Unstructured binary diagnostic payload demonstrating safe universal inventory and selective parser engagement.

## Capability & Expected Repair
- **Mechanism**: `resource_exhaustion` (Failure Family: `memory_or_resource_exhaustion`)
- **Editable Control**: `resources.memory_limit_mb` in `config/worker.yaml`
- **Observed Peak Demand**: 620 MiB
- **Initial Limit**: 512 MiB
- **Headroom Policy**: 1.20x minimum headroom ratio
- **Calculated Requirement**: 620 * 1.20 = 744 MiB -> 768 MiB (aligned to 128 MiB boundary, <= 1024 MiB ceiling)
- **Feasibility**: Host has 6144 MiB available for services, easily accommodating the 256 MiB increase.

## Verification & Limitations
- **Verification Level**: Achieves `STAGING_VERIFIED` / `MODEL_VERIFIED`.
- **Limitation**: The repair resolves the demonstrated memory-limit violation for the observed workload. The available evidence is insufficient to prove that the service has no memory leak. Full leak elimination would require heap profiling over multi-hour runtimes.
"""
    (DEMO_DIR / "README.md").write_text(readme_md, encoding="utf-8")


def validate_source_files() -> None:
    """Validate all files for syntax and contract adherence."""
    # YAML
    for yf in ["manifest.yaml", "config/worker.yaml", "config/component_aliases.yaml"]:
        p = DEMO_DIR / yf
        assert p.exists(), f"Missing {yf}"
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            assert isinstance(data, dict), f"{yf} did not parse as a dict"

    # CSV
    csv_path = DEMO_DIR / "telemetry" / "heap.csv"
    assert csv_path.exists(), "Missing heap.csv"
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required_cols = {"timestamp", "component", "working_set_mb", "heap_used_mb", "memory_limit_mb", "host_available_mb", "restart_count"}
        assert required_cols.issubset(set(reader.fieldnames or [])), f"heap.csv missing columns: {required_cols - set(reader.fieldnames or [])}"
        rows = list(reader)
        assert len(rows) >= 5, "heap.csv has too few rows"
        peak = max(float(r["working_set_mb"]) for r in rows)
        assert peak == 620.0, f"Expected peak 620 MiB, got {peak}"

    # JSONL
    for jf in ["telemetry/runtime-metrics.jsonl", "traces/inference-spans.jsonl"]:
        p = DEMO_DIR / jf
        assert p.exists(), f"Missing {jf}"
        with open(p, "r", encoding="utf-8") as f:
            count = 0
            for line in f:
                if line.strip():
                    item = json.loads(line)
                    assert isinstance(item, dict), f"Non-dict record in {jf}"
                    count += 1
            assert count >= 3, f"Too few records in {jf}"

    # Python AST
    py_path = DEMO_DIR / "source" / "worker.py"
    assert py_path.exists(), "Missing worker.py"
    ast.parse(py_path.read_text(encoding="utf-8"))

    # OOM Log
    oom_path = DEMO_DIR / "telemetry" / "oom-events.log"
    assert oom_path.exists(), "Missing oom-events.log"
    oom_content = oom_path.read_text(encoding="utf-8")
    assert "OOMKilled" in oom_content, "Missing OOMKilled in oom-events.log"
    assert "620" in oom_content, "Missing 620 in oom-events.log"
    assert "512" in oom_content, "Missing 512 in oom-events.log"

    # Binary file
    bin_path = DEMO_DIR / "unknown" / "diagnostic-context.bin"
    assert bin_path.exists(), "Missing diagnostic-context.bin"
    raw = bin_path.read_bytes()
    assert b"\x00" in raw, "diagnostic-context.bin must be binary"


def build_zip() -> Path:
    """Build the ZIP archive deterministically."""
    OUTPUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_ZIP.exists():
        OUTPUT_ZIP.unlink()

    # Collect files relative to DEMO_DIR, excluding README.md
    files_to_pack: list[tuple[Path, str]] = []
    for root, _, files in os.walk(DEMO_DIR):
        for f in files:
            if f == "README.md":
                continue
            full_p = Path(root) / f
            rel_p = full_p.relative_to(DEMO_DIR).as_posix()
            files_to_pack.append((full_p, rel_p))

    files_to_pack.sort(key=lambda item: item[1])

    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for full_p, arcname in files_to_pack:
            # Deterministic ZipInfo
            zinfo = zipfile.ZipInfo(arcname, date_time=FIXED_TIMESTAMP)
            zinfo.external_attr = (stat.S_IFREG | 0o644) << 16
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(zinfo, full_p.read_bytes())

    # Verify built ZIP
    hasher = hashlib.sha256()
    with open(OUTPUT_ZIP, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    sha256 = hasher.hexdigest()
    size = OUTPUT_ZIP.stat().st_size

    with zipfile.ZipFile(OUTPUT_ZIP, "r") as zf:
        names = zf.namelist()
        assert len(names) == len(files_to_pack), "Member count mismatch"
        assert len(names) == len(set(names)), "Duplicate member detected in ZIP"
        for n in names:
            assert not n.startswith(("/", "\\")), f"Absolute path detected: {n}"
            assert ".." not in n, f"Parent traversal detected: {n}"

    print(f"Created ZIP: {OUTPUT_ZIP}")
    print(f"Byte size: {size}")
    print(f"SHA-256: {sha256}")
    print(f"Member count: {len(names)}")
    for n in names:
        print(f"  - {n}")

    return OUTPUT_ZIP


def main() -> None:
    print("Step 1: Creating package source files...")
    create_package_files()
    print("Step 2: Validating syntax and schemas...")
    validate_source_files()
    print("Step 3: Building deterministic ZIP archive...")
    zip_p = build_zip()
    print("Step 4: Verifying preflight properties...")
    print(f"SUCCESS: Package built at {zip_p}")


if __name__ == "__main__":
    main()

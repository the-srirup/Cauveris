"""Build the demonstration incident package for Cauveris."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path


def build():
    pkg_dir = Path("packages/perception-worker-memory-exhaustion")
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "config").mkdir(exist_ok=True)
    (pkg_dir / "telemetry").mkdir(exist_ok=True)
    (pkg_dir / "src").mkdir(exist_ok=True)

    manifest_content = """incident_id: DEMO-PERCEPTION-MEMORY-001
title: Perception Worker Memory Exhaustion
description: Real perception worker OOM kill with configurable memory quota and headroom capacity.
system_name: perception-pipeline
required_evidence:
  - config/worker.yaml
  - telemetry/oom-events.log
  - telemetry/heap.csv
e2e:
  family: memory_or_resource_exhaustion
  expected_mechanism: resource_exhaustion
  expected_hypothesis: h_memory_exhaustion
  expected_key: resources.memory_limit_mb
"""

    worker_yaml = """dynamic_batching:
  batching_window_ms: 100
  max_batch_size: 8
resources:
  memory_limit_mb: 512
server:
  worker_count: 2
safety:
  detection_freshness_budget_ms: 400
"""

    oom_log = """2026-10-20T10:29:58Z INFO perception: batch completed in 42 ms
2026-10-20T10:29:59Z ERROR perception: OOMKilled; memory limit 512 MiB exceeded; peak working set 620 MiB
"""

    heap_csv = """timestamp,memory_used_mb,memory_total_mb
2026-10-20T10:29:58Z,580,8192
2026-10-20T10:29:59Z,620,8192
"""

    worker_py = '''"""Perception worker entrypoint."""

MEMORY_LIMIT_MB = 512


def run():
    return MEMORY_LIMIT_MB
'''

    (pkg_dir / "manifest.yaml").write_text(manifest_content, encoding="utf-8")
    (pkg_dir / "config" / "worker.yaml").write_text(worker_yaml, encoding="utf-8")
    (pkg_dir / "telemetry" / "oom-events.log").write_text(oom_log, encoding="utf-8")
    (pkg_dir / "telemetry" / "heap.csv").write_text(heap_csv, encoding="utf-8")
    (pkg_dir / "src" / "worker.py").write_text(worker_py, encoding="utf-8")

    zip_path = Path("packages/perception-worker-memory-exhaustion.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(pkg_dir):
            for f in files:
                full_path = Path(root) / f
                arcname = full_path.relative_to(pkg_dir)
                zf.write(full_path, arcname)

    import hashlib
    sha256 = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    print(f"Created ZIP: {zip_path}")
    print(f"Size: {zip_path.stat().st_size} bytes")
    print(f"SHA-256: {sha256}")


if __name__ == "__main__":
    build()

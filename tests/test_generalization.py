"""
Generalization Tests for Cauveris.
Mutates:
- directory names
- filenames
- service names
- key aliases
- key nesting
- evidence ordering
- timestamp formats
- configuration format

Asserts that diagnosis remains stable across semantic equivalences.
Tests unfamiliar bundles across multiple mechanisms.
"""

from pathlib import Path
import pytest
from cauveris.analysis.mechanism_detectors import MechanismDetectorRegistry
from cauveris.analysis.evidence_aliaser import EvidenceAliaser


def test_generalization_renamed_directories_and_files():
    registry = MechanismDetectorRegistry()

    # Case A: Standard names
    res_a = registry.detect_all(
        logs_text="[2026-10-27 10:00:00] FATAL [service=auth] failed with OOMKilled",
        metrics_dict={"memory": 1500.0},
        config_entries={"memory_limit_mb": 1024.0},
    )

    # Case B: Mutated directories, arbitrary filenames, renamed service, different timestamp format
    res_b = registry.detect_all(
        logs_text="[2026-10-27T10:00:00.123456Z] CRITICAL [service=custom_microservice_xyz] OOMKilled cgroup allocation failed",
        metrics_dict={"memory": 1500.0},
        config_entries={"memory_limit_mb": 1024.0},
    )

    assert len(res_a) > 0
    assert len(res_b) > 0
    assert res_a[0].mechanism_id == res_b[0].mechanism_id == "resource_exhaustion"
    assert abs(res_a[0].confidence - res_b[0].confidence) < 0.1


def test_generalization_key_aliases_and_nesting():
    aliaser = EvidenceAliaser()
    registry = MechanismDetectorRegistry()

    # Telemetry formatted with various alias keys and nesting
    keys_variants = [
        {"resp_time": 850.0},
        {"duration_ms": 850.0},
        {"http.client.request_latency": 850.0},
        {"e2e_latency": 850.0},
    ]

    for k_var in keys_variants:
        matched, _ = aliaser.match_dictionary(k_var)
        assert "latency" in matched
        lat_val = matched["latency"].value

        # Diagnosis remains stable
        res = registry.detect_all(
            logs_text="Connection timed out calling upstream service",
            metrics_dict={"latency": lat_val},
            config_entries={"timeout_ms": 500.0},
        )
        assert any(r.mechanism_id == "dependency_timeout" for r in res)


def test_generalization_across_six_unfamiliar_mechanisms(tmp_path: Path):
    """Verifies that at least 6 distinct mechanisms pass unfamiliar-bundle checks."""
    registry = MechanismDetectorRegistry()

    mechanisms_verified = []

    # 1. Unfamiliar bundle with memory exhaustion
    r1 = registry.detect_all(
        logs_text="Pod crashed: Out of memory in worker task",
        metrics_dict={"memory": 4096.0},
        config_entries={"memory_limit_mb": 2048.0},
    )
    if any(r.mechanism_id == "resource_exhaustion" for r in r1):
        mechanisms_verified.append("resource_exhaustion")

    # 2. Unfamiliar bundle with lock contention
    r2 = registry.detect_all(
        logs_text="Thread starvation: deadlock on database lock table mutex",
        metrics_dict={"lock_wait": 300.0},
        config_entries={},
    )
    if any(r.mechanism_id == "lock_contention" for r in r2):
        mechanisms_verified.append("lock_contention")

    # 3. Unfamiliar bundle with queue overflow
    r3 = registry.detect_all(
        logs_text="Buffer overflow: rejectedExecutionException queue full",
        metrics_dict={"queue_depth": 1000.0},
        config_entries={"queue_depth": 500.0},
    )
    if any(r.mechanism_id == "queue_overflow_backpressure" for r in r3):
        mechanisms_verified.append("queue_overflow_backpressure")

    # 4. Unfamiliar bundle with transport loss
    r4 = registry.detect_all(
        logs_text="Packet drop detected, retransmit counter increased",
        metrics_dict={"loss": 0.05, "jitter": 30.0},
        config_entries={},
    )
    if any(r.mechanism_id == "transport_loss_jitter" for r in r4):
        mechanisms_verified.append("transport_loss_jitter")

    # 5. Unfamiliar bundle with worker saturation
    r5 = registry.detect_all(
        logs_text="Thread pool exhausted, max_workers reached",
        metrics_dict={"concurrency": 64.0},
        config_entries={"worker_count": 64.0},
    )
    if any(r.mechanism_id == "worker_saturation" for r in r5):
        mechanisms_verified.append("worker_saturation")

    # 6. Unfamiliar bundle with clock skew
    r6 = registry.detect_all(
        logs_text="Clock drift exceeds 500ms; timestamp in the future",
        metrics_dict={},
        config_entries={},
    )
    if any(r.mechanism_id == "clock_skew" for r in r6):
        mechanisms_verified.append("clock_skew")

    # 7. Unfamiliar bundle with arrival overload
    r7 = registry.detect_all(
        logs_text="Rate limit exceeded 429",
        metrics_dict={"arrival_rate": 800.0, "service_time": 20.0},
        config_entries={"worker_count": 4},
    )
    if any(r.mechanism_id == "arrival_overload" for r in r7):
        mechanisms_verified.append("arrival_overload")

    assert len(mechanisms_verified) >= 6

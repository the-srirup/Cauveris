"""
Tests for Evidence Aliasing and Mechanism Detector Plugins.
Verifies:
- Configurable aliases and matching rules (original, canonical, rule, confidence, source)
- 8 canonical mechanism detectors
- Never silently converting unknown fields
- Adversarial tests where similar words do not trigger wrong mechanisms
"""

from cauveris.analysis.evidence_aliaser import EvidenceAliaser
from cauveris.analysis.mechanism_detectors import (
    MechanismDetectorRegistry,
)


def test_evidence_aliaser_preserves_metadata_and_rules():
    aliaser = EvidenceAliaser()

    # Exact alias
    m1 = aliaser.match("resp_time", source="otel_span", value=42.5)
    assert m1 is not None
    assert m1.original_field == "resp_time"
    assert m1.canonical_name == "latency"
    assert m1.matching_rule == "alias_lookup"
    assert m1.confidence >= 0.90
    assert m1.source == "otel_span"
    assert m1.value == 42.5

    # Regex alias
    m2 = aliaser.match("gateway_response_time_ms", source="prometheus", value=150)
    assert m2 is not None
    assert m2.canonical_name == "latency"
    assert m2.matching_rule in ("regex_pattern", "fuzzy_token")

    # Memory alias
    m3 = aliaser.match("cgroup_memory_mb", source="cadvisor", value=2048)
    assert m3 is not None
    assert m3.canonical_name == "memory"

    # Lock wait alias
    m4 = aliaser.match("contention_ms", source="thread_profile", value=85)
    assert m4 is not None
    assert m4.canonical_name == "lock_wait"

    # Unknown field must return None and NOT be silently converted
    m_unknown = aliaser.match("random_unrelated_telemetry_metric", source="test")
    assert m_unknown is None


def test_aliaser_dictionary_separation():
    aliaser = EvidenceAliaser()
    raw = {
        "ingress_rate_hz": 120.0,
        "rss_mb": 512.0,
        "unrelated_color": "blue",
    }
    matched, unknown = aliaser.match_dictionary(raw)
    assert "arrival_rate" in matched
    assert "memory" in matched
    assert "unrelated_color" in unknown
    assert unknown["unrelated_color"] == "blue"


def test_all_eight_mechanism_detectors():
    registry = MechanismDetectorRegistry()
    assert len(registry.detectors) >= 8

    # 1. Resource Exhaustion
    res_oom = registry.detect_all(
        logs_text="Fatal: OOMKilled cgroup container memory limit breached",
        metrics_dict={"memory": 2000.0},
        config_entries={"memory_limit_mb": 2048.0},
    )
    assert any(r.mechanism_id == "resource_exhaustion" for r in res_oom)

    # 2. Dependency Timeout
    res_to = registry.detect_all(
        logs_text="Error: context deadline exceeded while calling payment service",
        metrics_dict={"latency": 600.0},
        config_entries={"timeout_ms": 500.0},
    )
    assert any(r.mechanism_id == "dependency_timeout" for r in res_to)

    # 3. Lock Contention
    res_lock = registry.detect_all(
        logs_text="Detected deadlock waiting on mutex db_pool",
        metrics_dict={"lock_wait": 250.0},
        config_entries={},
    )
    assert any(r.mechanism_id == "lock_contention" for r in res_lock)

    # 4. Queue Overflow / Backpressure
    res_q = registry.detect_all(
        logs_text="Queue full: rejectedExecutionException incoming request dropped",
        metrics_dict={"queue_depth": 500.0},
        config_entries={"queue_depth": 500.0},
    )
    assert any(r.mechanism_id == "queue_overflow_backpressure" for r in res_q)

    # 5. Transport Loss or Jitter
    res_net = registry.detect_all(
        logs_text="WARN: high packet loss and retransmit on eth0",
        metrics_dict={"loss": 0.08, "jitter": 45.0},
        config_entries={},
    )
    assert any(r.mechanism_id == "transport_loss_jitter" for r in res_net)

    # 6. Worker Saturation
    res_worker = registry.detect_all(
        logs_text="Error: connection pool exhausted, all threads busy",
        metrics_dict={"concurrency": 32.0},
        config_entries={"worker_count": 32.0},
    )
    assert any(r.mechanism_id == "worker_saturation" for r in res_worker)

    # 7. Clock Skew
    res_clock = registry.detect_all(
        logs_text="Timestamp in the future detected, clock unsynchronized with ntp",
        metrics_dict={},
        config_entries={},
    )
    assert any(r.mechanism_id == "clock_skew" for r in res_clock)

    # 8. Arrival Overload
    res_arrival = registry.detect_all(
        logs_text="WARN: 429 rate limit exceeded",
        metrics_dict={"arrival_rate": 500.0, "service_time": 10.0},
        config_entries={"worker_count": 2},  # capacity = 200 Hz
    )
    assert any(r.mechanism_id == "arrival_overload" for r in res_arrival)


def test_adversarial_similar_words_do_not_falsely_trigger():
    """
    Adversarial test: words like 'timeout' in comments or memory in unrelated context
    must not trigger conflicting mechanisms without supporting patterns.
    """
    registry = MechanismDetectorRegistry()

    # Log discussing a 'timeout parameter documentation' or benign message
    benign_text = "Configuration notes: user can configure timeout if needed. All jobs finished normally."
    res = registry.detect_all(
        logs_text=benign_text,
        metrics_dict={"latency": 20.0},
        config_entries={"timeout_ms": 5000.0},
    )
    # Latency 20ms does NOT breach 5000ms, and benign log should either have low confidence or not trigger
    to_mech = next((r for r in res if r.mechanism_id == "dependency_timeout"), None)
    if to_mech:
        assert to_mech.confidence < 0.50
        assert len(to_mech.contradicting_evidence) > 0

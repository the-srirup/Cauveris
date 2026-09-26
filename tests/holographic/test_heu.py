"""
Unit tests for Holographic Evidence Units (HEUs) - Phase 1.

Tests cover:
- HolographicEvidenceUnit creation and validation
- BoundaryLayer enum
- Phase vector computation
- Encoded dimensions computation
- Timeline to HEU conversion
- Cross-layer correlations
"""
import pytest
import numpy as np
from datetime import datetime

from cauveris.holographic.heu import (
    HolographicEvidenceUnit,
    BoundaryLayer,
    _map_source_type_to_layer,
    _compute_encoded_dimensions,
    _compute_phase_vector,
    _synthesize_heu_id,
    convert_timeline_to_heus,
    _compute_causal_depths,
    _compute_dependency_counts,
    _compute_reconstruction_weight,
    _compute_ambiguity_score,
    _add_cross_layer_correlations,
)


class TestBoundaryLayer:
    """Test BoundaryLayer enum."""

    def test_all_layers_exist(self):
        expected = {
            "APPLICATION_LOG",
            "INFRASTRUCTURE_LOG",
            "DISTRIBUTED_TRACE",
            "METRICS_EXPORT",
            "NETWORK_FLOW",
            "CONFIG_STATE",
            "DEPLOYMENT_EVENT",
        }
        actual = {layer.name for layer in BoundaryLayer}
        assert actual == expected

    def test_layer_values(self):
        assert BoundaryLayer.APPLICATION_LOG.value == "application_log"
        assert BoundaryLayer.DISTRIBUTED_TRACE.value == "distributed_trace"
        assert BoundaryLayer.METRICS_EXPORT.value == "metrics_export"


class TestHolographicEvidenceUnit:
    """Test HolographicEvidenceUnit dataclass."""

    def test_valid_creation(self):
        heu = HolographicEvidenceUnit(
            heu_id="test_heu_1",
            timestamp_ns=1_000_000_000,
            boundary_layer=BoundaryLayer.APPLICATION_LOG,
            source_component="test_service",
            source_instance="test_instance_1",
            payload={"message": "test log"},
        )
        assert heu.heu_id == "test_heu_1"
        assert heu.timestamp_ns == 1_000_000_000
        assert heu.boundary_layer == BoundaryLayer.APPLICATION_LOG
        assert heu.reconstruction_weight == 1.0
        assert heu.ambiguity_score == 0.0
        assert heu.phase_vector.shape == (8,)

    def test_invalid_phase_vector_shape(self):
        with pytest.raises(ValueError, match="phase_vector must have shape"):
            HolographicEvidenceUnit(
                heu_id="test",
                timestamp_ns=0,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="test",
                source_instance="test",
                payload={},
                phase_vector=np.zeros(7),  # Wrong shape
            )

    def test_invalid_reconstruction_weight(self):
        with pytest.raises(ValueError, match="reconstruction_weight must be in"):
            HolographicEvidenceUnit(
                heu_id="test",
                timestamp_ns=0,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="test",
                source_instance="test",
                payload={},
                reconstruction_weight=1.5,  # Invalid
            )

    def test_invalid_ambiguity_score(self):
        with pytest.raises(ValueError, match="ambiguity_score must be in"):
            HolographicEvidenceUnit(
                heu_id="test",
                timestamp_ns=0,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="test",
                source_instance="test",
                payload={},
                ambiguity_score=-0.1,  # Invalid
            )

    def test_encoded_dimensions_clamping(self, caplog):
        heu = HolographicEvidenceUnit(
            heu_id="test",
            timestamp_ns=0,
            boundary_layer=BoundaryLayer.APPLICATION_LOG,
            source_component="test",
            source_instance="test",
            payload={},
            encoded_dimensions={"cpu_pressure": 1.5, "memory_pressure": -0.2},
        )
        # Should clamp to [0,1]
        assert heu.encoded_dimensions["cpu_pressure"] == 1.0
        assert heu.encoded_dimensions["memory_pressure"] == 0.0

    def test_timestamp_s_property(self):
        heu = HolographicEvidenceUnit(
            heu_id="test",
            timestamp_ns=1_500_000_000,
            boundary_layer=BoundaryLayer.APPLICATION_LOG,
            source_component="test",
            source_instance="test",
            payload={},
        )
        assert heu.timestamp_s == 1.5

    def test_is_synthesized_property(self):
        heu_obs = HolographicEvidenceUnit(
            heu_id="heu_app_log_test_000001",
            timestamp_ns=0,
            boundary_layer=BoundaryLayer.APPLICATION_LOG,
            source_component="test",
            source_instance="test",
            payload={},
        )
        heu_synth = HolographicEvidenceUnit(
            heu_id="synth_metrics_export_test_000001",
            timestamp_ns=0,
            boundary_layer=BoundaryLayer.METRICS_EXPORT,
            source_component="test",
            source_instance="test",
            payload={},
        )
        assert not heu_obs.is_synthesized
        assert heu_synth.is_synthesized

    def test_to_dict_and_from_dict(self):
        original = HolographicEvidenceUnit(
            heu_id="test_heu",
            timestamp_ns=1_000_000_000,
            boundary_layer=BoundaryLayer.DISTRIBUTED_TRACE,
            source_component="nav_service",
            source_instance="nav-1",
            payload={"span_id": "abc123"},
            encoded_dimensions={"cpu_pressure": 0.7},
            reconstruction_weight=0.9,
            ambiguity_score=0.1,
            cross_layer_correlations=["other_heu_1"],
            phase_vector=np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], dtype=np.float32),
        )

        data = original.to_dict()
        reconstructed = HolographicEvidenceUnit.from_dict(data)

        assert reconstructed.heu_id == original.heu_id
        assert reconstructed.timestamp_ns == original.timestamp_ns
        assert reconstructed.boundary_layer == original.boundary_layer
        assert reconstructed.source_component == original.source_component
        assert reconstructed.payload == original.payload
        assert reconstructed.encoded_dimensions == original.encoded_dimensions
        assert reconstructed.reconstruction_weight == original.reconstruction_weight
        assert reconstructed.ambiguity_score == original.ambiguity_score
        assert reconstructed.cross_layer_correlations == original.cross_layer_correlations
        np.testing.assert_array_equal(reconstructed.phase_vector, original.phase_vector)

    def test_hash_and_eq(self):
        heu1 = HolographicEvidenceUnit(
            heu_id="same_id", timestamp_ns=0, boundary_layer=BoundaryLayer.APPLICATION_LOG,
            source_component="a", source_instance="1", payload={}
        )
        heu2 = HolographicEvidenceUnit(
            heu_id="same_id", timestamp_ns=100, boundary_layer=BoundaryLayer.METRICS_EXPORT,
            source_component="b", source_instance="2", payload={}
        )
        heu3 = HolographicEvidenceUnit(
            heu_id="different_id", timestamp_ns=0, boundary_layer=BoundaryLayer.APPLICATION_LOG,
            source_component="a", source_instance="1", payload={}
        )

        assert heu1 == heu2
        assert heu1 != heu3
        assert hash(heu1) == hash(heu2)
        assert hash(heu1) != hash(heu3)


class TestMapSourceTypeToLayer:
    """Test _map_source_type_to_layer function."""

    def test_known_mappings(self):
        assert _map_source_type_to_layer("jsonl_log") == BoundaryLayer.APPLICATION_LOG
        assert _map_source_type_to_layer("text_log") == BoundaryLayer.INFRASTRUCTURE_LOG
        assert _map_source_type_to_layer("otel_trace") == BoundaryLayer.DISTRIBUTED_TRACE
        assert _map_source_type_to_layer("mcap_recording") == BoundaryLayer.DISTRIBUTED_TRACE
        assert _map_source_type_to_layer("csv_metrics") == BoundaryLayer.METRICS_EXPORT
        assert _map_source_type_to_layer("deployment_json") == BoundaryLayer.DEPLOYMENT_EVENT
        assert _map_source_type_to_layer("operator_note") == BoundaryLayer.CONFIG_STATE

    def test_unknown_defaults_to_application_log(self):
        assert _map_source_type_to_layer("unknown_type") == BoundaryLayer.APPLICATION_LOG
        assert _map_source_type_to_layer("") == BoundaryLayer.APPLICATION_LOG


class TestComputeEncodedDimensions:
    """Test _compute_encoded_dimensions function."""

    def test_cpu_pressure_detection(self):
        event = {
            "source_type": "csv_metrics",
            "message": "CPU utilization high",
            "attributes": {"cpu_usage": 0.9},
        }
        dims = _compute_encoded_dimensions(event, {})
        assert "cpu_pressure" in dims
        assert dims["cpu_pressure"] > 0.5

    def test_memory_pressure_detection(self):
        event = {
            "source_type": "jsonl_log",
            "message": "OOM killer invoked, out of memory",
            "attributes": {},
        }
        dims = _compute_encoded_dimensions(event, {})
        assert "memory_pressure" in dims
        assert dims["memory_pressure"] > 0.5

    def test_network_latency_detection(self):
        event = {
            "source_type": "otel_trace",
            "message": "Request timeout",
            "attributes": {"duration_ns": 500_000_000},
        }
        dims = _compute_encoded_dimensions(event, {})
        assert "network_latency" in dims

    def test_error_rate_detection(self):
        event = {
            "source_type": "jsonl_log",
            "message": "Failed to connect to database",
            "attributes": {"level": "ERROR"},
            "status": "error",
        }
        dims = _compute_encoded_dimensions(event, {})
        assert "error_rate" in dims
        assert dims["error_rate"] > 0.5

    def test_config_change_detection(self):
        event = {
            "source_type": "deployment_json",
            "message": "Deployment v42 rolled out",
            "attributes": {},
        }
        dims = _compute_encoded_dimensions(event, {})
        assert "config_change" in dims
        assert dims["config_change"] >= 0.9

    def test_deployment_activity_detection(self):
        event = {
            "source_type": "operator_note",
            "message": "Scaling up replicas to 10",
            "attributes": {},
        }
        dims = _compute_encoded_dimensions(event, {})
        assert "deployment_activity" in dims

    def test_service_dependency_detection(self):
        event = {
            "source_type": "otel_trace",
            "message": "Service call to payment_service",
            "attributes": {"peer.service": "payment_service"},
        }
        dims = _compute_encoded_dimensions(event, {})
        assert "service_dependency" in dims

    def test_empty_event_returns_empty(self):
        event = {
            "source_type": "jsonl_log",
            "message": "Heartbeat",
            "attributes": {},
        }
        dims = _compute_encoded_dimensions(event, {})
        assert dims == {}


class TestComputePhaseVector:
    """Test _compute_phase_vector function."""

    def test_phase_vector_shape_and_type(self):
        event = {"timestamp_ns": 500_000_000, "source_type": "jsonl_log", "attributes": {}}
        phase = _compute_phase_vector(event, incident_duration_ns=1_000_000_000)

        assert isinstance(phase, np.ndarray)
        assert phase.shape == (8,)
        assert phase.dtype == np.float32

    def test_time_dimension_normalized(self):
        event = {"timestamp_ns": 500_000_000, "attributes": {}}
        phase = _compute_phase_vector(event, incident_duration_ns=1_000_000_000)
        assert phase[0] == 0.5  # Halfway through incident

    def test_time_dimension_clamped(self):
        event = {"timestamp_ns": 2_000_000_000, "attributes": {}}
        phase = _compute_phase_vector(event, incident_duration_ns=1_000_000_000)
        assert phase[0] == 1.0  # Clamped at 1.0

    def test_causality_dimension(self):
        event = {"timestamp_ns": 0, "attributes": {}}
        phase = _compute_phase_vector(event, incident_duration_ns=1_000_000_000,
                                     causal_depth=2, max_causal_depth=4)
        assert phase[1] == 0.5  # 2/4

    def test_resource_dimensions_from_encoded(self):
        event = {
            "timestamp_ns": 0,
            "source_type": "csv_metrics",
            "message": "High CPU and memory usage",
            "attributes": {},
        }
        phase = _compute_phase_vector(event, incident_duration_ns=1_000_000_000)
        # CPU + memory + resource_contention should contribute
        assert phase[2] > 0.5


class TestSynthesizeHeuId:
    """Test _synthesize_heu_id function."""

    def test_format(self):
        heu_id = _synthesize_heu_id(
            BoundaryLayer.APPLICATION_LOG,
            "nav_controller",
            "nav-1",
            1_000_000_000,
            42,
        )
        assert heu_id.startswith("heu_application_log_nav_controller_nav-1_1000000000_000042.")
        assert len(heu_id.split(".")[-1]) == 8  # 8-char hash


class TestConvertTimelineToHeus:
    """Test convert_timeline_to_heus function."""

    def test_basic_conversion(self):
        timeline = [
            {
                "event_id": "evt_1",
                "timestamp_ns": 100_000_000,
                "source_type": "jsonl_log",
                "source": "nav_controller.log",
                "message": "High CPU usage detected",
                "attributes": {"service": "navigation_controller", "instance": "nav-1", "level": "WARN"},
                "status": "warning",
            },
            {
                "event_id": "evt_2",
                "timestamp_ns": 200_000_000,
                "source_type": "otel_trace",
                "source": "traces",
                "message": "Span for /nav/plan",
                "attributes": {"service": "navigation_controller", "trace_id": "abc"},
                "status": "ok",
            },
        ]
        raw_signals = {}
        incident_duration = 1_000_000_000

        heus = convert_timeline_to_heus(timeline, raw_signals, incident_duration)

        assert len(heus) == 2
        assert heus[0].boundary_layer == BoundaryLayer.APPLICATION_LOG
        assert heus[1].boundary_layer == BoundaryLayer.DISTRIBUTED_TRACE
        assert heus[0].source_component == "navigation_controller"
        assert heus[1].source_component == "navigation_controller"

    def test_heus_have_phase_vectors(self):
        timeline = [{
            "event_id": "evt_1",
            "timestamp_ns": 100_000_000,
            "source_type": "jsonl_log",
            "source": "test.log",
            "message": "Test",
            "attributes": {"service": "test_svc"},
        }]
        heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)
        assert heus[0].phase_vector.shape == (8,)
        assert not np.allclose(heus[0].phase_vector, 0)

    def test_heus_have_encoded_dimensions(self):
        timeline = [{
            "event_id": "evt_1",
            "timestamp_ns": 100_000_000,
            "source_type": "jsonl_log",
            "source": "test.log",
            "message": "CPU throttling",
            "attributes": {"service": "test_svc"},
        }]
        heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)
        assert "cpu_pressure" in heus[0].encoded_dimensions

    def test_heus_have_reconstruction_weight(self):
        timeline = [{
            "event_id": "evt_1",
            "timestamp_ns": 100_000_000,
            "source_type": "otel_trace",
            "source": "traces",
            "message": "Span",
            "attributes": {"service": "test_svc"},
        }]
        heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)
        # OTel traces should have high weight
        assert heus[0].reconstruction_weight >= 0.9

    def test_empty_timeline_returns_empty(self):
        heus = convert_timeline_to_heus([], {}, 1_000_000_000)
        assert heus == []

    def test_cross_layer_correlations_added(self):
        timeline = [
            {
                "event_id": "evt_1",
                "timestamp_ns": 100_000_000,
                "source_type": "jsonl_log",
                "source": "test.log",
                "message": "Log at 100ms",
                "attributes": {"service": "svc_a"},
            },
            {
                "event_id": "evt_2",
                "timestamp_ns": 100_500_000,  # Same ms bucket
                "source_type": "csv_metrics",
                "source": "metrics",
                "message": "Metric at 100ms",
                "attributes": {"service": "svc_a"},
            },
        ]
        heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)
        assert len(heus) == 2
        # Both should have each other as correlation
        assert heus[0].heu_id in heus[1].cross_layer_correlations
        assert heus[1].heu_id in heus[0].cross_layer_correlations


class TestComputeCausalDepths:
    """Test _compute_causal_depths function."""

    def test_deployment_is_root_cause(self):
        timeline = [
            {"event_id": "deploy_1", "source_type": "deployment_json", "status": "ok"},
            {"event_id": "error_1", "source_type": "jsonl_log", "status": "error"},
        ]
        depths = _compute_causal_depths(timeline)
        assert depths["deploy_1"] == 0
        assert depths["error_1"] == 2

    def test_otel_trace_root_span(self):
        timeline = [
            {"event_id": "span_1", "source_type": "otel_trace", "attributes": {}},
        ]
        depths = _compute_causal_depths(timeline)
        assert depths["span_1"] == 0


class TestComputeDependencyCounts:
    """Test _compute_dependency_counts function."""

    def test_counts_from_otel_traces(self):
        timeline = [
            {"source_type": "otel_trace", "attributes": {"service.name": "svc_a", "peer.service": "svc_b"}},
            {"source_type": "otel_trace", "attributes": {"service.name": "svc_a", "peer.service": "svc_c"}},
            {"source_type": "otel_trace", "attributes": {"service.name": "svc_b", "peer.service": "svc_c"}},
        ]
        counts = _compute_dependency_counts(timeline)
        assert counts["svc_a"] == 2
        assert counts["svc_b"] == 1


class TestComputeReconstructionWeight:
    """Test _compute_reconstruction_weight function."""

    def test_otel_trace_high_weight(self):
        weight = _compute_reconstruction_weight(
            BoundaryLayer.DISTRIBUTED_TRACE,
            {"cpu_pressure": 0.5}
        )
        assert weight >= 0.9

    def test_infrastructure_log_lower_weight(self):
        weight = _compute_reconstruction_weight(
            BoundaryLayer.INFRASTRUCTURE_LOG,
            {}
        )
        assert weight < 0.7


class TestComputeAmbiguityScore:
    """Test _compute_ambiguity_score function."""

    def test_second_precision_increases_ambiguity(self):
        event = {
            "original_timestamp": "2026-09-26T10:00:00Z",  # No fractional seconds
            "confidence": 0.5,
        }
        score = _compute_ambiguity_score(event, BoundaryLayer.APPLICATION_LOG, {})
        # Layer base (0.1) + second precision (0.2) + no dims (0.3) + confidence (0.5*0.2=0.1)
        assert 0.6 <= score <= 0.9

    def test_high_confidence_reduces_ambiguity(self):
        event = {"original_timestamp": "2026-09-26T10:00:00.123456Z", "confidence": 0.9}
        score = _compute_ambiguity_score(event, BoundaryLayer.DISTRIBUTED_TRACE, {"cpu": 0.5})
        assert score < 0.3


class TestAddCrossLayerCorrelations:
    """Test _add_cross_layer_correlations function."""

    def test_correlations_added_same_component_same_ms(self):
        heus = [
            HolographicEvidenceUnit(
                heu_id="heu_1", timestamp_ns=100_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="svc_a", source_instance="i1",
                payload={}, phase_vector=np.zeros(8)
            ),
            HolographicEvidenceUnit(
                heu_id="heu_2", timestamp_ns=100_500_000,
                boundary_layer=BoundaryLayer.METRICS_EXPORT,
                source_component="svc_a", source_instance="i1",
                payload={}, phase_vector=np.zeros(8)
            ),
        ]
        _add_cross_layer_correlations(heus)
        assert "heu_2" in heus[0].cross_layer_correlations
        assert "heu_1" in heus[1].cross_layer_correlations

    def test_no_correlation_different_component(self):
        heus = [
            HolographicEvidenceUnit(
                heu_id="heu_1", timestamp_ns=100_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="svc_a", source_instance="i1",
                payload={}, phase_vector=np.zeros(8)
            ),
            HolographicEvidenceUnit(
                heu_id="heu_2", timestamp_ns=100_000_000,
                boundary_layer=BoundaryLayer.METRICS_EXPORT,
                source_component="svc_b", source_instance="i1",
                payload={}, phase_vector=np.zeros(8)
            ),
        ]
        _add_cross_layer_correlations(heus)
        assert heus[0].cross_layer_correlations == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
"""
Unit tests for Holographic Compression - Phase 2.
"""
import pytest
import numpy as np

from cauveris.holographic.compression import (
    HolographicCompressor,
    CompressionConfig,
    CompressionMethod,
    CompressionResult,
    compress_holographic,
    EvidenceSynthesizer,
)
from cauveris.holographic.topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge
from cauveris.holographic.heu import HolographicEvidenceUnit, BoundaryLayer


class TestCompressionConfig:
    """Test CompressionConfig dataclass."""

    def test_defaults(self):
        config = CompressionConfig()
        assert config.method == CompressionMethod.HYBRID
        assert config.target_compression_ratio == 10.0
        assert config.min_fidelity_retention == 0.9
        assert config.pca_variance_threshold == 0.95

    def test_custom(self):
        config = CompressionConfig(
            method=CompressionMethod.PCA_PHASE,
            target_compression_ratio=20.0,
        )
        assert config.method == CompressionMethod.PCA_PHASE
        assert config.target_compression_ratio == 20.0


class TestHolographicCompressor:
    """Test HolographicCompressor class."""

    def setup_method(self):
        self.topo = SystemTopology()
        self.topo.add_component(ComponentInfo(
            name="svc_a",
            capacity=ResourceCapacity(cpu_cores=4.0),
            boundary_layers=["application_log", "metrics_export", "distributed_trace"]
        ))
        self.topo.add_component(ComponentInfo(
            name="svc_b",
            capacity=ResourceCapacity(cpu_cores=2.0),
            boundary_layers=["application_log", "metrics_export"]
        ))
        self.topo.add_causal_edge(CausalEdge(
            source="svc_a",
            target="svc_b",
            latency_ms=5.0
        ))

    def test_compress_small_set(self):
        """Test compression with small HEU set (should not compress)."""

        config = CompressionConfig(target_compression_ratio=10.0)
        compressor = HolographicCompressor(self.topo, config)

        # Less than 10 HEUs - should return as-is
        heus = []
        for i in range(5):
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 10_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="svc_a",
                source_instance="a1",
                payload={},
                phase_vector=np.zeros(8),
            ))

        result = compressor.compress(heus, 1_000_000_000)
        assert result.compression_ratio == 1.0
        assert len(result.compressed_heus) == 5

    def test_compress_pca_method(self):
        """Test PCA-based phase compression."""

        config = CompressionConfig(
            method=CompressionMethod.PCA_PHASE,
            target_compression_ratio=5.0,
            verify_fidelity=False,  # Skip for speed in tests
        )
        compressor = HolographicCompressor(self.topo, config)

        # Create HEUs with diverse phase vectors
        heus = []
        for i in range(50):
            phase = np.zeros(8)
            phase[i % 8] = 1.0  # Each HEU activates different dimension
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 10_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="svc_a",
                source_instance="a1",
                payload={},
                phase_vector=phase.astype(np.float32),
            ))

        result = compressor.compress(heus, 1_000_00_000_000)

        assert result.compression_ratio >= 2.0  # At least some compression
        assert result.method == CompressionMethod.PCA_PHASE
        assert result.fidelity_retention >= 0.0
        assert len(result.compressed_heus) < len(heus)

    def test_compress_cluster_method(self):
        """Test clustering-based compression."""

        config = CompressionConfig(
            method=CompressionMethod.CLUSTER_REP,
            target_compression_ratio=5.0,
            verify_fidelity=False,
        )
        compressor = HolographicCompressor(self.topo, config)

        heus = []
        for i in range(50):
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 10_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG if i % 2 == 0 else BoundaryLayer.METRICS_EXPORT,
                source_component="svc_a" if i % 2 == 0 else "svc_b",
                source_instance="a1" if i % 2 == 0 else "b1",
                payload={},
                phase_vector=np.zeros(8),
            ))

        result = compressor.compress(heus, 1_000_000_000)

        assert result.compression_ratio >= 2.0
        assert result.method == CompressionMethod.CLUSTER_REP

    def test_compress_greedy_method(self):
        """Test greedy fidelity compression."""

        config = CompressionConfig(
            method=CompressionMethod.GREEDY_FIDELITY,
            target_compression_ratio=5.0,
            verify_fidelity=False,
        )
        compressor = HolographicCompressor(self.topo, config)

        heus = []
        for i in range(30):
            # Give different reconstruction weights
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 10_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="svc_a",
                source_instance="a1",
                payload={"cpu_usage": 0.5 + 0.1 * (i % 5)},
                phase_vector=np.zeros(8),
                reconstruction_weight=0.5 + 0.05 * (i % 10),
            ))

        result = compressor.compress(heus, 1_000_000_000)

        assert result.compression_ratio >= 2.0
        assert result.method == CompressionMethod.GREEDY_FIDELITY

    def test_compress_hybrid_method(self):
        """Test hybrid compression (default)."""

        config = CompressionConfig(
            method=CompressionMethod.HYBRID,
            target_compression_ratio=5.0,
            verify_fidelity=False,
        )
        compressor = HolographicCompressor(self.topo, config)

        heus = []
        for i in range(50):
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 10_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG if i % 2 == 0 else BoundaryLayer.METRICS_EXPORT,
                source_component="svc_a" if i % 2 == 0 else "svc_b",
                source_instance="a1" if i % 2 == 0 else "b1",
                payload={},
                phase_vector=np.zeros(8),
            ))

        result = compressor.compress(heus, 1_000_000_000)

        assert result.compression_ratio >= 2.0
        assert result.method == CompressionMethod.HYBRID

    def test_compression_preserves_informative_heus(self):
        """Test that high-weight HEUs are preserved with greedy method."""

        config = CompressionConfig(
            method=CompressionMethod.GREEDY_FIDELITY,
            target_compression_ratio=4.0,
            verify_fidelity=False,
        )
        compressor = HolographicCompressor(self.topo, config)

        heus = []
        for i in range(40):
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 10_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="svc_a",
                source_instance="a1",
                payload={},
                phase_vector=np.zeros(8),
                reconstruction_weight=0.9 if i < 5 else 0.3,  # First 5 are high weight
            ))

        result = compressor.compress(heus, 1_000_000_000)

        # Greedy method should preserve high-weight HEUs
        compressed_ids = {h.heu_id for h in result.compressed_heus}
        for i in range(5):
            assert f"heu_{i}" in compressed_ids, f"High-weight HEU heu_{i} was not preserved"


class TestCompressHolographic:
    """Test convenience function."""

    def test_compress_function(self):
        topo = SystemTopology()
        topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(), boundary_layers=["application_log"]))

        heus = []
        for i in range(20):
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 10_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="svc_a",
                source_instance="a1",
                payload={},
                phase_vector=np.zeros(8),
            ))

        result = compress_holographic(topo, heus, 1_000_000_000)
        assert isinstance(result, CompressionResult)
        assert result.compression_ratio >= 1.0


class TestEvidenceSynthesizer:
    """Test EvidenceSynthesizer class."""

    def setup_method(self):
        self.topo = SystemTopology()
        self.topo.add_component(ComponentInfo(
            name="svc_a",
            capacity=ResourceCapacity(cpu_cores=4.0),
            boundary_layers=["application_log", "metrics_export", "distributed_trace"]
        ))

    def test_synthesize_missing_layers(self):
        """Test synthesizing missing boundary layers."""
        from cauveris.holographic.reconstruction import HolographicReconstruction, ReconstructedServiceState

        synth = EvidenceSynthesizer(self.topo)

        # Mock reconstruction with service state
        recon = HolographicReconstruction(
            incident_id="TEST",
            reconstruction_timestamp_ns=1_000_000_000,
            time_window_ns=(0, 1_000_000_000),
        )
        recon.reconstructed_services["svc_a"] = ReconstructedServiceState(
            component_name="svc_a",
            instance_id="a1",
            cpu_usage=0.8,
            memory_usage=0.6,
            network_usage=0.3,
        )

        observed = {"svc_a": [BoundaryLayer.APPLICATION_LOG]}  # Missing metrics and trace
        missing_heus = synth.synthesize_missing_layers(
            recon,
            observed,
            (0, 1_000_000_000)
        )

        assert len(missing_heus) > 0
        # Should create HEUs for missing layers
        layers = {h.boundary_layer for h in missing_heus}
        expected_missing = {BoundaryLayer.METRICS_EXPORT, BoundaryLayer.DISTRIBUTED_TRACE}
        assert expected_missing.issubset(layers)

        # All should be marked as synthesized
        for heu in missing_heus:
            assert heu.is_synthesized
            assert heu.reconstruction_weight <= 0.5
            assert heu.ambiguity_score >= 0.5

    def test_synthesize_payload_estimation(self):
        """Test payload estimation for different layers."""
        from cauveris.holographic.reconstruction import HolographicReconstruction, ReconstructedServiceState

        synth = EvidenceSynthesizer(self.topo)

        recon = HolographicReconstruction(
            incident_id="TEST",
            reconstruction_timestamp_ns=1_000_000_000,
            time_window_ns=(0, 1_000_000_000),
        )
        recon.reconstructed_services["svc_a"] = ReconstructedServiceState(
            component_name="svc_a",
            instance_id="a1",
            cpu_usage=0.8,
            memory_usage=0.6,
            network_usage=0.3,
            config_version="v42",
        )

        observed = {"svc_a": []}  # All layers missing
        missing_heus = synth.synthesize_missing_layers(
            recon,
            observed,
            (0, 1_000_000_000)
        )

        # Check specific payload content per layer
        log_heus = [h for h in missing_heus if h.boundary_layer == BoundaryLayer.APPLICATION_LOG]
        metric_heus = [h for h in missing_heus if h.boundary_layer == BoundaryLayer.METRICS_EXPORT]
        trace_heus = [h for h in missing_heus if h.boundary_layer == BoundaryLayer.DISTRIBUTED_TRACE]

        assert len(log_heus) > 0
        assert len(metric_heus) > 0
        assert len(trace_heus) > 0

        # Log should mention CPU
        assert "CPU" in log_heus[0].payload.get("message", "")

        # Metric should have numeric values
        assert "cpu_usage" in metric_heus[0].payload
        assert metric_heus[0].payload["cpu_usage"] > 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

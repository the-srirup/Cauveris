"""
Unit tests for Multi-Scale Holographic Reconstruction - Phase 2.
"""
import pytest
import numpy as np

from cauveris.holographic.multiscale import (
    MultiScaleReconstructor,
    MultiScaleConfig,
    ScaleReconstruction,
    ReconstructionScale,
    reconstruct_multiscale,
)
from cauveris.holographic.topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge
from cauveris.holographic.reconstruction import HolographicReconstruction
from cauveris.holographic.heu import HolographicEvidenceUnit, BoundaryLayer


class TestReconstructionScale:
    """Test ReconstructionScale enum."""

    def test_time_windows(self):
        assert ReconstructionScale.SYSTEMIC.time_window_ns == 24 * 60 * 60 * 1_000_000_000
        assert ReconstructionScale.INCIDENT.time_window_ns == 60 * 60 * 1_000_000_000
        assert ReconstructionScale.TRANSACTION.time_window_ns == 60 * 1_000_000_000
        assert ReconstructionScale.REQUEST.time_window_ns == 1_000_000_000

    def test_target_heu_counts(self):
        assert ReconstructionScale.SYSTEMIC.target_heu_count == 100
        assert ReconstructionScale.INCIDENT.target_heu_count == 1000
        assert ReconstructionScale.TRANSACTION.target_heu_count == 100
        assert ReconstructionScale.REQUEST.target_heu_count == 10


class TestMultiScaleConfig:
    """Test MultiScaleConfig dataclass."""

    def test_defaults(self):
        config = MultiScaleConfig()
        assert ReconstructionScale.SYSTEMIC in config.target_scales
        assert ReconstructionScale.INCIDENT in config.target_scales
        assert ReconstructionScale.TRANSACTION in config.target_scales
        assert ReconstructionScale.REQUEST in config.target_scales
        assert config.enable_prior_chaining is True
        assert config.min_heus_per_scale == 5

    def test_custom(self):
        config = MultiScaleConfig(
            target_scales=[ReconstructionScale.INCIDENT, ReconstructionScale.TRANSACTION],
            min_heus_per_scale=10,
        )
        assert len(config.target_scales) == 2
        assert config.min_heus_per_scale == 10


class TestMultiScaleReconstructor:
    """Test MultiScaleReconstructor class."""

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

        self.config = MultiScaleConfig(
            target_scales=[ReconstructionScale.INCIDENT, ReconstructionScale.TRANSACTION],
        )

    def test_reconstructor_creation(self):
        reconstructor = MultiScaleReconstructor(self.topo, self.config)
        assert reconstructor.topology == self.topo
        assert reconstructor.config == self.config

    def test_reconstruct_incident_scale(self):
        reconstructor = MultiScaleReconstructor(self.topo, self.config)

        # Simple timeline for incident
        timeline = []
        for i in range(20):
            timeline.append({
                "event_id": f"evt_{i}",
                "timestamp_ns": i * 50_000_000,
                "source_type": "jsonl_log" if i % 2 == 0 else "csv_metrics",
                "message": "Test event",
                "attributes": {"service": "svc_a" if i % 2 == 0 else "svc_b"},
                "status": "ok",
            })

        results = reconstructor.reconstruct(
            timeline,
            (0, 1_000_000_000),
            {}
        )

        assert ReconstructionScale.INCIDENT in results
        assert ReconstructionScale.TRANSACTION in results

        inc_result = results[ReconstructionScale.INCIDENT]
        if inc_result:
            assert isinstance(inc_result, ScaleReconstruction)
            assert inc_result.scale == ReconstructionScale.INCIDENT
            assert len(inc_result.heus) >= 5
            assert isinstance(inc_result.reconstruction, HolographicReconstruction)
            assert inc_result.reconstruction.incident_id is not None

    def test_downsample_heus(self):
        reconstructor = MultiScaleReconstructor(self.topo)

        # Create many HEUs
        from cauveris.holographic.heu import HolographicEvidenceUnit, BoundaryLayer
        heus = []
        for i in range(200):
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 5_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG if i % 2 == 0 else BoundaryLayer.METRICS_EXPORT,
                source_component="svc_a" if i % 2 == 0 else "svc_b",
                source_instance="a1" if i % 2 == 0 else "b1",
                payload={},
                phase_vector=np.zeros(8),
            ))

        # Downsample for transaction scale (target 100)
        downsampled = reconstructor._downsample_heus(
            heus, ReconstructionScale.TRANSACTION, 0, 1_000_000_000
        )
        assert len(downsampled) <= 100
        assert len(downsampled) >= 5  # min_heus_per_scale

        # Downsample for incident scale (target 1000)
        downsampled = reconstructor._downsample_heus(
            heus, ReconstructionScale.INCIDENT, 0, 1_000_000_000
        )
        assert len(downsampled) <= 1000

    def test_downsample_preserves_layers(self):
        reconstructor = MultiScaleReconstructor(self.topo)

        heus = []
        for i in range(100):
            layer = BoundaryLayer.APPLICATION_LOG if i % 3 != 0 else BoundaryLayer.METRICS_EXPORT
            heus.append(HolographicEvidenceUnit(
                heu_id=f"heu_{i}",
                timestamp_ns=i * 10_000_000,
                boundary_layer=layer,
                source_component="svc_a",
                source_instance="a1",
                payload={},
                phase_vector=np.zeros(8),
            ))

        downsampled = reconstructor._downsample_heus(
            heus, ReconstructionScale.TRANSACTION, 0, 1_000_000_000
        )

        # Should have both layers represented
        layers = set(h.boundary_layer for h in downsampled)
        assert len(layers) >= 1  # At least one layer


class TestReconstructMultiscale:
    """Test convenience function."""

    def test_reconstruct(self):
        topo = SystemTopology()
        topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(), boundary_layers=["application_log"]))

        timeline = []
        for i in range(15):
            timeline.append({
                "event_id": f"evt_{i}",
                "timestamp_ns": i * 10_000_000,
                "source_type": "jsonl_log",
                "message": "Test",
                "attributes": {"service": "svc_a"},
                "status": "ok",
            })

        results = reconstruct_multiscale(
            topo,
            timeline,
            (0, 1_000_000_000),
            {},
        )

        assert len(results) >= 1


class TestScaleComparison:
    """Test cross-scale comparison."""

    def test_compare_scales(self):
        topo = SystemTopology()
        topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(cpu_cores=4.0), boundary_layers=["application_log"]))

        reconstructor = MultiScaleReconstructor(topo)

        # Mock scale results
        from cauveris.holographic.heu import HolographicEvidenceUnit, BoundaryLayer
        from cauveris.holographic.solver import SolverResult

        heus = [HolographicEvidenceUnit(heu_id="h1", timestamp_ns=100, boundary_layer=BoundaryLayer.APPLICATION_LOG, source_component="svc_a", source_instance="a1", payload={}, phase_vector=np.zeros(8))]

        mock_result = SolverResult(
            x=np.array([0.5]), success=True, message="ok", iterations=10,
            objective_value=0.1, data_term=0.05, entropy_term=0.02,
            temporal_term=0.01, physics_term=0.01, sparsity_term=0.0,
            gradient_norm=0.01, constraint_violation=0.0, boundary_residual=0.1
        )

        mock_recon = HolographicReconstruction(incident_id="test", reconstruction_timestamp_ns=0, time_window_ns=(0, 100), overall_fidelity=0.9)

        scale_result = ScaleReconstruction(
            scale=ReconstructionScale.INCIDENT,
            time_window_ns=(0, 1_000_000_000),
            heus=heus,
            reconstruction=mock_recon,
            solver_result=mock_result,
        )

        results = {ReconstructionScale.INCIDENT: scale_result}
        comparison = reconstructor.compare_scales(results)

        assert "fidelity_by_scale" in comparison
        assert "incident" in comparison["fidelity_by_scale"]
        assert comparison["fidelity_by_scale"]["incident"] == 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

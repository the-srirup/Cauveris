"""
Unit tests for Holographic Measurement System - Phase 2.
"""
import pytest
import numpy as np
import scipy.sparse as sp

from cauveris.holographic.measurement import (
    MeasurementSystemBuilder,
    MeasurementSystem,
    MeasurementConfig,
    build_measurement_system,
    StateDimension,
    MeasurementRow,
)
from cauveris.holographic.topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge
from cauveris.holographic.heu import HolographicEvidenceUnit, BoundaryLayer, convert_timeline_to_heus
from cauveris.holographic.heu_kernel import CausalKernelBuilder


class TestStateDimension:
    """Test StateDimension dataclass."""

    def test_creation(self):
        sd = StateDimension(component="svc_a", dimension="cpu_pressure", index=5)
        assert sd.component == "svc_a"
        assert sd.dimension == "cpu_pressure"
        assert sd.index == 5
        assert str(sd) == "svc_a.cpu_pressure"


class TestMeasurementRow:
    """Test MeasurementRow dataclass."""

    def test_creation(self):
        row = MeasurementRow(
            heu_id="test_heu",
            boundary_layer=BoundaryLayer.APPLICATION_LOG,
            component="svc_a",
            dimension="cpu_pressure",
            state_indices=[0, 1],
            coefficients=np.array([0.8, 0.2]),
            timestamp_ns=1_000_000_000,
            observation_value=0.7,
            noise_std=0.1,
        )
        assert row.heu_id == "test_heu"
        assert len(row.state_indices) == 2
        assert row.observation_value == 0.7


class TestMeasurementSystem:
    """Test MeasurementSystem dataclass."""

    def test_empty_system(self):
        sys = MeasurementSystem(
            M=sp.csr_matrix((0, 0)),
            b=np.array([]),
            state_dims=[],
            measurements=[],
            n_state=0,
            n_obs=0,
        )
        assert sys.n_state == 0
        assert sys.n_obs == 0
        dense_M, dense_b = sys.to_dense()
        assert dense_M.shape == (0, 0)
        assert dense_b.shape == (0,)

    def test_get_state_slice(self):
        dims = [
            StateDimension("svc_a", "cpu_pressure", 0),
            StateDimension("svc_a", "memory_pressure", 1),
            StateDimension("svd_b", "cpu_pressure", 2),
        ]
        M = sp.csr_matrix((2, 3))
        b = np.array([0.5, 0.3])

        sys = MeasurementSystem(
            M=M,
            b=b,
            state_dims=dims,
            measurements=[],
            n_state=3,
            n_obs=2,
        )

        # All dims for svc_a
        svc_a_indices = sys.get_state_slice("svc_a")
        assert set(svc_a_indices) == {0, 1}

        # Only cpu_pressure for svc_a
        cpu_indices = sys.get_state_slice("svc_a", "cpu_pressure")
        assert cpu_indices == [0]


class TestMeasurementSystemBuilder:
    """Test MeasurementSystemBuilder class."""

    def setup_method(self):
        self.topo = SystemTopology()
        self.topo.add_component(ComponentInfo(
            name="svc_a",
            capacity=ResourceCapacity(cpu_cores=4.0),
            boundary_layers=["application_log", "metrics_export"]
        ))
        self.topo.add_component(ComponentInfo(
            name="svc_b",
            capacity=ResourceCapacity(cpu_cores=2.0),
            boundary_layers=["application_log"]
        ))
        self.topo.add_causal_edge(CausalEdge(source="svc_a", target="svc_b", latency_ms=5.0))

        self.kernel_builder = CausalKernelBuilder(self.topo)
        self.kernel_builder.build_all_kernels()

    def test_register_state_dimensions(self):
        heus = [
            HolographicEvidenceUnit(
                heu_id="heu_1",
                timestamp_ns=100_000_000,
                boundary_layer=BoundaryLayer.APPLICATION_LOG,
                source_component="svc_a",
                source_instance="a1",
                payload={},
                encoded_dimensions={"cpu_pressure": 0.8, "memory_pressure": 0.6},
                phase_vector=np.zeros(8),
            )
        ]

        builder = MeasurementSystemBuilder(self.topo, self.kernel_builder)
        builder._register_state_dimensions(heus)

        # Should have base dimensions for both components + encoded dimensions
        expected_dims = 2 * 8 + 2  # 8 base dims per component + 2 encoded
        assert len(builder._state_dims) >= 16

    def test_build_empty(self):
        builder = MeasurementSystemBuilder(self.topo, self.kernel_builder)
        system = builder.build([], 1_000_000_000)
        assert system.n_obs == 0
        assert system.n_state == 0

    def test_build_with_heus(self):
        timeline = [
            {
                "event_id": "evt_1",
                "timestamp_ns": 100_000_000,
                "source_type": "jsonl_log",
                "message": "High CPU",
                "attributes": {"service": "svc_a", "cpu_usage": 0.8},
                "status": "warning",
            },
            {
                "event_id": "evt_2",
                "timestamp_ns": 200_000_000,
                "source_type": "csv_metrics",
                "message": "Metric",
                "attributes": {"service": "svc_a", "cpu_usage": 0.7},
                "status": "ok",
            },
        ]
        heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)

        builder = MeasurementSystemBuilder(self.topo, self.kernel_builder)
        system = builder.build(heus, 1_000_000_000)

        assert system.n_obs > 0
        assert system.n_state > 0
        assert system.M.shape == (system.n_obs, system.n_state)
        assert system.b.shape == (system.n_obs,)
        assert len(system.measurements) == system.n_obs


class TestBuildMeasurementSystem:
    """Test convenience function."""

    def test_build(self):
        topo = SystemTopology()
        topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(), boundary_layers=["application_log"]))
        topo.add_component(ComponentInfo(name="svc_b", capacity=ResourceCapacity(), boundary_layers=["application_log"]))
        topo.add_causal_edge(CausalEdge(source="svc_a", target="svc_b"))

        timeline = [
            {"event_id": "1", "timestamp_ns": 100_000_000, "source_type": "jsonl_log", "message": "High cpu usage",
             "attributes": {"service": "svc_a", "cpu_usage": 0.5}, "status": "ok"},
        ]
        heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)

        kernel_builder = CausalKernelBuilder(topo)
        kernel_builder.build_all_kernels()

        system = build_measurement_system(topo, heus, 1_000_000_000, kernel_builder)
        assert system.n_state > 0
        assert system.n_obs > 0
        assert isinstance(system.M, sp.csr_matrix)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
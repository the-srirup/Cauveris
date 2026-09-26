"""
Unit tests for Holographic Causal Kernels - Phase 2.
"""
import pytest
import numpy as np

from cauveris.holographic.heu_kernel import (
    CausalKernelBuilder,
    KernelConfig,
    LocalPropagationKernel,
    CrossPropagationKernel,
    build_causal_kernels,
)
from cauveris.holographic.topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge


class TestKernelConfig:
    """Test KernelConfig dataclass."""

    def test_defaults(self):
        config = KernelConfig()
        assert config.time_step_ns == 1_000_000
        assert config.max_kernel_time_ns == 10_000_000_000
        assert config.decay_type == "exponential"
        assert config.normalization == "l1"

    def test_custom(self):
        config = KernelConfig(
            time_step_ns=500_000,
            decay_type="gamma",
            normalization="l2"
        )
        assert config.time_step_ns == 500_000
        assert config.decay_type == "gamma"


class TestLocalPropagationKernel:
    """Test LocalPropagationKernel dataclass."""

    def test_creation(self):
        time_axis = np.arange(0, 1_000_000_000, 1_000_000)
        kernel_vals = np.exp(-time_axis / 10_000_000)

        kernel = LocalPropagationKernel(
            component_name="test",
            boundary_layer="application_log",
            time_axis_ns=time_axis,
            kernel_values=kernel_vals,
            integral=1.0,
            peak_time_ns=0.0,
            half_life_ns=6_931_471,  # ln(2) * 10ms
        )
        assert kernel.component_name == "test"
        assert kernel.evaluate_at(0) == kernel_vals[0]
        assert kernel.evaluate_at(5_000_000) > 0

    def test_evaluate_out_of_bounds(self):
        time_axis = np.arange(0, 1_000_000_000, 1_000_000)
        kernel_vals = np.exp(-time_axis / 10_000_000)

        kernel = LocalPropagationKernel(
            component_name="test",
            boundary_layer="application_log",
            time_axis_ns=time_axis,
            kernel_values=kernel_vals,
            integral=1.0,
            peak_time_ns=0.0,
            half_life_ns=6_931_471,
        )
        # Out of bounds returns 0
        assert kernel.evaluate_at(-1) == 0.0
        assert kernel.evaluate_at(2_000_000_000) == 0.0


class TestCausalKernelBuilder:
    """Test CausalKernelBuilder class."""

    def setup_method(self):
        self.topo = SystemTopology()
        self.topo.add_component(ComponentInfo(
            name="svc_a",
            capacity=ResourceCapacity(cpu_cores=4.0),
            boundary_layers=["application_log", "distributed_trace", "metrics_export"]
        ))
        self.topo.add_component(ComponentInfo(
            name="svc_b",
            capacity=ResourceCapacity(cpu_cores=2.0),
            boundary_layers=["application_log", "metrics_export"]
        ))
        self.topo.add_causal_edge(CausalEdge(
            source="svc_a",
            target="svc_b",
            latency_ms=5.0,
            edge_type="rpc",
            queue_depth=2
        ))

    def test_build_all_kernels(self):
        config = KernelConfig(max_kernel_time_ns=1_000_000_000)  # 1s for faster test
        builder = CausalKernelBuilder(self.topo, config)
        kernels = builder.build_all_kernels()

        # Should have local kernels for each component-layer pair
        assert ("svc_a", "application_log") in kernels["local"]
        assert ("svc_a", "distributed_trace") in kernels["local"]
        assert ("svc_b", "application_log") in kernels["local"]

        # Should have cross kernels
        assert ("svc_a", "svc_b", "application_log", "application_log") in kernels["cross"]
        assert ("svc_a", "svc_b", "distributed_trace", "application_log") in kernels["cross"]

    def test_local_kernel_properties(self):
        config = KernelConfig(max_kernel_time_ns=1_000_000_000)
        builder = CausalKernelBuilder(self.topo, config)
        builder.build_all_kernels()

        kernel = builder.get_local_kernel("svc_a", "application_log")
        assert isinstance(kernel, LocalPropagationKernel)
        assert kernel.component_name == "svc_a"
        assert kernel.boundary_layer == "application_log"
        assert kernel.integral > 0.5  # Should be normalized
        assert kernel.peak_time_ns >= 0
        assert kernel.half_life_ns > 0

    def test_cross_kernel_properties(self):
        config = KernelConfig(max_kernel_time_ns=1_000_000_000)
        builder = CausalKernelBuilder(self.topo, config)
        builder.build_all_kernels()

        kernel = builder.get_cross_kernel("svc_a", "svc_b", "application_log", "application_log")
        assert isinstance(kernel, CrossPropagationKernel)
        assert kernel.source == "svc_a"
        assert kernel.target == "svc_b"
        assert kernel.edge_type == "rpc"
        # Cross kernel should have longer total latency than local
        local_a = builder.get_local_kernel("svc_a", "application_log")
        local_b = builder.get_local_kernel("svc_b", "application_log")
        assert kernel.total_latency_ns > local_a.peak_time_ns + local_b.peak_time_ns

    def test_kernel_matrix_shape(self):
        config = KernelConfig(max_kernel_time_ns=100_000_000)  # 100ms
        builder = CausalKernelBuilder(self.topo, config)
        builder.build_all_kernels()

        K = builder.build_kernel_matrix(
            components=["svc_a", "svc_b"],
            layers=["application_log", "metrics_export"],
            time_horizon_ns=100_000_000
        )
        # (n_components * n_layers, n_components, n_time_steps)
        expected_time = 100_000_000 // config.time_step_ns
        assert K.shape == (4, 2, expected_time)

    def test_verify_causality(self):
        config = KernelConfig(max_kernel_time_ns=1_000_000_000)
        builder = CausalKernelBuilder(self.topo, config)
        builder.build_all_kernels()

        checks = builder.verify_causality()
        assert "no_anticipation" in checks
        assert "conservation" in checks
        assert "peak_ordering" in checks
        # All should pass for our simple test case
        assert checks["no_anticipation"] is True
        assert checks["conservation"] is True
        assert checks["peak_ordering"] is True

    def test_different_decay_types(self):
        for decay_type in ["exponential", "gamma", "bi_exponential"]:
            config = KernelConfig(max_kernel_time_ns=100_000_000, decay_type=decay_type)
            builder = CausalKernelBuilder(self.topo, config)
            builder.build_all_kernels()
            kernel = builder.get_local_kernel("svc_a", "application_log")
            assert np.allclose(np.trapezoid(kernel.kernel_values, kernel.time_axis_ns), 1.0, atol=0.1)


class TestBuildCausalKernels:
    """Test convenience function."""

    def test_build_kernels(self):
        topo = SystemTopology()
        topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity()))
        topo.add_component(ComponentInfo(name="svc_b", capacity=ResourceCapacity()))
        topo.add_causal_edge(CausalEdge(source="svc_a", target="svc_b"))

        kernels = build_causal_kernels(topo)
        assert "local" in kernels
        assert "cross" in kernels
        assert len(kernels["local"]) == 2  # svc_a and svc_b (each has application_log layer by default)

    def test_with_config(self):
        topo = SystemTopology()
        topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(cpu_cores=8.0), boundary_layers=["application_log"]))

        config = KernelConfig(decay_type="gamma")
        kernels = build_causal_kernels(topo, config)
        assert len(kernels["local"]) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

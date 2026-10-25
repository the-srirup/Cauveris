"""
Tests for the GPU kernel path.

The CUDA extension is optional, so the tests that need a device are skipped
when there is none.  The tests that always run check the two things that
must hold whatever the machine looks like:

* the CPU fallback of :class:`GPUAcceleratedKernelBuilder` produces exactly
  what the reference implementation produces, and
* ``get_gpu_info()`` tells the truth about what is available and why.

The equivalence tests compare the GPU against the NumPy reference.  They are
the point of the whole exercise: a GPU path that computes something else is
worse than no GPU path at all.
"""

from __future__ import annotations

import numpy as np
import pytest

from cauveris.holographic.gpu_kernels import (
    EXTENSION_AVAILABLE,
    GPUConfig,
    GPUAcceleratedKernelBuilder,
    DecayType,
    NormalizationType,
    create_gpu_kernel_builder,
    get_gpu_info,
    is_gpu_available,
)
from cauveris.holographic.heu_kernel import CausalKernelBuilder
from cauveris.holographic.topology import (
    CausalEdge,
    ComponentInfo,
    ResourceCapacity,
    SystemTopology,
)

requires_gpu = pytest.mark.skipif(
    not is_gpu_available(),
    reason="the CUDA extension is not installed or no CUDA device is present",
)


def build_topology() -> SystemTopology:
    """A topology with three components, uneven layer counts and two edges."""
    topology = SystemTopology()
    topology.add_component(
        ComponentInfo(
            name="svc_a",
            component_type="service",
            capacity=ResourceCapacity(cpu_cores=4.0),
            boundary_layers=["application_log", "distributed_trace", "metrics_export"],
        )
    )
    topology.add_component(
        ComponentInfo(
            name="db_b",
            component_type="database",
            capacity=ResourceCapacity(cpu_cores=8.0, memory_gb=32.0),
            boundary_layers=["application_log", "metrics_export"],
        )
    )
    topology.add_component(
        ComponentInfo(
            name="queue_c",
            component_type="queue",
            capacity=ResourceCapacity(cpu_cores=2.0),
            boundary_layers=["application_log"],
        )
    )
    topology.add_causal_edge(
        CausalEdge(
            source="svc_a",
            target="db_b",
            latency_ms=5.0,
            edge_type="rpc",
            queue_depth=3,
        )
    )
    topology.add_causal_edge(
        CausalEdge(
            source="svc_a",
            target="queue_c",
            latency_ms=1.5,
            edge_type="topic",
            queue_depth=0,
        )
    )
    return topology


def small_config(**overrides) -> GPUConfig:
    """A short time axis, so that the tests stay quick."""
    settings = {
        "time_step_ns": 1_000_000,
        "max_kernel_time_ns": 1_000_000_000,
    }
    settings.update(overrides)
    return GPUConfig(**settings)


class TestAvailability:
    """What the module reports about the machine it runs on."""

    def test_gpu_info_is_honest(self):
        info = get_gpu_info()
        assert isinstance(info, dict)
        assert "available" in info
        if not info["available"]:
            # A machine without a GPU still has to say why.
            assert info.get("reason"), "an unavailable GPU must come with a reason"
        else:
            assert info.get("device_name")
            assert info.get("compute_capability")
            assert info["total_memory_mb"] > 0
            assert info["source"] == "cuda_runtime"

    def test_availability_flag_matches_the_extension(self):
        if not EXTENSION_AVAILABLE:
            assert is_gpu_available() is False
        else:
            assert isinstance(is_gpu_available(), bool)

    def test_extension_import_error_is_recorded(self):
        if not EXTENSION_AVAILABLE:
            info = get_gpu_info()
            assert "cauveris_kernels_py" in info["reason"]


class TestCPUFallback:
    """The fallback has to be indistinguishable from the reference."""

    def test_cpu_fallback_matches_the_reference(self):
        topology = build_topology()
        config = small_config()

        reference = CausalKernelBuilder(topology, config.to_cpu_config())
        reference.build_all_kernels()

        fallback = create_gpu_kernel_builder(topology, config)
        fallback.build_all_kernels()

        assert set(fallback._local_kernels) == set(reference._local_kernels)
        assert set(fallback._cross_kernels) == set(reference._cross_kernels)

        for key, expected in reference._local_kernels.items():
            actual = fallback._local_kernels[key]
            assert np.allclose(actual.kernel_values, expected.kernel_values, atol=1e-12)
            assert actual.integral == pytest.approx(expected.integral)
            assert actual.peak_time_ns == pytest.approx(expected.peak_time_ns)
            assert actual.half_life_ns == pytest.approx(expected.half_life_ns)

        for key, expected in reference._cross_kernels.items():
            actual = fallback._cross_kernels[key]
            assert np.allclose(actual.kernel_values, expected.kernel_values, atol=1e-12)
            assert actual.total_latency_ns == pytest.approx(expected.total_latency_ns)

    def test_disabling_the_gpu_uses_the_reference(self):
        topology = build_topology()
        builder = GPUAcceleratedKernelBuilder(topology, small_config(use_gpu=False))
        assert builder._use_gpu is False
        result = builder.build_all_kernels()
        assert result["local"]
        assert result["cross"]

    def test_lookups_accept_enum_and_string_layers(self):
        from cauveris.holographic.heu import BoundaryLayer

        topology = build_topology()
        builder = create_gpu_kernel_builder(topology, small_config())
        builder.build_all_kernels()
        assert builder.get_local_kernel("svc_a", "application_log") is not None
        assert builder.get_local_kernel("svc_a", BoundaryLayer.APPLICATION_LOG) is not None


@requires_gpu
class TestGPUEquivalence:
    """The GPU has to reproduce the reference, not approximate it."""

    @pytest.mark.parametrize("decay", list(DecayType))
    @pytest.mark.parametrize("normalization", list(NormalizationType))
    def test_local_kernels_match_the_reference(self, decay, normalization):
        topology = build_topology()
        config = small_config(decay_type=decay, normalization=normalization)

        reference = CausalKernelBuilder(topology, config.to_cpu_config())
        reference.build_all_kernels()

        builder = create_gpu_kernel_builder(topology, config)
        builder.build_all_kernels()

        assert len(builder._local_kernels) == len(reference._local_kernels)
        for key, expected in reference._local_kernels.items():
            actual = builder._local_kernels[key]
            peak = float(np.max(np.abs(expected.kernel_values)))
            assert peak > 0.0
            # The comparison is relative to the peak of the kernel: the
            # absolute values of a normalized kernel are tiny.
            assert np.max(np.abs(actual.kernel_values - expected.kernel_values)) <= (
                1e-5 * peak
            )
            assert actual.integral == pytest.approx(expected.integral, rel=1e-6)
            assert actual.peak_time_ns == pytest.approx(expected.peak_time_ns)
            assert actual.half_life_ns == pytest.approx(expected.half_life_ns)

    def test_cross_kernels_match_the_reference(self):
        topology = build_topology()
        config = small_config()

        reference = CausalKernelBuilder(topology, config.to_cpu_config())
        reference.build_all_kernels()

        builder = create_gpu_kernel_builder(topology, config)
        builder.build_all_kernels()

        assert len(builder._cross_kernels) == len(reference._cross_kernels)
        for key, expected in reference._cross_kernels.items():
            actual = builder._cross_kernels[key]
            peak = float(np.max(np.abs(expected.kernel_values)))
            assert peak > 0.0
            assert np.max(np.abs(actual.kernel_values - expected.kernel_values)) <= (
                1e-4 * peak
            )
            assert actual.total_latency_ns == pytest.approx(expected.total_latency_ns)

    def test_cross_kernel_respects_the_transport_delay(self):
        """A slow edge has to move the response to the right."""
        topology = build_topology()
        builder = create_gpu_kernel_builder(topology, small_config())
        builder.build_all_kernels()

        fast = builder.get_cross_kernel("svc_a", "queue_c", "application_log", "application_log")
        slow = builder.get_cross_kernel("svc_a", "db_b", "application_log", "application_log")
        assert fast is not None and slow is not None
        # The queue edge has 1.5ms of latency and no queueing, the database
        # edge has 5ms plus 3 messages of queueing.
        assert slow.network_latency_ns > fast.network_latency_ns
        assert slow.queueing_latency_ns > 0
        assert fast.queueing_latency_ns == 0

    def test_kernel_matrix_matches_the_reference(self):
        topology = build_topology()
        config = small_config()
        components = ["svc_a", "db_b", "queue_c"]
        layers = ["application_log", "metrics_export"]
        horizon = 500_000_000

        reference = CausalKernelBuilder(topology, config.to_cpu_config())
        reference.build_all_kernels()
        expected = reference.build_kernel_matrix(components, layers, horizon)

        builder = create_gpu_kernel_builder(topology, config)
        builder.build_all_kernels()
        actual = builder.build_kernel_matrix(components, layers, horizon)

        assert actual.shape == expected.shape
        assert np.max(np.abs(actual - expected)) <= 1e-6 * float(np.max(np.abs(expected)))

    def test_causality_checks_pass_on_the_gpu(self):
        topology = build_topology()
        builder = create_gpu_kernel_builder(topology, small_config())
        builder.build_all_kernels()
        checks = builder.verify_causality()
        assert checks["no_anticipation"] is True
        assert checks["conservation"] is True
        assert checks["peak_ordering"] is True


@requires_gpu
class TestLinalg:
    """The linear algebra primitives have to be correct, not just present."""

    def test_matmul_matches_numpy(self):
        import cauveris_kernels_py as kernels

        rng = np.random.default_rng(7)
        a = rng.normal(size=(5, 4)).astype(np.float32)
        b = rng.normal(size=(4, 6)).astype(np.float32)
        got = kernels.matmul(a, b)
        expected = a @ b
        assert got.shape == expected.shape
        assert np.allclose(got, expected, atol=1e-4)

    def test_batch_matmul_matches_numpy(self):
        import cauveris_kernels_py as kernels

        rng = np.random.default_rng(11)
        a = rng.normal(size=(3, 5, 4)).astype(np.float32)
        b = rng.normal(size=(3, 4, 6)).astype(np.float32)
        got = kernels.batch_matmul(a, b)
        expected = np.stack([a[i] @ b[i] for i in range(3)])
        assert got.shape == expected.shape
        assert np.allclose(got, expected, atol=1e-4)

    def test_norms_and_products(self):
        import cauveris_kernels_py as kernels

        rng = np.random.default_rng(13)
        x = rng.normal(size=256).astype(np.float32)
        y = rng.normal(size=256).astype(np.float32)
        assert kernels.dot_product(x, y) == pytest.approx(float(x @ y), rel=1e-4)
        assert kernels.l2_norm(x) == pytest.approx(float(np.linalg.norm(x)), rel=1e-4)
        assert kernels.l1_norm(x) == pytest.approx(float(np.abs(x).sum()), rel=1e-4)

    def test_conjugate_gradient_solves_a_spd_system(self):
        import cauveris_kernels_py as kernels

        rng = np.random.default_rng(17)
        m = rng.normal(size=(60, 60)).astype(np.float32)
        a = (m @ m.T + 6.0 * np.eye(60)).astype(np.float32)
        x_true = rng.normal(size=60).astype(np.float32)
        b = (a @ x_true).astype(np.float32)

        result = kernels.solve_cg_dense(a, b, tol=1e-5)
        assert result["converged"] is True
        assert np.max(np.abs(result["x"] - x_true)) < 1e-2

    def test_conjugate_gradient_on_a_sparse_matrix(self):
        import cauveris_kernels_py as kernels

        # A path graph: n nodes, each connected to its neighbour.
        n = 64
        rows, cols, values = [], [], []
        row_ptr = [0]
        for i in range(n):
            for j in (i - 1, i, i + 1):
                if 0 <= j < n:
                    cols.append(j)
                    values.append(4.0 if j == i else -1.0)
            row_ptr.append(len(cols))
        b = np.ones(n, dtype=np.float32)

        result = kernels.solve_cg_csr(
            np.asarray(row_ptr, dtype=np.int32),
            np.asarray(cols, dtype=np.int32),
            np.asarray(values, dtype=np.float32),
            b,
            tol=1e-5,
        )
        assert result["converged"] is True

        # The solution of this system is not constant: the boundary rows
        # have one neighbour instead of two, so the interior bulges upwards
        # and the ends hang lower.  The solver is checked against the
        # solution of the same matrix, computed densely.
        dense = np.zeros((n, n), dtype=np.float32)
        for i in range(n):
            for j in (i - 1, i, i + 1):
                if 0 <= j < n:
                    dense[i, j] = 4.0 if j == i else -1.0
        expected = np.linalg.solve(dense, b)
        assert np.max(np.abs(result["x"] - expected)) < 1e-3

    def test_regularized_least_squares_matches_numpy(self):
        import cauveris_kernels_py as kernels

        rng = np.random.default_rng(19)
        a = rng.normal(size=(40, 8)).astype(np.float32)
        b = rng.normal(size=40).astype(np.float32)
        lam = np.full(8, 0.5, dtype=np.float32)

        result = kernels.solve_rls(a, b, lam, 40, 8)
        expected = np.linalg.solve(a.T @ a + np.diag(lam), a.T @ b)
        assert np.max(np.abs(result["x"] - expected)) < 1e-2
        assert result["converged"] is True

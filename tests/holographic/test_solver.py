"""
Unit tests for Holographic Inverse Solver - Phase 2.
"""
import pytest
import numpy as np
import scipy.sparse as sp

from cauveris.holographic.solver import (
    HolographicSolver,
    SolverConfig,
    SolverMethod,
    SolverResult,
    solve_holographic_inverse,
)
from cauveris.holographic.topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge
from cauveris.holographic.heu import convert_timeline_to_heus
from cauveris.holographic.heu_kernel import CausalKernelBuilder
from cauveris.holographic.measurement import build_measurement_system, MeasurementConfig


class TestSolverConfig:
    """Test SolverConfig dataclass."""

    def test_defaults(self):
        config = SolverConfig()
        assert config.method == SolverMethod.SLSQP
        assert config.max_iterations == 500
        assert config.lambda_data == 1.0
        assert config.lambda_entropy == 0.1
        assert config.lambda_temporal == 0.01
        assert config.lambda_physics == 10.0
        assert config.state_lower_bound == 0.0
        assert config.state_upper_bound == 1.5

    def test_custom(self):
        config = SolverConfig(
            method=SolverMethod.TRUST_CONSTR,
            lambda_entropy=0.2,
            max_iterations=1000,
        )
        assert config.method == SolverMethod.TRUST_CONSTR
        assert config.lambda_entropy == 0.2
        assert config.max_iterations == 1000


class TestSolverResult:
    """Test SolverResult dataclass."""

    def test_creation(self):
        x = np.array([0.5, 0.3, 0.8])
        result = SolverResult(
            x=x,
            success=True,
            message="Converged",
            iterations=50,
            objective_value=0.01,
            data_term=0.005,
            entropy_term=0.003,
            temporal_term=0.001,
            physics_term=0.001,
            sparsity_term=0.0,
            gradient_norm=0.001,
            constraint_violation=0.0,
            boundary_residual=0.05,
        )
        assert result.success
        assert result.iterations == 50
        assert "SolverResult" in str(result)
        assert "success=True" in str(result)


class TestHolographicSolver:
    """Test HolographicSolver class."""

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
        self.topo.add_causal_edge(CausalEdge(
            source="svc_a",
            target="svc_b",
            latency_ms=5.0
        ))

        # Build measurement system
        timeline = [
            {"event_id": "1", "timestamp_ns": 100_000_000, "source_type": "jsonl_log", "message": "High CPU",
             "attributes": {"service": "svc_a", "cpu_usage": 0.8}, "status": "warning"},
            {"event_id": "2", "timestamp_ns": 200_000_000, "source_type": "csv_metrics", "message": "Metric",
             "attributes": {"service": "svc_a", "cpu_usage": 0.7}, "status": "ok"},
            {"event_id": "3", "timestamp_ns": 300_000_000, "source_type": "jsonl_log", "message": "Normal CPU",
             "attributes": {"service": "svc_b", "cpu_usage": 0.3}, "status": "ok"},
        ]
        heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)

        kernel_builder = CausalKernelBuilder(self.topo)
        kernel_builder.build_all_kernels()

        self.measurement_system = build_measurement_system(
            self.topo, heus, 1_000_000_000, kernel_builder, MeasurementConfig()
        )

    def test_solver_creation(self):
        solver = HolographicSolver(self.measurement_system, self.topo)
        assert solver.n_state == self.measurement_system.n_state
        assert solver.M.shape == self.measurement_system.M.shape

    def test_solve_basic(self):
        config = SolverConfig(max_iterations=100, lambda_entropy=0.1)
        solver = HolographicSolver(self.measurement_system, self.topo, config)
        result = solver.solve()

        assert isinstance(result, SolverResult)
        assert result.x.shape == (solver.n_state,)
        assert np.all(result.x >= config.state_lower_bound - 1e-6)
        assert np.all(result.x <= config.state_upper_bound + 1e-6)
        # Should complete (even if not fully converged)
        assert result.iterations >= 0

    def test_solve_with_prior(self):
        config = SolverConfig(max_iterations=100)
        solver = HolographicSolver(self.measurement_system, self.topo, config)

        x_prior = np.full(solver.n_state, 0.5)
        solver.set_prior(x_prior)
        result = solver.solve()

        assert result.success or result.iterations > 0  # Should run

    def test_solve_different_methods(self):
        for method in [SolverMethod.L_BFGS_B, SolverMethod.SLSQP]:
            config = SolverConfig(method=method, max_iterations=50)
            solver = HolographicSolver(self.measurement_system, self.topo, config)
            result = solver.solve()
            assert result is not None

    def test_solve_empty_system(self):
        empty_topo = SystemTopology()
        empty_topo.add_component(ComponentInfo(name="svc_a"))

        from cauveris.holographic.measurement import MeasurementSystem
        empty_system = MeasurementSystem(
            M=sp.csr_matrix((0, 0)),
            b=np.array([]),
            state_dims=[],
            measurements=[],
            n_state=0,
            n_obs=0,
        )

        solver = HolographicSolver(empty_system, empty_topo)
        result = solver.solve()

        assert not result.success
        assert "Empty state" in result.message

    def test_objective_components(self):
        config = SolverConfig(max_iterations=50)
        solver = HolographicSolver(self.measurement_system, self.topo, config)

        # Test objective at zero
        x_zero = np.zeros(solver.n_state)

        # Data term should be ||b||^2 at x=0
        data_at_zero = solver._data_term(x_zero)
        b_norm_sq = np.sum(self.measurement_system.b ** 2)
        assert abs(data_at_zero - b_norm_sq) < 1e-6

        # Entropy at zero should be log(n_state) (uniform distribution has max entropy)
        entropy_at_zero = solver._entropy_term(x_zero)
        assert abs(entropy_at_zero - np.log(solver.n_state)) < 1e-6

    def test_gradient(self):
        config = SolverConfig(max_iterations=50)
        solver = HolographicSolver(self.measurement_system, self.topo, config)

        x = np.ones(solver.n_state) * 0.5
        grad = solver._gradient(x)

        assert grad.shape == (solver.n_state,)
        assert np.all(np.isfinite(grad))

    def test_decode_state(self):
        config = SolverConfig(max_iterations=50)
        solver = HolographicSolver(self.measurement_system, self.topo, config)
        result = solver.solve()

        decoded = solver.decode_state(result.x)
        assert "services" in decoded
        assert "svc_a" in decoded["services"] or "svc_b" in decoded["services"]

        svc_a_state = decoded["services"].get("svc_a", {})
        # Should have the basic dimensions
        assert "cpu_pressure" in svc_a_state


class TestSolveHolographicInverse:
    """Test convenience function."""

    def test_solve(self):
        topo = SystemTopology()
        topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(), boundary_layers=["application_log"]))

        timeline = [
            {"event_id": "1", "timestamp_ns": 100_000_000, "source_type": "jsonl_log", "message": "Test",
             "attributes": {"service": "svc_a", "cpu_usage": 0.5}, "status": "ok"},
        ]
        heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)

        kernel_builder = CausalKernelBuilder(topo)
        kernel_builder.build_all_kernels()

        system = build_measurement_system(topo, heus, 1_000_000_000, kernel_builder)

        result = solve_holographic_inverse(system, topo, SolverConfig(max_iterations=50))
        assert isinstance(result, SolverResult)
        assert result.x.shape == (system.n_state,)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

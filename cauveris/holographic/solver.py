"""
Holographic Inverse Solver - Constrained optimization for bulk reconstruction.

Implements the convex optimization problem:
    min_x ||M·x - b||² + λ_entropy·S(x) + λ_temporal·||x - x_prior||² + λ_physics·||C(x)||²

With entropy regularization encouraging sparse, structured solutions
consistent with holographic principle.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.optimize as opt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

from .measurement import MeasurementSystem
from .topology import SystemTopology, ComponentInfo, CausalEdge


class SolverMethod(Enum):
    """Optimization method."""
    L_BFGS_B = "L-BFGS-B"        # Constrained quasi-Newton
    TRUST_CONSTR = "trust-constr" # Trust region with constraints
    SLSQP = "SLSQP"               # Sequential least squares
    ADMM = "admm"                 # ADMM for large sparse systems


@dataclass(slots=True)
class SolverConfig:
    """Configuration for holographic inverse solver."""
    method: SolverMethod = SolverMethod.SLSQP
    max_iterations: int = 500
    tolerance: float = 1e-6
    ftol: float = 1e-9

    # Regularization weights
    lambda_data: float = 1.0         # Data fidelity weight (||Mx - b||²)
    lambda_entropy: float = 0.1      # Holographic entropy weight
    lambda_temporal: float = 0.01    # Temporal continuity weight (||x - x_prior||²)
    lambda_physics: float = 10.0     # Physics constraint weight
    lambda_sparsity: float = 0.01    # L1 sparsity weight

    # Bounds
    state_lower_bound: float = 0.0
    state_upper_bound: float = 1.5   # Allow slight overshoot for pressure

    # Convergence
    verbose: bool = False
    track_history: bool = False

    # Physics constraints
    enforce_monotonic: bool = True    # Pressure should not decrease without reason
    enforce_capacity: bool = True     # Pressure <= capacity limits
    enforce_causality: bool = True    # Causal ordering constraints


@dataclass(slots=True)
class SolverResult:
    """Result of holographic inverse solve."""
    x: np.ndarray                      # Optimized state vector
    success: bool
    message: str
    iterations: int
    objective_value: float

    # Objective components at solution
    data_term: float
    entropy_term: float
    temporal_term: float
    physics_term: float
    sparsity_term: float

    # Convergence info
    gradient_norm: float
    constraint_violation: float
    boundary_residual: float          # ||M·x - b|| / ||b||

    # History (if track_history=True)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        return (f"SolverResult(success={self.success}, iter={self.iterations}, "
                f"obj={self.objective_value:.6f}, ||Mx-b||/||b||={self.boundary_residual:.4f})")


class HolographicSolver:
    """
    Holographic inverse problem solver with entropy regularization.

    Solves for the bulk state vector x that best explains boundary
    observations b through measurement operator M.
    """

    def __init__(
        self,
        measurement_system: MeasurementSystem,
        topology: SystemTopology,
        config: Optional[SolverConfig] = None,
    ):
        self.system = measurement_system
        self.topology = topology
        self.config = config or SolverConfig()
        self.n_state = measurement_system.n_state
        self.M = measurement_system.M
        self.b = measurement_system.b
        self.state_dims = measurement_system.state_dims

        # Precompute constraint matrices
        self._build_constraint_matrices()

        # Prior state (for temporal continuity)
        self.x_prior: Optional[np.ndarray] = None

    def _build_constraint_matrices(self) -> None:
        """Build constraint matrices for physics and structure."""
        n = self.n_state

        # Physics constraints: C_phys · x >= 0 (inequality constraints)
        # e.g., pressure >= 0, pressure <= capacity, causal ordering
        self.C_phys = None
        self.c_phys = None

        # Sparsity pattern for structured regularization
        self.sparsity_weights = np.ones(n, dtype=np.float32)

    def set_prior(self, x_prior: np.ndarray) -> None:
        """Set prior state for temporal continuity regularization."""
        assert x_prior.shape == (self.n_state,), f"Prior shape mismatch: {x_prior.shape} vs {self.n_state}"
        self.x_prior = x_prior.astype(np.float32)

    def solve(self) -> SolverResult:
        """Solve the holographic inverse problem."""
        if self.n_state == 0:
            return SolverResult(
                x=np.array([]),
                success=False,
                message="Empty state vector",
                iterations=0,
                objective_value=0.0,
                data_term=0.0,
                entropy_term=0.0,
                temporal_term=0.0,
                physics_term=0.0,
                sparsity_term=0.0,
                gradient_norm=0.0,
                constraint_violation=0.0,
                boundary_residual=0.0,
            )

        # Initial guess: weighted least squares solution
        x0 = self._initial_guess().astype(np.float64)

        # Bounds (use float64 for SLSQP)
        bounds = [(float(self.config.state_lower_bound), float(self.config.state_upper_bound))] * self.n_state

        # Objective function (float64 -> float64)
        def objective(x: np.ndarray) -> float:
            return float(self._objective(x.astype(np.float32)))

        def gradient(x: np.ndarray) -> np.ndarray:
            return self._gradient(x.astype(np.float32)).astype(np.float64)

        # Constraints
        constraints = self._build_constraints()

        # Run optimizer
        if self.config.method == SolverMethod.L_BFGS_B:
            result = opt.minimize(
                objective, x0, method='L-BFGS-B',
                jac=gradient,
                bounds=bounds,
                options={
                    'maxiter': self.config.max_iterations,
                    'ftol': self.config.ftol,
                    'gtol': self.config.tolerance,
                }
            )
        elif self.config.method == SolverMethod.TRUST_CONSTR:
            result = opt.minimize(
                objective, x0, method='trust-constr',
                jac=gradient,
                bounds=bounds,
                constraints=constraints,
                options={
                    'maxiter': self.config.max_iterations,
                    'gtol': self.config.tolerance,
                    'verbose': 2 if self.config.verbose else 0,
                }
            )
        elif self.config.method == SolverMethod.SLSQP:
            result = opt.minimize(
                objective, x0, method='SLSQP',
                jac=gradient,
                bounds=bounds,
                constraints=constraints,
                options={
                    'maxiter': self.config.max_iterations,
                    'ftol': self.config.ftol,
                }
            )
        elif self.config.method == SolverMethod.ADMM:
            # ADMM not yet implemented, fallback to SLSQP for now
            result = opt.minimize(
                objective, x0, method='SLSQP',
                jac=gradient,
                bounds=bounds,
                constraints=constraints,
                options={
                    'maxiter': self.config.max_iterations,
                    'ftol': self.config.ftol,
                }
            )
        else:
            # Fallback to SLSQP
            result = opt.minimize(
                objective, x0, method='SLSQP',
                jac=gradient,
                bounds=bounds,
                constraints=constraints,
                options={
                    'maxiter': self.config.max_iterations,
                    'ftol': self.config.ftol,
                }
            )

        # Compute final objective components (convert back to float32)
        x_opt = result.x.astype(np.float32)
        data_term = self._data_term(x_opt)
        entropy_term = self._entropy_term(x_opt)
        temporal_term = self._temporal_term(x_opt)
        physics_term = self._physics_term(x_opt)
        sparsity_term = self._sparsity_term(x_opt)

        boundary_residual = self._boundary_residual(x_opt)
        constraint_viol = self._constraint_violation(x_opt)

        return SolverResult(
            x=x_opt,
            success=result.success,
            message=str(result.message),
            iterations=result.nit if hasattr(result, 'nit') else 0,
            objective_value=result.fun,
            data_term=data_term,
            entropy_term=entropy_term,
            temporal_term=temporal_term,
            physics_term=physics_term,
            sparsity_term=sparsity_term,
            gradient_norm=np.linalg.norm(gradient(x_opt)),
            constraint_violation=constraint_viol,
            boundary_residual=boundary_residual,
        )

    def _initial_guess(self) -> np.ndarray:
        """Compute initial guess from weighted least squares."""
        # x0 = (M^T W M)^{-1} M^T W b  (weighted by observation precision)
        if self.n_state == 0 or self.M.shape[0] == 0:
            return np.zeros(self.n_state, dtype=np.float32)

        # Use observation scales as weights
        w_obs = np.array([self.system.obs_scales.get(i, 1.0) for i in range(self.M.shape[0])])
        W = sp.diags(w_obs)

        # Scaled least squares: M^T W M x = M^T W b
        MTW = self.M.T @ W
        A = MTW @ self.M
        rhs = MTW @ self.b

        # Add small diagonal for stability
        A = A + sp.eye(self.n_state) * 1e-6

        try:
            x0 = sp.linalg.spsolve(A, rhs)
            return np.clip(x0, self.config.state_lower_bound, self.config.state_upper_bound).astype(np.float32)
        except Exception:
            return np.zeros(self.n_state, dtype=np.float32)

    def _objective(self, x: np.ndarray) -> float:
        """Full objective function."""
        obj = (
            self.config.lambda_data * self._data_term(x) +
            self.config.lambda_entropy * self._entropy_term(x) +
            self.config.lambda_temporal * self._temporal_term(x) +
            self.config.lambda_physics * self._physics_term(x) +
            self.config.lambda_sparsity * self._sparsity_term(x)
        )
        return float(obj)

    def _gradient(self, x: np.ndarray) -> np.ndarray:
        """Gradient of full objective."""
        grad = (
            self.config.lambda_data * self._data_gradient(x) +
            self.config.lambda_entropy * self._entropy_gradient(x) +
            self.config.lambda_temporal * self._temporal_gradient(x) +
            self.config.lambda_physics * self._physics_gradient(x) +
            self.config.lambda_sparsity * self._sparsity_gradient(x)
        )
        return grad.astype(np.float32)

    def _data_term(self, x: np.ndarray) -> float:
        """Data fidelity: ||M·x - b||²"""
        residual = self.M @ x - self.b
        return float(np.sum(residual ** 2))

    def _data_gradient(self, x: np.ndarray) -> np.ndarray:
        """Gradient of data term: 2 M^T (M x - b)"""
        residual = self.M @ x - self.b
        return (2.0 * self.M.T @ residual).astype(np.float32)

    def _entropy_term(self, x: np.ndarray) -> float:
        """
        Holographic entropy regularization.

        Encourages solutions with structure similar to holographic encoding:
        - Sparse but not too sparse (like hologram pixels)
        - Smooth in regions, sharp at boundaries
        """
        # Shift to positive for entropy
        x_pos = np.maximum(x, 1e-10)

        # Normalize to probability distribution
        total = np.sum(x_pos)
        if total > 0:
            p = x_pos / total
            # Shannon entropy (negative for minimization: -S = Σ p log p)
            entropy = -np.sum(p * np.log(p + 1e-12))
            return float(entropy)

        return 0.0

    def _entropy_gradient(self, x: np.ndarray) -> np.ndarray:
        """Gradient of entropy term."""
        x_pos = np.maximum(x, 1e-10)
        total = np.sum(x_pos)
        if total == 0:
            return np.zeros_like(x)

        p = x_pos / total
        # d/dx (-Σ p_i log p_i) where p = x/Σx
        # = -(log p + 1) / Σx + (Σ p log p) / (Σx)²
        # = -(log(x/Σx) + 1)/Σx + entropy/Σx
        entropy = -np.sum(p * np.log(p + 1e-12))

        grad = (-(np.log(p + 1e-12) + 1) / total + entropy / (total * total))

        # Only gradient where x > 0
        grad[x <= 1e-10] = 0.0

        return grad.astype(np.float32)

    def _temporal_term(self, x: np.ndarray) -> float:
        """Temporal continuity: ||x - x_prior||²"""
        if self.x_prior is None:
            return 0.0
        diff = x - self.x_prior
        return float(np.sum(diff ** 2))

    def _temporal_gradient(self, x: np.ndarray) -> np.ndarray:
        """Gradient of temporal term."""
        if self.x_prior is None:
            return np.zeros_like(x)
        return (2.0 * (x - self.x_prior)).astype(np.float32)

    def _physics_term(self, x: np.ndarray) -> float:
        """
        Physics constraints as soft penalties.

        Hard constraints:
        - x >= 0 (already enforced by bounds)
        - Causal ordering: if A causes B, peak(A) <= peak(B)
        - Capacity: pressure <= capacity
        """
        penalty = 0.0

        if self.config.enforce_capacity:
            # Capacity constraints: pressure should not exceed 1.5 (with some headroom)
            for i, sd in enumerate(self.state_dims):
                if "pressure" in sd.dimension and x[i] > 1.5:
                    penalty += (x[i] - 1.5) ** 2 * 100.0

        if self.config.enforce_causality:
            # Causal ordering: source component pressure should not be << target pressure
            for edge in self.topology.causal_edges:
                src_idx = self.system.get_state_slice(edge.source, "cpu_pressure")
                dst_idx = self.system.get_state_slice(edge.target, "cpu_pressure")
                if len(src_idx) > 0 and len(dst_idx) > 0:
                    # If downstream has high pressure, upstream should have at least some
                    src_press = x[src_idx[0]]
                    dst_press = x[dst_idx[0]]
                    if dst_press > 0.8 and src_press < 0.3:
                        penalty += (0.3 - src_press) ** 2 * 10.0

        return penalty

    def _physics_gradient(self, x: np.ndarray) -> np.ndarray:
        """Gradient of physics penalty."""
        grad = np.zeros_like(x)

        if self.config.enforce_capacity:
            for i, sd in enumerate(self.state_dims):
                if "pressure" in sd.dimension and x[i] > 1.5:
                    grad[i] += 200.0 * (x[i] - 1.5)

        if self.config.enforce_causality:
            for edge in self.topology.causal_edges:
                src_idx = self.system.get_state_slice(edge.source, "cpu_pressure")
                dst_idx = self.system.get_state_slice(edge.target, "cpu_pressure")
                if len(src_idx) > 0 and len(dst_idx) > 0:
                    src_press = x[src_idx[0]]
                    dst_press = x[dst_idx[0]]
                    if dst_press > 0.8 and src_press < 0.3:
                        grad[src_idx[0]] -= 20.0 * (0.3 - src_press)
                        grad[dst_idx[0]] += 20.0 * (0.3 - src_press)

        return grad.astype(np.float32)

    def _sparsity_term(self, x: np.ndarray) -> float:
        """L1 sparsity regularization."""
        return float(np.sum(np.abs(x)))

    def _sparsity_gradient(self, x: np.ndarray) -> np.ndarray:
        """Gradient of L1 term (subgradient)."""
        # Subgradient: sign(x) for x != 0, [-1, 1] for x = 0
        # We use smoothed sign: x / sqrt(x² + ε)
        eps = 1e-6
        return (x / np.sqrt(x ** 2 + eps)).astype(np.float32)

    def _build_constraints(self) -> List[dict]:
        """Build constraints for trust-constr/SLSQP."""
        constraints = []

        # Capacity constraints: pressure <= limit
        if self.config.enforce_capacity:
            for i, sd in enumerate(self.state_dims):
                if "pressure" in sd.dimension:
                    # x[i] <= 1.5
                    constraints.append({
                        'type': 'ineq',
                        'fun': lambda x, idx=i: 1.5 - x[idx]
                    })

        return constraints

    def _boundary_residual(self, x: np.ndarray) -> float:
        """Relative boundary residual: ||M·x - b|| / ||b||"""
        if self.b.size == 0:
            return 0.0
        residual = self.M @ x - self.b
        return float(np.linalg.norm(residual) / (np.linalg.norm(self.b) + 1e-12))

    def _constraint_violation(self, x: np.ndarray) -> float:
        """Total constraint violation."""
        viol = 0.0

        if self.config.enforce_capacity:
            for i, sd in enumerate(self.state_dims):
                if "pressure" in sd.dimension and x[i] > 1.5:
                    viol += (x[i] - 1.5) ** 2

        if self.config.enforce_causality:
            for edge in self.topology.causal_edges:
                src_idx = self.system.get_state_slice(edge.source, "cpu_pressure")
                dst_idx = self.system.get_state_slice(edge.target, "cpu_pressure")
                if len(src_idx) > 0 and len(dst_idx) > 0:
                    src_press = x[src_idx[0]]
                    dst_press = x[dst_idx[0]]
                    if dst_press > 0.8 and src_press < 0.3:
                        viol += (0.3 - src_press) ** 2

        return viol

    def decode_state(self, x: np.ndarray) -> Dict[str, Any]:
        """
        Decode optimized state vector to structured reconstruction.

        Returns:
            Dict with component states, network, resources
        """
        result = {
            "services": {},
            "network": {},
            "resources": {},
            "ambiguity": [],
        }

        # Per-component state
        for sd in self.state_dims:
            comp = sd.component
            dim = sd.dimension
            val = float(np.clip(x[sd.index], 0, 1.5))

            if comp not in result["services"]:
                result["services"][comp] = {
                    "cpu_pressure": 0.0,
                    "memory_pressure": 0.0,
                    "network_latency": 0.0,
                    "error_rate": 0.0,
                    "config_change": 0.0,
                    "deployment_activity": 0.0,
                    "resource_contention": 0.0,
                    "service_dependency": 0.0,
                }

            if dim in result["services"][comp]:
                result["services"][comp][dim] = val

        return result


def solve_holographic_inverse(
    measurement_system: MeasurementSystem,
    topology: SystemTopology,
    config: Optional[SolverConfig] = None,
    x_prior: Optional[np.ndarray] = None,
) -> SolverResult:
    """
    Convenience function to solve holographic inverse problem.

    Args:
        measurement_system: Built measurement system
        topology: System topology
        config: Solver configuration
        x_prior: Prior state for temporal continuity

    Returns:
        SolverResult with optimized state
    """
    solver = HolographicSolver(measurement_system, topology, config)
    if x_prior is not None:
        solver.set_prior(x_prior)
    return solver.solve()


if __name__ == "__main__":
    # Quick test
    from .topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge
    from .heu import convert_timeline_to_heus
    from .heu_kernel import CausalKernelBuilder
    from .measurement import build_measurement_system

    topo = SystemTopology()
    topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(cpu_cores=4.0), boundary_layers=["application_log", "metrics_export"]))
    topo.add_component(ComponentInfo(name="svc_b", capacity=ResourceCapacity(cpu_cores=2.0), boundary_layers=["application_log", "metrics_export"]))
    topo.add_causal_edge(CausalEdge(source="svc_a", target="svc_b", latency_ms=5.0))

    timeline = [
        {"event_id": "1", "timestamp_ns": 100_000_000, "source_type": "jsonl_log", "message": "High CPU",
         "attributes": {"service": "svc_a", "cpu_usage": 0.8}, "status": "warning"},
        {"event_id": "2", "timestamp_ns": 200_000_000, "source_type": "csv_metrics", "message": "Metric",
         "attributes": {"service": "svc_a", "cpu_usage": 0.7}, "status": "ok"},
    ]
    heus = convert_timeline_to_heus(timeline, {}, 1_000_000_000)

    kernel_builder = CausalKernelBuilder(topo)
    kernel_builder.build_all_kernels()

    system = build_measurement_system(topo, heus, 1_000_000_000, kernel_builder)
    print(f"Measurement system: {system.n_obs} obs, {system.n_state} state dims")

    solver = HolographicSolver(system, topo)
    result = solver.solve()
    print(f"Solver: {result}")
    print(f"State shape: {result.x.shape}")
    print(f"Decoded: {solver.decode_state(result.x)}")

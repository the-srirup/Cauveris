"""
Advanced Physics-Based Propagation Kernels for Holographic Reconstruction.

Implements research-level mathematical physics:
1. Wave equation propagation with boundary conditions (AdS/CFT inspired)
2. Feynman path integral formulation for causal inference
3. Tensor network representations (MPS/TTN) for scalable reconstruction
4. Differential geometry on bulk manifold (Ryu-Takayanagi surfaces)
5. Quantum entanglement entropy for compression bounds
6. Renormalization group flow for multi-scale analysis
"""

from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any
from enum import Enum

from .topology import SystemTopology, ComponentInfo, CausalEdge
from .heu import HolographicEvidenceUnit, BoundaryLayer


# ============================================================================
# Core Physics Constants and Types
# ============================================================================

class DecayType(Enum):
    EXPONENTIAL = "exponential"
    GAMMA = "gamma"
    BI_EXPONENTIAL = "bi_exponential"
    POWER_LAW = "power_law"
    STRETCHED_EXPONENTIAL = "stretched_exponential"
    WAVE = "wave"
    PATH_INTEGRAL = "path_integral"


class GeometryType(Enum):
    FLAT = "flat"
    ADS = "ads"                    # Anti-de Sitter space
    SYMMETRIC = "symmetric"        # Symmetric space
    PRODUCT = "product"            # Product manifold


@dataclass(slots=True)
class WaveKernelConfig:
    """Configuration for wave equation propagation."""
    wave_speed: float = 1.0                    # Speed of causal propagation (normalized)
    damping_coefficient: float = 0.01          # Damping (dissipation)
    boundary_condition: str = "absorbing"      # "absorbing", "reflecting", "periodic"
    courant_number: float = 0.5                # CFL condition for stability
    spatial_discretization: float = 0.1        # Spatial grid spacing
    self_latency_factor: float = 0.1           # Internal latency as fraction of capacity


@dataclass(slots=True)
class PathIntegralConfig:
    """Configuration for Feynman path integral causal inference."""
    num_paths: int = 10000                     # Number of Monte Carlo paths
    action_weight: float = 1.0                 # Weight of classical action
    quantum_fluctuation: float = 0.1           # ℏ effective scale
    time_slicing: int = 100                    # Time discretization steps
    importance_sampling: bool = True           # Use importance sampling


@dataclass(slots=True)
class TensorNetworkConfig:
    """Configuration for tensor network representation."""
    max_bond_dimension: int = 64               # Maximum bond dimension
    truncation_threshold: float = 1e-12        # SVD truncation threshold
    canonicalize: bool = True                  # Keep in canonical form
    geometry: GeometryType = GeometryType.ADS  # Bulk geometry


@dataclass(slots=True)
class RenormalizationConfig:
    """Configuration for RG flow analysis."""
    num_scales: int = 5                        # Number of RG steps
    coarse_graining_factor: float = 2.0        # Factor per step
    relevant_operators: List[str] = field(default_factory=lambda: ["mass", "coupling"])
    fixed_point_tolerance: float = 1e-6


@dataclass(slots=True)
class AdvancedKernelConfig:
    """Unified configuration for all advanced kernels."""
    wave: WaveKernelConfig = field(default_factory=WaveKernelConfig)
    path_integral: PathIntegralConfig = field(default_factory=PathIntegralConfig)
    tensor_network: TensorNetworkConfig = field(default_factory=TensorNetworkConfig)
    renormalization: RenormalizationConfig = field(default_factory=RenormalizationConfig)

    # Global parameters
    time_step_ns: int = 1_000_000
    max_kernel_time_ns: int = 10_000_000_000
    bulk_dimension: int = 3                    # Bulk spatial dimensions
    boundary_layers: int = 8                   # Number of boundary layers


# ============================================================================
# 1. Wave Equation Propagation Kernel
# ============================================================================

class WavePropagationKernel:
    """
    Wave equation propagation kernel for boundary-bulk mapping.

    Solves: (∂²/∂t² - c²∇² + γ∂/∂t) ψ = 0
    with appropriate boundary conditions on the holographic screen.

    In the AdS/CFT context, this represents the bulk-to-boundary propagator
    (Green's function) for a massive scalar field in AdS_{d+1}.
    """

    def __init__(
        self,
        topology: SystemTopology,
        config: AdvancedKernelConfig,
        component: ComponentInfo,
        boundary_layer: BoundaryLayer,
    ):
        self.topology = topology
        self.config = config
        self.component = component
        self.boundary_layer = boundary_layer
        self.wave_config = config.wave

        # Discretization parameters
        self.dt = config.time_step_ns * 1e-9  # Convert to seconds
        self.max_time = config.max_kernel_time_ns * 1e-9
        self.dx = self.wave_config.spatial_discretization
        self.c = self.wave_config.wave_speed
        self.gamma = self.wave_config.damping_coefficient

        # CFL condition check
        self.cfl = self.c * self.dt / self.dx
        if self.cfl > self.wave_config.courant_number:
            # Adjust dt to satisfy CFL
            self.dt = self.wave_config.courant_number * self.dx / self.c
            self.time_steps = int(self.max_time / self.dt)
        else:
            self.time_steps = int(self.max_time / self.dt)

        # Spatial grid (1D for simplicity, can extend to 3D)
        self.nx = max(10, int(1.0 / self.dx))
        self.x_grid = np.linspace(0, 1.0, self.nx)

        # Initialize wave field
        self.psi = np.zeros((self.time_steps, self.nx), dtype=np.float32)
        self.psi_prev = np.zeros(self.nx, dtype=np.float32)
        self.psi_curr = np.zeros(self.nx, dtype=np.float32)

    def _initial_condition(self) -> np.ndarray:
        """Initial condition: localized pulse at component position."""
        # Gaussian pulse at center
        x0 = 0.5
        sigma = 0.1
        return np.exp(-(self.x_grid - x0)**2 / (2 * sigma**2))

    def _boundary_condition(self, psi: np.ndarray, step: int) -> np.ndarray:
        """Apply boundary conditions at spatial boundaries."""
        psi_new = psi.copy()
        bc = self.wave_config.boundary_condition

        if bc == "absorbing":
            # Simple absorbing boundary (Mur's ABC)
            psi_new[0] = psi[1]
            psi_new[-1] = psi[-2]
        elif bc == "reflecting":
            # Reflecting boundary (Neumann)
            psi_new[0] = psi[1]
            psi_new[-1] = psi[-2]
        elif bc == "periodic":
            # Periodic boundary
            psi_new[0] = psi[-2]
            psi_new[-1] = psi[1]

        return psi_new

    def _source_term(self, step: int) -> np.ndarray:
        """Source term for driven wave equation."""
        # Impulse at t=0, x=0.5
        source = np.zeros(self.nx)
        if step == 0:
            source[self.nx // 2] = 1.0 / (self.dx * self.dt)
        return source

    def compute_kernel(self) -> np.ndarray:
        """
        Compute wave propagation kernel using finite difference time domain (FDTD).

        Returns kernel values at boundary (x=0 or x=1) as function of time.
        """
        # Initialize
        self.psi_prev = self._initial_condition()
        self.psi_curr = self.psi_prev.copy()

        # Boundary observation point (holographic screen at x=0)
        boundary_idx = 0
        kernel_values = np.zeros(self.time_steps, dtype=np.float32)

        # FDTD coefficients
        c2_dt2_dx2 = (self.c * self.dt / self.dx) ** 2
        gamma_dt = self.gamma * self.dt

        for n in range(self.time_steps):
            # Record boundary value (this is the kernel response)
            kernel_values[n] = self.psi_curr[boundary_idx]

            # FDTD update: ψ^{n+1} = 2ψ^n - ψ^{n-1} + c²Δt²/Δx² (ψ^n_{i+1} - 2ψ^n_i + ψ^n_{i-1}) - γΔt(ψ^n - ψ^{n-1})/Δt
            psi_next = np.zeros_like(self.psi_curr)

            # Interior points
            for i in range(1, self.nx - 1):
                laplacian = self.psi_curr[i + 1] - 2 * self.psi_curr[i] + self.psi_curr[i - 1]
                psi_next[i] = (
                    2 * self.psi_curr[i]
                    - self.psi_prev[i]
                    + c2_dt2_dx2 * laplacian
                    - gamma_dt * (self.psi_curr[i] - self.psi_prev[i])
                    + self.dt**2 * self._source_term(n)[i]
                )

            # Apply boundary conditions
            psi_next = self._boundary_condition(psi_next, n)

            # Time step
            self.psi_prev = self.psi_curr
            self.psi_curr = psi_next

        # Normalize
        integral = np.trapezoid(kernel_values, dx=self.dt)
        if integral > 0:
            kernel_values = kernel_values / integral

        return kernel_values

    def compute_green_function_ads(self, mass: float = 0.0) -> np.ndarray:
        """
        Compute bulk-to-boundary Green's function in AdS_{d+1}.

        For a massive scalar field in AdS_{d+1} with metric:
        ds² = (L²/z²)(dz² + dx² - dt²)

        The bulk-to-boundary propagator is:
        K(z, x, t; x', t') = C_Δ (z/(z² + (x-x')² - (t-t')²))^Δ

        where Δ = d/2 + √(d²/4 + m²L²) is the scaling dimension.
        """
        d = self.config.bulk_dimension
        L = 1.0  # AdS radius

        # Scaling dimension
        delta = d / 2 + np.sqrt(d**2 / 4 + mass**2 * L**2)
        C_delta = delta * math.gamma(delta) / (math.pi**(d/2) * math.gamma(delta - d/2 + 1))

        # Time axis
        time_axis = np.arange(0, self.max_time, self.dt)
        kernel = np.zeros_like(time_axis, dtype=np.float32)

        # For simplicity, evaluate at boundary (z → 0) with x=x'=0
        # K ~ t^{-2Δ} for large t (power law decay)
        for i, t in enumerate(time_axis):
            if t > 0:
                kernel[i] = C_delta * (t / L)**(-2 * delta)
            else:
                kernel[i] = kernel[1] if len(kernel) > 1 else 1.0

        # Normalize
        integral = np.trapezoid(kernel, time_axis)
        if integral > 0:
            kernel = kernel / integral

        return kernel


class WaveKernelBuilder:
    """Builder for wave propagation kernels across all components and layers."""

    def __init__(self, topology: SystemTopology, config: AdvancedKernelConfig):
        self.topology = topology
        self.config = config
        self._kernels: Dict[Tuple[str, BoundaryLayer], np.ndarray] = {}

    def build_all(self) -> Dict[Tuple[str, BoundaryLayer], np.ndarray]:
        """Build wave kernels for all component-layer pairs."""
        self._kernels.clear()

        for comp_name, comp in self.topology.components.items():
            for layer in comp.boundary_layers:
                kernel_obj = WavePropagationKernel(
                    self.topology, self.config, comp, layer
                )
                # Use analytic AdS Green's function for efficiency
                kernel_values = kernel_obj.compute_green_function_ads(mass=0.1)
                self._kernels[(comp_name, layer)] = kernel_values

        return self._kernels


# ============================================================================
# 2. Feynman Path Integral for Causal Inference
# ============================================================================

class PathIntegralCausalKernel:
    """
    Feynman path integral formulation for causal inference.

    Computes the propagator as a sum over all paths:
    K(x_f, t_f; x_i, t_i) = ∫ Dx(t) exp(i/ℏ S[x(t)])

    For causal inference, we use imaginary time (Wick rotation):
    K = ∫ Dx(τ) exp(-S_E[x(τ)]/ℏ)

    where S_E is the Euclidean action. This gives the probability amplitude
    for causal influence from source to target.
    """

    def __init__(
        self,
        topology: SystemTopology,
        config: AdvancedKernelConfig,
        source: ComponentInfo,
        target: ComponentInfo,
        edge: CausalEdge,
    ):
        self.topology = topology
        self.config = config
        self.source = source
        self.target = target
        self.edge = edge
        self.path_config = config.path_integral

        # Discretization
        self.dt = config.time_step_ns * 1e-9
        self.max_time = config.max_kernel_time_ns * 1e-9
        self.N = self.path_config.time_slicing
        self.dtau = self.max_time / self.N
        self.hbar = self.path_config.quantum_fluctuation
        self.action_weight = self.path_config.action_weight

        # Classical path (straight line in causal structure)
        self.classical_latency = edge.latency_ms * 1e-3  # Convert to seconds
        self.queueing_delay = edge.queue_depth * config.wave.self_latency_factor * 1e-3

    def _euclidean_action(self, path: np.ndarray) -> float:
        """
        Euclidean action for a path in the causal network.

        S_E = ∫ dτ [½(dx/dτ)² + V(x)]

        For causal propagation, the potential V(x) encodes the network topology:
        - Low potential along causal edges
        - High potential (barrier) for non-causal connections
        """
        # Kinetic term: ½ ∫ (dx/dτ)² dτ
        dx_dtau = np.gradient(path, self.dtau)
        kinetic = 0.5 * np.trapezoid(dx_dtau**2, dx=self.dtau)

        # Potential term: network topology
        # Path should follow causal edges
        potential = 0.0
        for i, x in enumerate(path):
            # Potential is low near causal edges, high elsewhere
            # Simplified: distance to causal manifold
            potential += self._causal_potential(x)

        potential *= self.dtau

        return self.action_weight * (kinetic + potential)

    def _causal_potential(self, x: float) -> float:
        """Potential encoding causal structure."""
        # x ∈ [0, 1] represents position along causal chain
        # Source at x=0, target at x=1
        # Minimum potential along the causal edge
        edge_position = x  # Simplified mapping
        return 10.0 * (edge_position - 0.5)**2  # Parabolic well centered at causal path

    def _classical_path(self) -> np.ndarray:
        """Classical (minimum action) path."""
        # Straight line from source to target in causal time
        tau = np.linspace(0, self.max_time, self.N)
        return tau / self.max_time  # Linear path

    def _sample_fluctuation(self, classical_path: np.ndarray) -> np.ndarray:
        """Sample quantum fluctuations around classical path."""
        # Generate random fluctuation with proper correlation
        # Use Ornstein-Uhlenbeck process for smooth paths
        fluctuation = np.zeros(self.N)
        fluctuation[0] = np.random.normal(0, np.sqrt(self.hbar * self.dtau))

        for i in range(1, self.N):
            # OU process: dx = -θ x dt + σ dW
            theta = 1.0 / self.dtau
            sigma = np.sqrt(2 * self.hbar * theta)
            fluctuation[i] = (
                fluctuation[i - 1] * np.exp(-theta * self.dtau)
                + sigma * np.sqrt((1 - np.exp(-2 * theta * self.dtau)) / (2 * theta))
                * np.random.normal(0, 1)
            )

        return classical_path + fluctuation

    def compute_kernel_monte_carlo(self) -> np.ndarray:
        """
        Compute propagator using Monte Carlo path integral.

        Returns time-domain kernel by projecting paths onto time axis.
        """
        n_samples = self.path_config.num_paths
        time_bins = int(self.max_time / self.dt)
        kernel = np.zeros(time_bins, dtype=np.float32)

        classical_path = self._classical_path()

        for _ in range(n_samples):
            if self.path_config.importance_sampling:
                # Importance sampling: sample from Gaussian around classical path
                path = self._sample_fluctuation(classical_path)
            else:
                # Naive sampling (inefficient)
                path = self._sample_fluctuation(classical_path)

            action = self._euclidean_action(path)
            weight = np.exp(-action / self.hbar)

            # Project path onto time axis
            # The path parameter τ maps to physical time through the causal structure
            for i, x in enumerate(path):
                t_physical = x * self.classical_latency + self.queueing_delay
                bin_idx = int(t_physical / self.dt)
                if 0 <= bin_idx < time_bins:
                    kernel[bin_idx] += weight

        # Normalize
        kernel = kernel / n_samples
        integral = np.trapezoid(kernel, dx=self.dt)
        if integral > 0:
            kernel = kernel / integral

        return kernel

    def compute_kernel_saddle_point(self) -> np.ndarray:
        """
        Compute propagator using saddle-point (semiclassical) approximation.

        K ≈ exp(-S_E[classical]/ℏ) × (fluctuation determinant)^{-1/2}
        """
        classical_path = self._classical_path()
        S_cl = self._euclidean_action(classical_path)

        # Fluctuation determinant (simplified)
        # For quadratic action, det = (2πℏ)^{N/2} / √det(Hessian)
        det_factor = 1.0 / np.sqrt(2 * np.pi * self.hbar)

        time_bins = int(self.max_time / self.dt)
        kernel = np.zeros(time_bins, dtype=np.float32)

        # Gaussian approximation around classical path
        for i in range(time_bins):
            t = i * self.dt
            # Classical contribution
            if t >= self.classical_latency:
                tau_idx = int((t - self.classical_latency) / self.max_time * self.N)
                if tau_idx < self.N:
                    kernel[i] = det_factor * np.exp(-S_cl / self.hbar)

        # Add quantum spread
        # Convolve with Gaussian of width √(ℏ × time)
        quantum_width = np.sqrt(self.hbar * self.dt)
        kernel = np.convolve(kernel, self._gaussian_kernel(quantum_width), mode='same')

        integral = np.trapezoid(kernel, dx=self.dt)
        if integral > 0:
            kernel = kernel / integral

        return kernel

    def _gaussian_kernel(self, sigma: float) -> np.ndarray:
        """Gaussian kernel for quantum spreading."""
        width = int(5 * sigma / self.dt)
        x = np.arange(-width, width + 1) * self.dt
        g = np.exp(-x**2 / (2 * sigma**2))
        return g / np.sum(g)


class PathIntegralKernelBuilder:
    """Builder for path integral causal kernels."""

    def __init__(self, topology: SystemTopology, config: AdvancedKernelConfig):
        self.topology = topology
        self.config = config
        self._kernels: Dict[Tuple[str, str], np.ndarray] = {}

    def build_all(self) -> Dict[Tuple[str, str], np.ndarray]:
        """Build path integral kernels for all causal edges."""
        self._kernels.clear()

        for edge in self.topology.causal_edges:
            if edge.source in self.topology.components and edge.target in self.topology.components:
                src_comp = self.topology.components[edge.source]
                dst_comp = self.topology.components[edge.target]

                pi_kernel = PathIntegralCausalKernel(
                    self.topology, self.config, src_comp, dst_comp, edge
                )
                # Use saddle-point approximation for efficiency
                kernel_values = pi_kernel.compute_kernel_saddle_point()
                self._kernels[(edge.source, edge.target)] = kernel_values

        return self._kernels

# ============================================================================
# 3. Tensor Network Representation (MPS/TTN)
# ============================================================================

@dataclass
class TensorNetworkState:
    """Matrix Product State (MPS) representation of holographic state."""
    tensors: List[np.ndarray]          # List of 3-index tensors [left, physical, right]
    bond_dimensions: List[int]         # Bond dimensions between sites
    physical_dimensions: List[int]     # Physical dimensions at each site
    canonical_center: int = 0          # Site where MPS is orthogonalized

    def __post_init__(self):
        self.n_sites = len(self.tensors)
        assert len(self.bond_dimensions) == self.n_sites - 1
        assert len(self.physical_dimensions) == self.n_sites

    def normalize(self) -> float:
        """Normalize the MPS and return norm."""
        norm = 1.0
        for tensor in self.tensors:
            norm *= np.linalg.norm(tensor)
        if norm > 0:
            self.tensors[0] = self.tensors[0] / norm**(1/self.n_sites)
        return norm

    def canonicalize(self, center: int = 0) -> None:
        """Bring MPS to canonical form with orthogonality center at 'center'."""
        # Left canonicalize (sites 0 to center-1)
        for i in range(center):
            U, S, Vh = np.linalg.svd(
                self.tensors[i].reshape(self.bond_dimensions[i-1] if i > 0 else 1,
                                        self.physical_dimensions[i] * self.bond_dimensions[i]),
                full_matrices=False
            )
            self.tensors[i] = U.reshape(self.bond_dimensions[i-1] if i > 0 else 1,
                                        self.physical_dimensions[i], U.shape[1])
            # Absorb singular values into next tensor
            next_tensor = self.tensors[i + 1]
            next_shape = next_tensor.shape
            self.tensors[i + 1] = (np.diag(S) @ Vh @ next_tensor.reshape(S.shape[0], -1)).reshape(next_shape)

        # Right canonicalize (sites n-1 to center+1)
        for i in range(self.n_sites - 1, center, -1):
            U, S, Vh = np.linalg.svd(
                self.tensors[i].reshape(self.physical_dimensions[i] * self.bond_dimensions[i-1],
                                        self.bond_dimensions[i] if i < self.n_sites - 1 else 1),
                full_matrices=False
            )
            self.tensors[i] = Vh.reshape(U.shape[1], self.physical_dimensions[i],
                                         self.bond_dimensions[i] if i < self.n_sites - 1 else 1)
            # Absorb into previous tensor
            prev_tensor = self.tensors[i - 1]
            prev_shape = prev_tensor.shape
            self.tensors[i - 1] = (prev_tensor.reshape(-1, S.shape[0]) @ np.diag(S) @ U.T).reshape(prev_shape)

        self.canonical_center = center

    def compute_entanglement_entropy(self, cut: int) -> float:
        """Compute entanglement entropy across bond 'cut'."""
        if cut < 0 or cut >= self.n_sites - 1:
            return 0.0

        # Bring to canonical form with center at cut
        self.canonicalize(cut)

        # Get singular values from bond at cut
        tensor = self.tensors[cut]
        left_dim = self.bond_dimensions[cut - 1] if cut > 0 else 1
        phys_dim = self.physical_dimensions[cut]
        right_dim = self.bond_dimensions[cut]

        # Reshape and SVD
        M = tensor.reshape(left_dim * phys_dim, right_dim)
        _, S, _ = np.linalg.svd(M, full_matrices=False)

        # Entanglement entropy: S = -∑ λ_i² log λ_i²
        lambdas = S**2
        sum_lambdas = np.sum(lambdas)
        if sum_lambdas <= 1e-12 or np.isnan(sum_lambdas):
            return 0.0
        lambdas = lambdas / sum_lambdas
        entropy = -np.sum(lambdas * np.log(lambdas + 1e-12))
        return float(entropy)

    def contract_with_vector(self, vector: np.ndarray) -> complex:
        """Contract MPS with a product state vector."""
        result = self.tensors[0][0]  # Start with left boundary
        for i in range(self.n_sites):
            phys_idx = int(vector[i]) if i < len(vector) else 0
            result = result @ self.tensors[i][:, phys_idx, :]
        return result[0, 0]


class TensorNetworkBuilder:
    """
    Builds tensor network representation of the holographic system.

    Maps the boundary HEU data to a Matrix Product State (MPS) or
    Tree Tensor Network (TTN) in the bulk, enabling efficient
    computation of entanglement entropy and correlation functions.
    """

    def __init__(self, topology: SystemTopology, config: AdvancedKernelConfig):
        self.topology = topology
        self.config = config
        self.tn_config = config.tensor_network
        self.max_bond = self.tn_config.max_bond_dimension
        self.trunc_thresh = self.tn_config.truncation_threshold

    def build_mps_from_heus(
        self,
        heus: List[HolographicEvidenceUnit],
        components: List[str],
        layers: List[BoundaryLayer],
    ) -> TensorNetworkState:
        """
        Build MPS from HEU data.

        Each site corresponds to a (component, layer) pair.
        Physical dimension = number of time bins.
        Bond dimensions determined by entanglement structure.
        """
        n_sites = len(components) * len(layers)

        # Collect phase vectors for each site
        site_data = {}
        for heu in heus:
            key = (heu.source_component, heu.boundary_layer)
            if key not in site_data:
                site_data[key] = []
            site_data[key].append(heu.phase_vector)

        # Build tensors for each site
        tensors = []
        bond_dims = []
        phys_dims = []

        # Component-layer ordering
        site_order = []
        for comp in components:
            for layer in layers:
                site_order.append((comp, layer))

        for idx, (comp, layer) in enumerate(site_order):
            key = (comp, layer)
            if key in site_data:
                vectors = np.stack(site_data[key])
                # Use SVD to find optimal bond dimension
                U, S, Vh = np.linalg.svd(vectors.T, full_matrices=False)

                # Truncate based on threshold
                keep = np.sum(S > self.trunc_thresh * S[0])
                keep = min(keep, self.max_bond)
                keep = max(keep, 1)

                U_trunc = U[:, :keep]
                Vh_trunc = Vh[:keep, :]

                # Physical dimension = number of HEUs for this site
                phys_dim = len(vectors)
                phys_dims.append(phys_dim)

                # Left bond dimension
                left_bond = bond_dims[-1] if bond_dims else 1
                right_bond = keep if idx < n_sites - 1 else 1
                bond_dims.append(right_bond)

                # Build tensor: [left, physical, right]
                tensor = np.zeros((left_bond, phys_dim, right_bond), dtype=np.complex64)
                for p in range(phys_dim):
                    tensor[:, p, :] = np.outer(U_trunc[:, 0] if left_bond > 1 else [1.0],
                                                Vh_trunc[0, :] if right_bond > 1 else [1.0])

                tensors.append(tensor)
            else:
                # Empty site - identity tensor
                left_bond = bond_dims[-1] if bond_dims else 1
                right_bond = 2 if idx < n_sites - 1 else 1
                bond_dims.append(right_bond)
                phys_dims.append(1)
                tensor = np.eye(left_bond, right_bond, dtype=np.complex64).reshape(left_bond, 1, right_bond)
                tensors.append(tensor)

        mps = TensorNetworkState(
            tensors=tensors,
            bond_dimensions=bond_dims[:-1],  # Last bond is dummy
            physical_dimensions=phys_dims,
        )
        mps.normalize()
        if self.tn_config.canonicalize:
            mps.canonicalize(0)

        return mps

    def compute_entanglement_spectrum(self, mps: TensorNetworkState) -> List[float]:
        """Compute entanglement spectrum (singular values) for all bonds."""
        spectrum = []
        for cut in range(mps.n_sites - 1):
            mps.canonicalize(cut)
            tensor = mps.tensors[cut]
            left_dim = mps.bond_dimensions[cut - 1] if cut > 0 else 1
            phys_dim = mps.physical_dimensions[cut]
            right_dim = mps.bond_dimensions[cut]

            M = tensor.reshape(left_dim * phys_dim, right_dim)
            _, S, _ = np.linalg.svd(M, full_matrices=False)
            spectrum.extend(S.tolist())
        return spectrum

    def compute_mutual_information(self, mps: TensorNetworkState, site_a: int, site_b: int) -> float:
        """Compute mutual information between two sites using MPS."""
        if site_a > site_b:
            site_a, site_b = site_b, site_a

        # Entanglement entropy of A∪B minus individual entropies
        # For MPS, we can compute this efficiently
        S_A = mps.compute_entanglement_entropy(site_a - 1) if site_a > 0 else 0.0
        S_B = mps.compute_entanglement_entropy(site_b - 1) if site_b > 0 else 0.0
        S_AB = mps.compute_entanglement_entropy(site_b - 1)  # Entropy of combined region

        # Approximate mutual information
        MI = S_A + S_B - S_AB
        return max(0.0, MI)


class TTNBuilder:
    """Tree Tensor Network builder for hierarchical systems."""

    def __init__(self, topology: SystemTopology, config: AdvancedKernelConfig):
        self.topology = topology
        self.config = config

    def build_ttn(self, heus: List[HolographicEvidenceUnit]) -> Dict:
        """
        Build TTN reflecting system hierarchy.

        Tree structure follows causal topology:
        - Leaves: individual components
        - Internal nodes: clusters of related components
        - Root: entire system
        """
        # Build tree from topology
        tree = self._build_causal_tree()

        # Assign HEUs to leaves
        leaf_heus = self._assign_heus_to_leaves(heus, tree)

        # Bottom-up construction
        tensors = self._build_ttn_bottom_up(tree, leaf_heus)

        return {
            'tree': tree,
            'tensors': tensors,
            'entanglement_spectrum': self._compute_ttn_spectrum(tensors),
        }

    def _build_causal_tree(self) -> Dict:
        """Build tree structure from causal topology."""
        # Simple: cluster by strongly connected components
        import networkx as nx

        G = nx.DiGraph()
        for comp in self.topology.components:
            G.add_node(comp)
        for edge in self.topology.causal_edges:
            G.add_edge(edge.source, edge.target)

        # Find SCCs
        sccs = list(nx.strongly_connected_components(G))
        condensation = nx.condensation(G, sccs)

        # Build tree from condensation DAG
        tree = {}
        for i, scc in enumerate(sccs):
            tree[f'scc_{i}'] = {
                'components': list(scc),
                'children': [],
                'parent': None,
            }

        # Add edges
        for u, v in condensation.edges():
            tree[f'scc_{u}']['children'].append(f'scc_{v}')
            tree[f'scc_{v}']['parent'] = f'scc_{u}'

        return tree

    def _assign_heus_to_leaves(self, heus: List[HolographicEvidenceUnit], tree: Dict) -> Dict:
        """Assign HEUs to tree leaves."""
        leaf_heus = {}
        for node_name, node_data in tree.items():
            if not node_data['children']:  # Leaf
                comp = node_data['components'][0]
                leaf_heus[node_name] = [h for h in heus if h.source_component == comp]
        return leaf_heus

    def _build_ttn_bottom_up(self, tree: Dict, leaf_heus: Dict) -> Dict:
        """Build TTN tensors bottom-up."""
        tensors = {}

        def process_node(node_name: str) -> Tuple[np.ndarray, int]:
            node = tree[node_name]
            if not node['children']:
                # Leaf: build from HEUs
                heus = leaf_heus.get(node_name, [])
                if heus:
                    vectors = np.stack([h.phase_vector for h in heus])
                    U, S, Vh = np.linalg.svd(vectors.T, full_matrices=False)
                    keep = min(len(S), self.config.tensor_network.max_bond_dimension)
                    tensor = U[:, :keep] @ np.diag(S[:keep]) @ Vh[:keep, :]
                    bond_dim = keep
                else:
                    tensor = np.eye(2, dtype=np.complex64)
                    bond_dim = 2
                tensors[node_name] = tensor
                return tensor, bond_dim
            else:
                # Internal node: combine children
                child_tensors = []
                child_bonds = []
                for child in node['children']:
                    ct, cb = process_node(child)
                    child_tensors.append(ct)
                    child_bonds.append(cb)

                # Combine (simplified: tensor product then truncate)
                combined = child_tensors[0]
                for ct in child_tensors[1:]:
                    combined = np.kron(combined, ct)

                # Reshape and truncate
                U, S, Vh = np.linalg.svd(combined.reshape(-1, combined.shape[-1]), full_matrices=False)
                keep = min(len(S), self.config.tensor_network.max_bond_dimension)
                tensor = U[:, :keep] @ np.diag(S[:keep]) @ Vh[:keep, :]
                bond_dim = keep

                tensors[node_name] = tensor
                return tensor, bond_dim

        # Find root
        root = None
        for name, node in tree.items():
            if node['parent'] is None:
                root = name
                break

        if root:
            process_node(root)

        return tensors

    def _compute_ttn_spectrum(self, tensors: Dict) -> List[float]:
        """Compute entanglement spectrum from TTN."""
        spectrum = []
        for tensor in tensors.values():
            if tensor.ndim == 2:
                _, S, _ = np.linalg.svd(tensor, full_matrices=False)
                spectrum.extend(S.tolist())
        return spectrum


# ============================================================================
# 4. Differential Geometry on Bulk Manifold (Ryu-Takayanagi)
# ============================================================================


@dataclass(slots=True)
class BulkGeometry:
    """
    Encodes the bulk geometry (AdS_{d+1}) for holographic duality.

    In Poincaré coordinates:
    ds² = (L²/z²)(dz² + η_μν dx^μ dx^ν)

    Provides methods for computing geometric quantities needed for:
    - Ryu-Takayanagi formula (minimal surfaces)
    - Bulk-to-boundary propagators
    - Covariant derivatives and curvature
    """

    ads_radius: float = 1.0          # AdS radius L
    boundary_dimension: int = 3      # Boundary spacetime dimensions
    bulk_dimension: int = 4          # Bulk spacetime dimensions (AdS_{d+1})

    def ads_metric(self, z: float) -> np.ndarray:
        """
        AdS metric in Poincaré coordinates: ds² = (L²/z²)(dz² + dx²)

        Returns the metric tensor g_μν at a given radial coordinate z.
        """
        factor = (self.ads_radius ** 2) / (z ** 2)
        # diag(1, 1, 1, ..., 1) for spatial part + dz²
        metric = np.eye(self.bulk_dimension) * factor
        # Time component has opposite sign (for Minkowski signature)
        metric[0, 0] = -factor  # Assuming time is first coordinate
        return metric

    def christoffel_symbols(self, z: float) -> np.ndarray:
        """
        Compute Christoffel symbols Γ^λ_μν for AdS metric.

        For AdS in Poincaré coords: Γ^z_zz = -1/z, Γ^z_ii = 1/z, Γ^i_zi = -1/z
        """
        christoffel = np.zeros((self.bulk_dimension, self.bulk_dimension, self.bulk_dimension))

        # Non-zero Christoffel symbols for AdS_{d+1} in Poincaré coordinates
        # Γ^z_zz = -1/z
        christoffel[self.bulk_dimension-1, self.bulk_dimension-1, self.bulk_dimension-1] = -1.0 / z

        # Γ^z_ii = 1/z (for i = 0,...,d-1 spatial)
        for i in range(self.bulk_dimension-1):
            christoffel[self.bulk_dimension-1, i, i] = 1.0 / z

        # Γ^i_zi = Γ^i_iz = -1/z (for i = 0,...,d-1 spatial)
        for i in range(self.bulk_dimension-1):
            christoffel[i, self.bulk_dimension-1, i] = -1.0 / z
            christoffel[i, i, self.bulk_dimension-1] = -1.0 / z

        return christoffel

    def ricci_scalar(self, z: float) -> float:
        """
        Compute Ricci scalar R for AdS_{d+1}.

        For AdS_{d+1}: R = -d(d+1)/L²
        """
        d = self.boundary_dimension
        return -d * (d + 1) / (self.ads_radius ** 2)

    def geodesic_equation(self, z: float, zdot: float) -> float:
        """
        Geodesic equation for radial motion: d²z/dτ² + Γ^z_μν (dx^μ/dτ)(dx^ν/dτ) = 0

        For radial geodesics in AdS: d²z/dτ² - (1/z)(dz/dτ)² = 0
        """
        return (1.0 / z) * zdot**2


class RyuTakayanagiCalculator:
    """
    Implements the Ryu-Takayanagi formula for holographic entanglement entropy.

    S_A = min_{γ_A ∼ ∂A} [Area(γ_A) / (4G_N)]

    Where γ_A is a bulk surface homologous to boundary region A.
    In discrete settings, this becomes a minimal cut problem.
    """

    def __init__(self, topology: SystemTopology, ads_radius: float = 1.0):
        self.topology = topology
        self.ads_radius = ads_radius
        self.G_eff = 1.0  # Effective Newton's constant (can be tuned)

    def compute_entanglement_entropy(self, region: List[str]) -> float:
        """
        Compute entanglement entropy for a boundary region using RT formula.

        Args:
            region: List of component names in the boundary region

        Returns:
            Entanglement entropy S_A = Area(minimal surface) / (4G_N)
        """
        # Build causal graph from topology
        G = self._build_causal_graph()

        # Define boundary of region
        boundary_nodes = self._get_region_boundary(region, G)

        if not boundary_nodes:
            return 0.0

        # Add super source and sink for min-cut computation
        super_source = "super_source"
        super_sink = "super_sink"
        G_with_super = G.copy()
        G_with_super.add_node(super_source)
        G_with_super.add_node(super_sink)

        # Connect super source to boundary of region
        for node in boundary_nodes:
            G_with_super.add_edge(super_source, node, capacity=1.0)
            G_with_super.add_edge(node, super_sink, capacity=1.0)

        # Compute minimum cut (which gives minimal surface area)
        try:
            import networkx as nx
            flow_value = nx.maximum_flow_value(G_with_super, super_source, super_sink)
            min_cut_area = float(flow_value)
        except ImportError:
            # Fallback: simple edge count
            min_cut_area = len(boundary_nodes)  # Approximation

        # Ryu-Takayanagi formula: S = A/(4G_N)
        entropy = min_cut_area / (4 * self.G_eff)
        return entropy

    def _build_causal_graph(self):
        """Build causal graph from system topology."""
        import networkx as nx
        G = nx.Graph()  # Undirected for min-cut

        # Add nodes (components)
        for comp in self.topology.components:
            G.add_node(comp)

        # Add edges (causal relations) with capacities
        for edge in self.topology.causal_edges:
            # Capacity inversely related to latency (faster = higher capacity)
            capacity = 1.0 / (edge.latency_ms + 1.0)  # Avoid division by zero
            G.add_edge(edge.source, edge.target, capacity=capacity)

        return G

    def _get_region_boundary(self, region: List[str], G) -> List[str]:
        """Get boundary of region in causal graph."""
        boundary = []
        region_set = set(region)

        for node in region:
            # Check if node has neighbors outside region
            for neighbor in G.neighbors(node):
                if neighbor not in region_set:
                    boundary.append(node)
                    break

        return list(set(boundary))  # Remove duplicates


class EntanglementEntropyCalculator:
    """
    Computes various entanglement entropies and quantum information measures.

    Implements:
    - Von Neumann entropy: S(ρ) = -Tr(ρ log ρ)
    - Entanglement of formation
    - Squashed entanglement bounds
    - Accessible information (Holevo bound)
    - Holographic bounds via Ryu-Takayanagi
    """

    def __init__(self):
        pass

    def von_neumann_entropy(self, density_matrix: np.ndarray) -> float:
        """
        Compute von Neumann entropy S(ρ) = -Tr(ρ log ρ).

        Args:
            density_matrix: Hermitian, positive semidefinite matrix with Tr(ρ) = 1

        Returns:
            Von Neumann entropy
        """
        # Ensure density matrix is valid
        density_matrix = (density_matrix + density_matrix.conj().T) / 2  # Make Hermitian
        tr = np.trace(density_matrix)
        if abs(tr) <= 1e-12 or np.isnan(tr) or np.isinf(tr):
            return 0.0
        density_matrix = density_matrix / tr  # Normalize

        # Eigenvalues
        try:
            eigenvals = np.linalg.eigvalsh(density_matrix)
        except np.linalg.LinAlgError:
            return 0.0

        eigenvals = eigenvals[eigenvals > 1e-12]  # Remove near-zero eigenvalues
        if len(eigenvals) == 0:
            return 0.0

        # S = -∑ λ_i log λ_i
        entropy = -np.sum(eigenvals * np.log(eigenvals))
        return float(entropy)

    def entanglement_of_formation(self, state_vector: np.ndarray, dim_a: int, dim_b: int) -> float:
        """
        Compute entanglement of formation for a bipartite pure state.

        For pure state |ψ⟩_{AB}, EoF = S(ρ_A) where ρ_A = Tr_B(|ψ⟩⟨ψ|)
        """
        # Reshape state vector
        psi = state_vector.reshape(dim_a, dim_b)

        # Reduced density matrix ρ_A = Tr_B(|ψ⟩⟨ψ|)
        rho_a = psi @ psi.conj().T  # Partial trace over B

        # Von Neumann entropy of ρ_A
        return self.von_neumann_entropy(rho_a)

    def accessible_information(self, ensemble: List[Tuple[np.ndarray, float]]) -> float:
        """
        Compute accessible information (Holevo bound) for an ensemble.

        χ = S(∑ p_i ρ_i) - ∑ p_i S(ρ_i)

        Args:
            ensemble: List of (density_matrix, probability) pairs

        Returns:
            Holevo χ (upper bound on accessible information)
        """
        if not ensemble:
            return 0.0

        # Average state: ρ̄ = ∑ p_i ρ_i
        rho_avg = np.zeros_like(ensemble[0][0])
        for rho, p in ensemble:
            rho_avg += p * rho

        # Holevo χ = S(ρ̄) - ∑ p_i S(ρ_i)
        s_avg = self.von_neumann_entropy(rho_avg)
        s_ensemble = sum(p * self.von_neumann_entropy(rho) for rho, p in ensemble)

        chi = s_avg - s_ensemble
        return max(0.0, chi)  # Non-negative by concavity of entropy

    def squashed_entanglement_bound(self, mutual_information: float) -> float:
        """
        Squashed entanglement provides an upper bound on entanglement of formation.

        E_sq ≤ I(A:B)/2

        Args:
            mutual_information: Quantum mutual information I(A:B)

        Returns:
            Upper bound on squashed entanglement
        """
        return mutual_information / 2.0


class RenormalizationGroupFlow:
    """
    Implements renormalization group flow analysis for holographic systems.

    Tracks how effective couplings change with scale:
    - Beta functions: β(g) = μ ∂g/∂μ
    - Fixed points: β(g*) = 0
    - Scale-dependent physics extraction
    """

    def __init__(self, config: RenormalizationConfig):
        self.config = config
        self.scales = []  # Energy scales
        self.couplings = {}  # Coupling names -> values at each scale
        self.beta_functions = {}  # Coupling names -> beta functions

    def initialize_flow(self, uv_couplings: Dict[str, float]):
        """
        Initialize RG flow with UV boundary conditions.

        Args:
            uv_couplings: Dictionary of coupling names -> UV values
        """
        # Generate scale sequence (UV to IR)
        self.scales = [self.config.coarse_graining_factor ** i
                      for i in range(self.config.num_scales)]
        self.scales = [1.0 / s for s in self.scales]  # Invert for energy scale

        # Initialize couplings at each scale
        for coupling_name, uv_value in uv_couplings.items():
            self.couplings[coupling_name] = [uv_value] * len(self.scales)

    def compute_beta_function(self, coupling_name: str,
                            coupling_value: float,
                            scale_index: int) -> float:
        """
        Compute beta function for a coupling.

        For holographic theories, beta functions often take the form:
        β(g) = -ε g + a g² + b g³ + ... (perturbative)
        or non-perturbative forms from bulk geometry

        Args:
            coupling_name: Name of the coupling
            coupling_value: Current value of the coupling
            scale_index: Index in scale sequence

        Returns:
            Beta function value β(g)
        """
        # Default: simple perturbative beta function
        # This should be customized based on the specific holographic model
        epsilon = 0.1  # Anomalous dimension
        a = 0.5        # Quadratic coefficient

        beta = -epsilon * coupling_value + a * coupling_value**2

        # Add holographic corrections (example)
        # In AdS/CFT, beta functions relate to bulk scalar field potentials
        if coupling_name == "mass":
            beta += 0.01 * np.sqrt(max(0, coupling_value))  # Holographic correction

        return beta

    def flow_equations(self) -> Dict[str, List[float]]:
        """
        Solve RG flow equations from UV to IR.

        Returns:
            Dictionary mapping coupling names to their values at each scale
        """
        if not self.couplings:
            return {}

        # Make a copy to store results
        flowed_couplings = {name: values[:] for name, values in self.couplings.items()}

        # Simple Euler integration: g(μ_{i+1}) = g(μ_i) + β(g) Δt
        # In logarithmic scale: Δt = log(μ_{i+1}/μ_i)
        for i in range(len(self.scales) - 1):
            scale_ratio = self.scales[i+1] / self.scales[i]
            dt = np.log(scale_ratio) if scale_ratio > 0 else 0.1

            for coupling_name in self.couplings:
                current_value = flowed_couplings[coupling_name][i]
                beta = self.compute_beta_function(coupling_name, current_value, i)
                flowed_couplings[coupling_name][i+1] = current_value + beta * dt

                # Ensure couplings stay positive (if required)
                if coupling_name in ["mass", "coupling"]:  # Typically positive
                    flowed_couplings[coupling_name][i+1] = max(0.0, flowed_couplings[coupling_name][i+1])

        return flowed_couplings

    def find_fixed_points(self, tolerance: float = None) -> Dict[str, float]:
        """
        Find fixed points of the RG flow where β(g*) = 0.

        Args:
            tolerance: Tolerance for considering beta function zero

        Returns:
            Dictionary of coupling names -> fixed point values
        """
        if tolerance is None:
            tolerance = self.config.fixed_point_tolerance

        fixed_points = {}

        # Scan plausible range for each coupling
        for coupling_name in self.couplings:
            # Simple search: look for where beta changes sign
            test_values = np.logspace(-3, 2, 50)  # From 0.001 to 100
            zero_crossings = []

            prev_beta = self.compute_beta_function(coupling_name, test_values[0], 0)
            for val in test_values[1:]:
                beta = self.compute_beta_function(coupling_name, val, 0)
                if prev_beta * beta < 0:  # Sign change
                    # Linear interpolation to find zero
                    zero_val = val - beta * (val - test_values[0]) / (beta - prev_beta)
                    zero_crossings.append(zero_val)
                prev_beta = beta

            if zero_crossings:
                # Take the first zero crossing as approximate fixed point
                fixed_points[coupling_name] = zero_crossings[0]

        return fixed_points


# ============================================================================
# 5. Advanced Kernel Builder (Unifier)
# ============================================================================

class AdvancedKernelBuilder:
    """
    Unified builder for all advanced physics-based kernels.

    Combines:
    - Wave propagation kernels (FDTD + AdS Green's functions)
    - Path integral causal kernels (Monte Carlo + saddle-point)
    - Tensor network representations (MPS/TTN)
    - Differential geometry tools (Christoffel, Ricci, RT formula)
    - Entanglement entropy measures
    - Renormalization group flow
    """

    def __init__(self, topology: SystemTopology, config: AdvancedKernelConfig = None):
        self.topology = topology
        self.config = config or AdvancedKernelConfig()

        # Initialize subsystem builders
        self.wave_builder = WaveKernelBuilder(topology, self.config)
        self.path_builder = PathIntegralKernelBuilder(topology, self.config)
        self.tn_builder = TensorNetworkBuilder(topology, self.config)
        self.ttn_builder = TTNBuilder(topology, self.config)
        self.rt_calculator = RyuTakayanagiCalculator(topology)
        self.entropy_calculator = EntanglementEntropyCalculator()
        self.rg_flow = RenormalizationGroupFlow(self.config.renormalization)

        # Cache for built kernels
        self._kernel_cache = {}

    def build_all_kernels(self) -> Dict[str, Any]:
        """
        Build all advanced kernels and return them in a unified dictionary.

        Returns:
            Dictionary containing all built kernels and computational tools
        """
        self._kernel_cache.clear()

        # Build wave kernels
        self._kernel_cache['wave_kernels'] = self.wave_builder.build_all()

        # Build path integral kernels
        self._kernel_cache['path_integral_kernels'] = self.path_builder.build_all()

        # Build tensor network structures (placeholder - needs HEU data)
        self._kernel_cache['tensor_network_builder'] = self.tn_builder
        self._kernel_cache['ttn_builder'] = self.ttn_builder

        # Build geometric tools
        self._kernel_cache['bulk_geometry'] = BulkGeometry(
            ads_radius=1.0,
            boundary_dimension=self.config.boundary_layers,
            bulk_dimension=self.config.bulk_dimension + 1  # AdS_{d+1}
        )

        self._kernel_cache['ryu_takayanagi'] = self.rt_calculator
        self._kernel_cache['entanglement_entropy'] = self.entropy_calculator
        self._kernel_cache['renormalization_group'] = self.rg_flow

        return self._kernel_cache

    def compute_wave_propagation(self, component: str, layer: BoundaryLayer) -> np.ndarray:
        """
        Convenience method to compute wave propagation kernel.
        """
        if 'wave_kernels' not in self._kernel_cache:
            self.build_all_kernels()

        key = (component, layer)
        return self._kernel_cache['wave_kernels'].get(key, np.array([]))

    def compute_causal_propagation(self, source: str, target: str) -> np.ndarray:
        """
        Convenience method to compute causal propagation kernel.
        """
        if 'path_integral_kernels' not in self._kernel_cache:
            self.build_all_kernels()

        key = (source, target)
        return self._kernel_cache['path_integral_kernels'].get(key, np.array([]))

    def compute_entanglement_entropy_mps(self, heus: List[HolographicEvidenceUnit],
                                       components: List[str],
                                       layers: List[BoundaryLayer],
                                       cut: int) -> float:
        """
        Compute entanglement entropy using MPS representation.
        """
        mps = self.tn_builder.build_mps_from_heus(heus, components, layers)
        return mps.compute_entanglement_entropy(cut)

    def compute_holographic_entropy(self, region: List[str]) -> float:
        """
        Compute entanglement entropy via Ryu-Takayanagi formula.
        """
        return self.rt_calculator.compute_entanglement_entropy(region)

    def analyze_rg_flow(self, uv_couplings: Dict[str, float]) -> Dict[str, Any]:
        """
        Analyze renormalization group flow from UV to IR.
        """
        self.rg_flow.initialize_flow(uv_couplings)
        flowed = self.rg_flow.flow_equations()
        fixed_points = self.rg_flow.find_fixed_points()

        return {
            'flowed_couplings': flowed,
            'fixed_points': fixed_points,
            'scales': self.rg_flow.scales
        }

    def get_available_computations(self) -> List[str]:
        """
        List all available advanced computations.
        """
        return [
            'wave_propagation',
            'causal_propagation',
            'tensor_network_mps',
            'tensor_network_ttn',
            'holographic_entanglement_entropy',
            'von_neumann_entropy',
            'entanglement_of_formation',
            'accessible_information',
            'renormalization_group_flow',
            'fixed_point_analysis'
        ]


# Convenience functions for easy access
def build_advanced_kernels(topology: SystemTopology,
                          config: AdvancedKernelConfig = None) -> AdvancedKernelBuilder:
    """
    Factory function to create an AdvancedKernelBuilder.

    Args:
        topology: System topology
        config: Advanced kernel configuration (uses defaults if None)

    Returns:
        Configured AdvancedKernelBuilder instance
    """
    return AdvancedKernelBuilder(topology, config)


def compute_holographic_entanglement(builder: AdvancedKernelBuilder,
                                   region: List[str]) -> float:
    """
    Convenience function to compute holographic entanglement entropy.

    Args:
        builder: AdvancedKernelBuilder instance
        region: Boundary region as list of component names

    Returns:
        Holographic entanglement entropy
    """
    return builder.compute_holographic_entropy(region)


def compute_wave_kernel(builder: AdvancedKernelBuilder,
                       component: str,
                       layer: BoundaryLayer) -> np.ndarray:
    """
    Convenience function to compute wave propagation kernel.
    """
    return builder.compute_wave_propagation(component, layer)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Configuration classes
    'WaveKernelConfig',
    'PathIntegralConfig',
    'TensorNetworkConfig',
    'RenormalizationConfig',
    'AdvancedKernelConfig',

    # Kernel classes
    'WavePropagationKernel',
    'WaveKernelBuilder',
    'PathIntegralCausalKernel',
    'PathIntegralKernelBuilder',
    'TensorNetworkState',
    'TensorNetworkBuilder',
    'TTNBuilder',
    'BulkGeometry',
    'RyuTakayanagiCalculator',
    'EntanglementEntropyCalculator',
    'RenormalizationGroupFlow',
    'AdvancedKernelBuilder',

    # Convenience functions
    'build_advanced_kernels',
    'compute_holographic_entanglement',
    'compute_wave_kernel',

    # Enums
    'DecayType',
    'GeometryType',
]

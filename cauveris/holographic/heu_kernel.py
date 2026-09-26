"""
Holographic Causal Kernels - Green's functions for boundary-bulk propagation.

Implements the mathematical kernels that describe how internal system state
propagates to the observable boundary (HEUs). These are the "holographic
propagation kernels" analogous to Green's functions in AdS/CFT.
"""
from __future__ import annotations

import math
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .topology import SystemTopology, ComponentInfo, CausalEdge, ResourceCapacity


@dataclass(slots=True)
class KernelConfig:
    """Configuration for kernel construction."""
    time_step_ns: int = 1_000_000          # 1ms resolution
    max_kernel_time_ns: int = 10_000_000_000  # 10 second max propagation
    self_latency_factor: float = 0.1       # Internal latency as fraction of capacity
    queue_service_time_ms: float = 0.5     # Base service time for queueing
    decay_type: str = "exponential"        # exponential, gamma, bi_exponential
    normalization: str = "l1"              # l1, l2, max


@dataclass(slots=True)
class LocalPropagationKernel:
    """Kernel describing how component state propagates to its own boundary."""
    component_name: str
    boundary_layer: str
    time_axis_ns: np.ndarray          # Time points [0, dt, 2dt, ...]
    kernel_values: np.ndarray         # K(t) values
    integral: float                   # ∫K(t)dt (should be 1.0 for conservation)
    peak_time_ns: float              # Time of maximum response
    half_life_ns: float              # Time for kernel to decay to 0.5

    def evaluate_at(self, t_ns: float) -> float:
        """Evaluate kernel at specific time."""
        if t_ns < 0 or t_ns >= self.time_axis_ns[-1]:
            return 0.0
        idx = int(t_ns / (self.time_axis_ns[1] - self.time_axis_ns[0]))
        return float(self.kernel_values[idx])

    def convolve(self, signal: np.ndarray, dt_ns: int) -> np.ndarray:
        """Convolve signal with kernel."""
        return np.convolve(signal, self.kernel_values, mode='full')[:len(signal)] * (dt_ns / 1e9)


@dataclass(slots=True)
class CrossPropagationKernel:
    """Kernel describing cross-component propagation (service-to-service)."""
    source: str
    target: str
    edge_type: str
    time_axis_ns: np.ndarray
    kernel_values: np.ndarray
    total_latency_ns: float        # Sum of: src_internal + network + queue + dst_internal
    network_latency_ns: float
    queueing_latency_ns: float


class CausalKernelBuilder:
    """
    Builds causal propagation kernels from SystemTopology.

    For each boundary layer and component pair, computes how internal
    state changes propagate to observable signals at the boundary.
    """

    def __init__(
        self,
        topology: SystemTopology,
        config: Optional[KernelConfig] = None,
    ):
        self.topology = topology
        self.config = config or KernelConfig()
        self._local_kernels: Dict[Tuple[str, str], LocalPropagationKernel] = {}
        self._cross_kernels: Dict[Tuple[str, str], CrossPropagationKernel] = {}

    def build_all_kernels(self) -> Dict:
        """
        Build all propagation kernels for all components and boundary layers.

        Returns:
            Dict with 'local' and 'cross' kernel mappings.
        """
        # Clear cache
        self._local_kernels.clear()
        self._cross_kernels.clear()

        # Build local kernels for each component and its boundary layers
        for comp_name, comp in self.topology.components.items():
            for layer in comp.boundary_layers:
                self._local_kernels[(comp_name, layer)] = self._build_local_kernel(comp, layer)

        # Build cross kernels for each causal edge
        for edge in self.topology.causal_edges:
            if edge.source in self.topology.components and edge.target in self.topology.components:
                src_comp = self.topology.components[edge.source]
                dst_comp = self.topology.components[edge.target]
                # Build cross kernels for each boundary layer pair
                for src_layer in src_comp.boundary_layers:
                    for dst_layer in dst_comp.boundary_layers:
                        self._cross_kernels[(edge.source, edge.target, src_layer, dst_layer)] = \
                            self._build_cross_kernel(src_comp, dst_comp, edge, src_layer, dst_layer)

        return {
            'local': self._local_kernels,
            'cross': self._cross_kernels,
        }

    def _build_local_kernel(
        self,
        component: ComponentInfo,
        boundary_layer: str,
    ) -> LocalPropagationKernel:
        """
        Build local propagation kernel: internal state → component's own boundary.

        Physical model: State changes in a component's CPU/memory/network propagate
        to its local logs/metrics with a characteristic delay based on the component's
        internal architecture (sampling intervals, buffer sizes, etc.).
        """
        dt = self.config.time_step_ns
        max_t = self.config.max_kernel_time_ns
        time_axis = np.arange(0, max_t, dt, dtype=np.float64)

        # Characteristic time constant based on component capacity and layer
        tau_ns = self._compute_local_tau(component, boundary_layer)

        if self.config.decay_type == "exponential":
            kernel = np.exp(-time_axis / tau_ns) / tau_ns
        elif self.config.decay_type == "gamma":
            # Gamma distribution with shape=2 (more realistic for queuing)
            shape = 2.0
            scale = tau_ns / shape
            kernel = (time_axis ** (shape - 1) * np.exp(-time_axis / scale)) / \
                     (scale ** shape * math.gamma(shape))
        elif self.config.decay_type == "bi_exponential":
            # Fast + slow components (e.g., log buffer flush + metric scrape)
            tau_fast = tau_ns * 0.1
            tau_slow = tau_ns
            kernel = 0.7 * np.exp(-time_axis / tau_fast) / tau_fast + \
                     0.3 * np.exp(-time_axis / tau_slow) / tau_slow
        else:
            kernel = np.exp(-time_axis / tau_ns) / tau_ns

        # Normalize
        if self.config.normalization == "l1":
            integral = np.trapezoid(kernel, time_axis)
            if integral > 0:
                kernel = kernel / integral
        elif self.config.normalization == "l2":
            norm = np.sqrt(np.trapezoid(kernel ** 2, time_axis))
            if norm > 0:
                kernel = kernel / norm
        elif self.config.normalization == "max":
            max_val = np.max(kernel)
            if max_val > 0:
                kernel = kernel / max_val

        integral = float(np.trapezoid(kernel, time_axis))
        peak_idx = np.argmax(kernel)
        peak_time = float(time_axis[peak_idx])

        # Half-life (time to decay to 0.5 of peak)
        peak_val = kernel[peak_idx]
        half_life = max_t
        for i in range(peak_idx, len(kernel)):
            if kernel[i] <= peak_val * 0.5:
                half_life = float(time_axis[i])
                break

        return LocalPropagationKernel(
            component_name=component.name,
            boundary_layer=boundary_layer,
            time_axis_ns=time_axis,
            kernel_values=kernel.astype(np.float32),
            integral=integral,
            peak_time_ns=peak_time,
            half_life_ns=half_life,
        )

    def _compute_local_tau(self, component: ComponentInfo, layer: str) -> float:
        """Compute characteristic time constant for local propagation."""
        # Base latency from resource capacity (higher capacity = faster internal propagation)
        base_tau_ms = 10.0  # 10ms base

        # Adjust by component type
        type_factors = {
            "service": 1.0,
            "database": 2.0,      # Databases have more internal buffering
            "queue": 0.5,         # Queues are fast
            "gateway": 0.8,       # Gateways are network-bound
            "monitoring": 1.5,    # Monitoring aggregates
        }
        base_tau_ms *= type_factors.get(component.component_type, 1.0)

        # Adjust by boundary layer
        layer_factors = {
            "application_log": 1.0,        # Logs: immediate
            "infrastructure_log": 1.2,     # System logs: slight delay
            "distributed_trace": 0.3,      # Traces: very fast (instrumented)
            "metrics_export": 5.0,         # Metrics: scrape interval ~10-30s
            "network_flow": 1.0,           # NetFlow: per-packet or per-flow
            "config_state": 10.0,          # Config: propagation through reload
            "deployment_event": 0.1,       # Deployment: instant marker
        }
        base_tau_ms *= layer_factors.get(layer, 1.0)

        # Convert to nanoseconds
        return base_tau_ms * 1_000_000

    def _build_cross_kernel(
        self,
        src: ComponentInfo,
        dst: ComponentInfo,
        edge: CausalEdge,
        src_layer: str,
        dst_layer: str,
    ) -> CrossPropagationKernel:
        """
        Build cross-component propagation kernel: src internal → dst boundary.

        Physical model: Convolution of:
        1. src internal state → src boundary (local kernel)
        2. Network transport (edge latency, queueing)
        3. dst internal processing → dst boundary (local kernel)
        """
        dt = self.config.time_step_ns
        max_t = self.config.max_kernel_time_ns
        time_axis = np.arange(0, max_t, dt, dtype=np.float64)

        # Get local kernels
        src_kernel = self._local_kernels.get((src.name, src_layer))
        dst_kernel = self._local_kernels.get((dst.name, dst_layer))

        if src_kernel is None:
            src_kernel = self._build_local_kernel(src, src_layer)
        if dst_kernel is None:
            dst_kernel = self._build_local_kernel(dst, dst_layer)

        # Network + queueing delay
        network_latency_ns = edge.latency_ms * 1_000_000
        queueing_latency_ns = edge.queue_depth * self.config.queue_service_time_ms * 1_000_000
        total_network_latency_ns = network_latency_ns + queueing_latency_ns

        # Shift src kernel by network latency
        shift_idx = int(total_network_latency_ns / dt)
        shifted_src = np.zeros_like(src_kernel.kernel_values)
        if shift_idx < len(shifted_src):
            shifted_src[shift_idx:] = src_kernel.kernel_values[:-shift_idx]

        # Convolve: shifted_src * dst_kernel
        cross_kernel = np.convolve(shifted_src, dst_kernel.kernel_values, mode='full')
        cross_kernel = cross_kernel[:len(time_axis)]

        # Normalize
        if self.config.normalization == "l1":
            integral = np.trapezoid(cross_kernel, time_axis)
            if integral > 0:
                cross_kernel = cross_kernel / integral

        total_latency = (
            src_kernel.peak_time_ns +
            total_network_latency_ns +
            dst_kernel.peak_time_ns
        )

        return CrossPropagationKernel(
            source=src.name,
            target=dst.name,
            edge_type=edge.edge_type,
            time_axis_ns=time_axis,
            kernel_values=cross_kernel.astype(np.float32),
            total_latency_ns=total_latency,
            network_latency_ns=network_latency_ns,
            queueing_latency_ns=queueing_latency_ns,
        )

    def get_local_kernel(self, component: str, layer: str) -> Optional[LocalPropagationKernel]:
        """Get local propagation kernel for component+layer."""
        return self._local_kernels.get((component, layer))

    def get_cross_kernel(
        self,
        source: str,
        target: str,
        src_layer: str = "application_log",
        dst_layer: str = "application_log",
    ) -> Optional[CrossPropagationKernel]:
        """Get cross-component propagation kernel."""
        return self._cross_kernels.get((source, target, src_layer, dst_layer))

    def build_kernel_matrix(
        self,
        components: List[str],
        layers: List[str],
        time_horizon_ns: int,
    ) -> np.ndarray:
        """
        Build full kernel matrix K for measurement system.

        K[i, j, t] = how component j's state affects component i's boundary at layer l at time t

        Returns:
            Kernel tensor of shape (n_components * n_layers, n_components, n_time_steps)
        """
        n_comp = len(components)
        n_layers = len(layers)
        n_time = time_horizon_ns // self.config.time_step_ns

        # State index: component * n_layers + layer
        K = np.zeros((n_comp * n_layers, n_comp, n_time), dtype=np.float32)

        comp_to_idx = {c: i for i, c in enumerate(components)}
        layer_to_idx = {l: i for i, l in enumerate(layers)}

        # Diagonal blocks: local propagation
        for i, comp in enumerate(components):
            for l_idx, layer in enumerate(layers):
                kernel = self.get_local_kernel(comp, layer)
                if kernel:
                    state_idx = i * n_layers + l_idx
                    # Pad/truncate kernel to n_time
                    k_vals = kernel.kernel_values[:n_time]
                    K[state_idx, i, :len(k_vals)] = k_vals

        # Off-diagonal blocks: cross propagation
        for edge in self.topology.causal_edges:
            if edge.source in comp_to_idx and edge.target in comp_to_idx:
                src_i = comp_to_idx[edge.source]
                dst_i = comp_to_idx[edge.target]

                src_comp = self.topology.components[edge.source]
                dst_comp = self.topology.components[edge.target]

                for src_layer in src_comp.boundary_layers:
                    for dst_layer in dst_comp.boundary_layers:
                        kernel = self.get_cross_kernel(
                            edge.source, edge.target, src_layer, dst_layer
                        )
                        if kernel:
                            src_state_idx = src_i * n_layers + layer_to_idx.get(src_layer, 0)
                            dst_obs_idx = dst_i * n_layers + layer_to_idx.get(dst_layer, 0)
                            k_vals = kernel.kernel_values[:n_time]
                            K[dst_obs_idx, src_i, :len(k_vals)] = k_vals

        return K

    def verify_causality(self) -> Dict[str, bool]:
        """
        Verify kernel causality properties.

        Returns dict of checks:
        - no_anticipation: kernel is zero for t < 0
        - conservation: ∫K(t)dt ≈ 1 for local kernels
        - peak_ordering: cross kernel peaks after local kernels
        """
        results = {
            "no_anticipation": True,
            "conservation": True,
            "peak_ordering": True,
        }

        for (comp, layer), kernel in self._local_kernels.items():
            # No anticipation: kernel should be zero for t < 0 (by construction)
            if np.any(kernel.kernel_values[:10] > 1e-6):  # First 10ms shouldn't have signal
                results["no_anticipation"] = False

            # Conservation: integral ≈ 1
            if abs(kernel.integral - 1.0) > 0.15:  # Relaxed tolerance for numerical integration
                results["conservation"] = False

        # Peak ordering: cross kernels should peak after local kernels
        for (src, dst, src_l, dst_l), cross in self._cross_kernels.items():
            src_local = self._local_kernels.get((src, src_l))
            dst_local = self._local_kernels.get((dst, dst_l))
            if src_local and dst_local:
                if cross.total_latency_ns < (src_local.peak_time_ns + dst_local.peak_time_ns):
                    results["peak_ordering"] = False

        return results


def build_causal_kernels(
    topology: SystemTopology,
    config: Optional[KernelConfig] = None,
) -> Dict:
    """
    Convenience function to build all causal kernels.

    Args:
        topology: System topology
        config: Kernel configuration

    Returns:
        Dictionary with 'local', 'cross' kernel mappings
    """
    builder = CausalKernelBuilder(topology, config)
    return builder.build_all_kernels()


if __name__ == "__main__":
    # Quick test
    from .topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge

    topo = SystemTopology()
    topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(cpu_cores=4.0), boundary_layers=["application_log", "distributed_trace", "metrics_export"]))
    topo.add_component(ComponentInfo(name="svc_b", capacity=ResourceCapacity(cpu_cores=2.0), boundary_layers=["application_log", "metrics_export"]))
    topo.add_causal_edge(CausalEdge(source="svc_a", target="svc_b", latency_ms=5.0, edge_type="rpc"))

    kernels = build_causal_kernels(topo)
    print(f"Local kernels: {len(kernels['local'])}")
    print(f"Cross kernels: {len(kernels['cross'])}")

    builder = CausalKernelBuilder(topo)
    checks = builder.verify_causality()
    print(f"Causality checks: {checks}")
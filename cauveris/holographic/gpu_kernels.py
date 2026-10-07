"""
GPU-Accelerated Holographic Kernels - Python wrapper for C++ CUDA implementation.

This module provides a drop-in replacement for the NumPy-based kernel computations
in heu_kernel.py, with automatic GPU acceleration when available.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

import numpy as np

from .topology import SystemTopology
from .heu import BoundaryLayer
from .heu_kernel import LocalPropagationKernel, CrossPropagationKernel

logger = logging.getLogger(__name__)

# Try to import the C++ extension
try:
    from cauveris_kernels_py import (
        KernelConfig,
        LocalKernelBuilder,
        CausalEdge as CppCausalEdge,
        ComponentType as CppComponentType,
        BoundaryLayer as CppBoundaryLayer,
        DecayType as CppDecayType,
        NormalizationType as CppNormalizationType,
        build_local_kernels,
        build_cross_kernels,
    )
    GPU_AVAILABLE = True
    logger.info("GPU-accelerated kernels loaded successfully")
except ImportError as e:
    GPU_AVAILABLE = False
    logger.warning(f"GPU kernels not available, falling back to CPU: {e}")


class DecayType(Enum):
    EXPONENTIAL = "exponential"
    GAMMA = "gamma"
    BI_EXPONENTIAL = "bi_exponential"


class NormalizationType(Enum):
    L1 = "l1"
    L2 = "l2"
    MAX = "max"


@dataclass
class GPUConfig:
    """Configuration for GPU-accelerated kernels."""
    time_step_ns: int = 1_000_000          # 1ms resolution
    max_kernel_time_ns: int = 10_000_000_000  # 10 second max propagation
    self_latency_factor: float = 0.1
    queue_service_time_ms: float = 0.5
    decay_type: DecayType = DecayType.EXPONENTIAL
    normalization: NormalizationType = NormalizationType.L1
    use_gpu: bool = True
    gpu_device_id: int = 0

    def to_cpp_config(self) -> "KernelConfig":
        """Convert to C++ KernelConfig."""
        if not GPU_AVAILABLE:
            raise RuntimeError("GPU kernels not available")
        cfg = KernelConfig()
        cfg.time_step_ns = self.time_step_ns
        cfg.max_kernel_time_ns = self.max_kernel_time_ns
        cfg.self_latency_factor = self.self_latency_factor
        cfg.queue_service_time_ms = self.queue_service_time_ms
        cfg.decay_type = CppDecayType[self.decay_type.name]
        cfg.normalization = CppNormalizationType[self.normalization.name]
        return cfg


def _component_type_to_cpp(comp_type: str) -> "CppComponentType":
    """Map component type string to C++ enum."""
    mapping = {
        "service": CppComponentType.SERVICE,
        "database": CppComponentType.DATABASE,
        "cache": CppComponentType.CACHE,
        "gateway": CppComponentType.GATEWAY,
        "message_queue": CppComponentType.MESSAGE_QUEUE,
        "monitoring": CppComponentType.MONITORING,
    }
    return mapping.get(comp_type, CppComponentType.SERVICE)


def _boundary_layer_to_cpp(layer: BoundaryLayer) -> "CppBoundaryLayer":
    """Map Python BoundaryLayer to C++ enum."""
    mapping = {
        BoundaryLayer.APPLICATION_LOG: CppBoundaryLayer.APPLICATION_LOG,
        BoundaryLayer.METRICS_EXPORT: CppBoundaryLayer.METRICS_EXPORT,
        BoundaryLayer.DISTRIBUTED_TRACE: CppBoundaryLayer.DISTRIBUTED_TRACE,
        BoundaryLayer.NETWORK_FLOW: CppBoundaryLayer.NETWORK_FLOW,
        BoundaryLayer.INFRASTRUCTURE_LOG: CppBoundaryLayer.INFRASTRUCTURE_LOG,
    }
    return mapping.get(layer, CppBoundaryLayer.APPLICATION_LOG)


class GPUAcceleratedKernelBuilder:
    """
    GPU-accelerated drop-in replacement for CausalKernelBuilder.

    Builds causal propagation kernels using CUDA for massive speedups
    on large topologies (100+ components).
    """

    def __init__(self, topology: SystemTopology, config: Optional[GPUConfig] = None):
        self.topology = topology
        self.config = config or GPUConfig()
        self._local_kernels: Dict[Tuple[str, BoundaryLayer], Any] = {}
        self._cross_kernels: Dict[Tuple[str, str, BoundaryLayer, BoundaryLayer], Any] = {}
        self._use_gpu = self.config.use_gpu and GPU_AVAILABLE

        if self._use_gpu:
            logger.info("Initializing GPU-accelerated kernel builder")
        else:
            logger.info("GPU not available, using CPU fallback")

    def build_all_kernels(self) -> Dict:
        """
        Build all propagation kernels.

        Returns:
            Dict with 'local' and 'cross' kernel mappings (same format as CPU version)
        """
        if self._use_gpu:
            return self._build_all_kernels_gpu()
        else:
            return self._build_all_kernels_cpu()

    def _build_all_kernels_cpu(self) -> Dict:
        """Build kernels using original CPU implementation."""
        from .heu_kernel import KernelConfig as CPUConfig, CausalKernelBuilder

        cpu_config = CPUConfig(
            time_step_ns=self.config.time_step_ns,
            max_kernel_time_ns=self.config.max_kernel_time_ns,
            self_latency_factor=self.config.self_latency_factor,
            queue_service_time_ms=self.config.queue_service_time_ms,
            decay_type=self.config.decay_type.value,
            normalization=self.config.normalization.value,
        )
        builder = CausalKernelBuilder(self.topology, cpu_config)
        return builder.build_all_kernels()

    def _build_all_kernels_gpu(self) -> Dict:
        """Build kernels using GPU acceleration."""
        # Extract component data
        component_names = list(self.topology.components.keys())
        component_types = [_component_type_to_cpp(c.component_type) for c in self.topology.components.values()]
        component_layers = [[_boundary_layer_to_cpp(layer) for layer in c.boundary_layers] for c in self.topology.components.values()]

        # Build local kernels
        local_kernels_dict = build_local_kernels(
            component_names,
            [int(t) for t in component_types],
            [[int(layer_val) for layer_val in layers] for layers in component_layers],
            self.config.to_cpp_config()
        )

        # Convert to Python format
        local_kernels = {}
        for key, kernel in local_kernels_dict.items():
            # Parse key: "component_name|layer_int"
            parts = key.split("|")
            if len(parts) == 2:
                comp_name = parts[0]
                layer = BoundaryLayer(int(parts[1]))
                local_kernels[(comp_name, layer)] = self._cpp_to_python_local_kernel(kernel)

        # Build cross kernels
        edges = []
        for edge in self.topology.causal_edges:
            cpp_edge = CppCausalEdge()
            cpp_edge.source = edge.source
            cpp_edge.target = edge.target
            cpp_edge.latency_ms = edge.latency_ms
            cpp_edge.queue_depth = edge.queue_depth
            cpp_edge.edge_type = edge.edge_type
            edges.append(cpp_edge)

        local_builder = LocalKernelBuilder(self.config.to_cpp_config())
        cross_kernels_dict = build_cross_kernels(
            component_names,
            [int(t) for t in component_types],
            [[int(layer_val) for layer_val in layers] for layers in component_layers],
            edges,
            local_builder
        )

        # Convert cross kernels
        cross_kernels = {}
        for key, kernel in cross_kernels_dict.items():
            # Parse key: "source|target|src_layer|dst_layer"
            parts = key.split("|")
            if len(parts) == 4:
                src = parts[0]
                dst = parts[1]
                src_layer = BoundaryLayer(int(parts[2]))
                dst_layer = BoundaryLayer(int(parts[3]))
                cross_kernels[(src, dst, src_layer, dst_layer)] = self._cpp_to_python_cross_kernel(kernel)

        return {
            'local': local_kernels,
            'cross': cross_kernels,
        }

    def _cpp_to_python_local_kernel(self, cpp_kernel: Any) -> LocalPropagationKernel:
        """Convert C++ LocalPropagationKernel to Python format."""
        kernel = LocalPropagationKernel(
            component_name=cpp_kernel.component_name,
            boundary_layer=cpp_kernel.boundary_layer,
            time_axis_ns=np.array(cpp_kernel.time_axis_ns, dtype=np.float64),
            kernel_values=np.array(cpp_kernel.kernel_values, dtype=np.float32),
            integral=cpp_kernel.integral,
            peak_time_ns=cpp_kernel.peak_time_ns,
            half_life_ns=cpp_kernel.half_life_ns,
        )
        return kernel

    def _cpp_to_python_cross_kernel(self, cpp_kernel: Any) -> CrossPropagationKernel:
        """Convert C++ CrossPropagationKernel to Python format."""
        kernel = CrossPropagationKernel(
            source=cpp_kernel.source,
            target=cpp_kernel.target,
            edge_type=cpp_kernel.edge_type,
            time_axis_ns=np.array(cpp_kernel.time_axis_ns, dtype=np.float64),
            kernel_values=np.array(cpp_kernel.kernel_values, dtype=np.float32),
            total_latency_ns=cpp_kernel.total_latency_ns,
            network_latency_ns=cpp_kernel.network_latency_ns,
            queueing_latency_ns=cpp_kernel.queueing_latency_ns,
        )
        return kernel

    def get_local_kernel(self, component: str, layer: BoundaryLayer) -> Optional[Any]:
        """Get local propagation kernel for component+layer."""
        return self._local_kernels.get((component, layer))

    def get_cross_kernel(
        self,
        source: str,
        target: str,
        src_layer: BoundaryLayer = BoundaryLayer.APPLICATION_LOG,
        dst_layer: BoundaryLayer = BoundaryLayer.APPLICATION_LOG,
    ) -> Optional[Any]:
        """Get cross-component propagation kernel."""
        return self._cross_kernels.get((source, target, src_layer, dst_layer))

    def build_kernel_matrix(
        self,
        components: List[str],
        layers: List[BoundaryLayer],
        time_horizon_ns: int,
    ) -> np.ndarray:
        """
        Build full kernel matrix K for measurement system.

        K[i, j, t] = how component j's state affects component i's boundary at layer l at time t

        This is GPU-accelerated for large matrices.
        """
        if self._use_gpu and len(components) * len(layers) > 50:
            return self._build_kernel_matrix_gpu(components, layers, time_horizon_ns)
        else:
            return self._build_kernel_matrix_cpu(components, layers, time_horizon_ns)

    def _build_kernel_matrix_cpu(
        self,
        components: List[str],
        layers: List[BoundaryLayer],
        time_horizon_ns: int,
    ) -> np.ndarray:
        """CPU fallback for kernel matrix construction."""
        from .heu_kernel import CausalKernelBuilder, KernelConfig as CPUConfig

        cpu_config = CPUConfig(
            time_step_ns=self.config.time_step_ns,
            max_kernel_time_ns=self.config.max_kernel_time_ns,
            self_latency_factor=self.config.self_latency_factor,
            queue_service_time_ms=self.config.queue_service_time_ms,
            decay_type=self.config.decay_type.value,
            normalization=self.config.normalization.value,
        )
        builder = CausalKernelBuilder(self.topology, cpu_config)
        return builder.build_kernel_matrix(components, layers, time_horizon_ns)

    def _build_kernel_matrix_gpu(
        self,
        components: List[str],
        layers: List[BoundaryLayer],
        time_horizon_ns: int,
    ) -> np.ndarray:
        """GPU-accelerated kernel matrix construction."""
        # For now, fall back to CPU for matrix construction
        # Full GPU implementation would require custom CUDA kernels for sparse matrix assembly
        logger.info("Kernel matrix construction on GPU not yet implemented, using CPU")
        return self._build_kernel_matrix_cpu(components, layers, time_horizon_ns)

    def verify_causality(self) -> Dict[str, bool]:
        """Verify kernel causality properties."""
        # CPU version is fast enough for verification
        from .heu_kernel import CausalKernelBuilder, KernelConfig as CPUConfig

        cpu_config = CPUConfig(
            time_step_ns=self.config.time_step_ns,
            max_kernel_time_ns=self.config.max_kernel_time_ns,
            self_latency_factor=self.config.self_latency_factor,
            queue_service_time_ms=self.config.queue_service_time_ms,
            decay_type=self.config.decay_type.value,
            normalization=self.config.normalization.value,
        )
        builder = CausalKernelBuilder(self.topology, cpu_config)
        return builder.verify_causality()


def create_gpu_kernel_builder(
    topology: SystemTopology,
    config: Optional[GPUConfig] = None,
) -> GPUAcceleratedKernelBuilder:
    """
    Factory function to create GPU-accelerated kernel builder.

    Args:
        topology: System topology
        config: GPU configuration

    Returns:
        GPUAcceleratedKernelBuilder instance
    """
    return GPUAcceleratedKernelBuilder(topology, config)


def is_gpu_available() -> bool:
    """Check if GPU acceleration is available."""
    return GPU_AVAILABLE


def get_gpu_info() -> Dict[str, Any]:
    """Get GPU device information."""
    if not GPU_AVAILABLE:
        return {"available": False}

    try:
        import pycuda.driver as cuda
        cuda.init()
        device = cuda.Device(0)
        return {
            "available": True,
            "device_name": device.name(),
            "compute_capability": f"{device.compute_capability()[0]}.{device.compute_capability()[1]}",
            "total_memory_mb": device.total_memory() // (1024 * 1024),
        }
    except Exception as e:
        return {"available": False, "error": str(e)}

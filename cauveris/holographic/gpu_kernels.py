"""
GPU-accelerated holographic causal kernels.

This module is a drop-in replacement for the NumPy implementation in
``heu_kernel.py``.  The CUDA extension evaluates exactly the same Green's
functions as the reference implementation: the *policy* of the model (the
characteristic time of every component and boundary layer) stays in Python,
and the extension only evaluates and convolves.  That split is deliberate -
a second copy of the policy in CUDA would be a second place for the two
paths to drift apart, and the GPU would then answer a slightly different
question than the CPU.

``tests/holographic/test_gpu_kernels.py`` checks that the two paths agree.

The GPU is optional.  Without the compiled extension - or without a CUDA
device - everything falls back to the NumPy reference implementation, and
``get_gpu_info()`` says which of the two is in play and why.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .topology import SystemTopology
from .heu_kernel import (
    CrossPropagationKernel,
    LocalPropagationKernel,
    compute_local_tau_ns,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The compiled extension
# ---------------------------------------------------------------------------

try:  # pragma: no cover - depends on the machine the package runs on
    import cauveris_kernels_py as _kernels

    EXTENSION_AVAILABLE = True
    _IMPORT_ERROR: Optional[BaseException] = None
except ImportError as exc:  # pragma: no cover - depends on the machine
    _kernels = None
    EXTENSION_AVAILABLE = False
    _IMPORT_ERROR = exc
    logger.info("CUDA extension not available, the kernel engine runs on the CPU: %s", exc)


@lru_cache(maxsize=1)
def _device_count() -> int:
    """Number of CUDA devices the CUDA runtime can see."""
    if not EXTENSION_AVAILABLE:
        return 0
    try:
        return int(_kernels.device_count())
    except Exception as exc:  # pragma: no cover - depends on the driver
        logger.warning("The CUDA runtime could not be queried: %s", exc)
        return 0


def is_gpu_available() -> bool:
    """True when the compiled extension is present *and* a CUDA device exists."""
    return EXTENSION_AVAILABLE and _device_count() > 0


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
    """Configuration for the kernel engine."""

    time_step_ns: int = 1_000_000  # 1ms resolution
    max_kernel_time_ns: int = 10_000_000_000  # 10 second max propagation
    self_latency_factor: float = 0.1
    queue_service_time_ms: float = 0.5
    decay_type: DecayType = DecayType.EXPONENTIAL
    normalization: NormalizationType = NormalizationType.L1
    use_gpu: bool = True
    gpu_device_id: int = 0

    @property
    def num_steps(self) -> int:
        """Number of samples on the time axis."""
        return len(
            np.arange(0, self.max_kernel_time_ns, self.time_step_ns, dtype=np.float64)
        )

    def to_cpp_config(self):
        """Translate into the configuration object of the CUDA extension."""
        if not EXTENSION_AVAILABLE:
            raise RuntimeError(
                "the cauveris_kernels_py extension is not installed, so there is no "
                "GPU configuration to build"
            )
        decay_map = {
            DecayType.EXPONENTIAL: _kernels.DecayType.EXPONENTIAL,
            DecayType.GAMMA: _kernels.DecayType.GAMMA,
            DecayType.BI_EXPONENTIAL: _kernels.DecayType.BI_EXPONENTIAL,
        }
        norm_map = {
            NormalizationType.L1: _kernels.NormalizationType.L1_NORM,
            NormalizationType.L2: _kernels.NormalizationType.L2_NORM,
            NormalizationType.MAX: _kernels.NormalizationType.MAX_NORM,
        }
        config = _kernels.PropagationConfig()
        config.time_step_ns = float(self.time_step_ns)
        config.num_steps = int(self.num_steps)
        config.max_time_ns = float(self.max_kernel_time_ns)
        config.decay_type = decay_map[self.decay_type]
        config.normalization = norm_map[self.normalization]
        # These three are the values the reference implementation uses.
        config.gamma_shape = 2.0
        config.biexp_alpha = 0.7
        config.biexp_fast_ratio = 0.1
        return config

    def to_cpu_config(self):
        """Translate into the configuration object of the NumPy reference."""
        from .heu_kernel import KernelConfig

        return KernelConfig(
            time_step_ns=self.time_step_ns,
            max_kernel_time_ns=self.max_kernel_time_ns,
            self_latency_factor=self.self_latency_factor,
            queue_service_time_ms=self.queue_service_time_ms,
            decay_type=self.decay_type.value,
            normalization=self.normalization.value,
        )


def _layer_key(layer: Any) -> str:
    """The plain string of a boundary layer, whichever form it arrives in."""
    return getattr(layer, "value", layer)


class GPUAcceleratedKernelBuilder:
    """
    Builds causal propagation kernels, on the GPU when that is possible.

    The public surface is the one of :class:`~cauveris.holographic.heu_kernel.CausalKernelBuilder`
    so that the two can be swapped without the callers noticing.
    """

    def __init__(
        self,
        topology: SystemTopology,
        config: Optional[GPUConfig] = None,
    ):
        self.topology = topology
        self.config = config or GPUConfig()
        self._local_kernels: Dict[Tuple[str, str], LocalPropagationKernel] = {}
        self._cross_kernels: Dict[Tuple[str, str, str, str], CrossPropagationKernel] = {}
        self._use_gpu = self.config.use_gpu and is_gpu_available()

        if self._use_gpu:
            logger.info(
                "Building causal kernels on the CUDA device %d", self.config.gpu_device_id
            )
        elif self.config.use_gpu:
            logger.info(
                "No usable CUDA device, building causal kernels with the NumPy reference"
            )
        else:
            logger.info("GPU acceleration disabled, building causal kernels with NumPy")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_all_kernels(self) -> Dict:
        """
        Build all propagation kernels for all components and boundary layers.

        Returns:
            Dict with 'local' and 'cross' kernel mappings.
        """
        self._local_kernels.clear()
        self._cross_kernels.clear()

        if self._use_gpu:
            result = self._build_all_kernels_gpu()
        else:
            result = self._build_all_kernels_cpu()

        # Keep the built kernels on self as well: consumers (e.g. the
        # counterfactual forward projection) read `kernel_builder._local_kernels`
        # after calling build_all_kernels().
        self._local_kernels = result.get("local", {})
        self._cross_kernels = result.get("cross", {})
        return result

    def get_local_kernel(
        self, component: str, layer: Any
    ) -> Optional[LocalPropagationKernel]:
        """Get local propagation kernel for component+layer."""
        return self._local_kernels.get((component, _layer_key(layer)))

    def get_cross_kernel(
        self,
        source: str,
        target: str,
        src_layer: Any = "application_log",
        dst_layer: Any = "application_log",
    ) -> Optional[CrossPropagationKernel]:
        """Get cross-component propagation kernel."""
        return self._cross_kernels.get(
            (source, target, _layer_key(src_layer), _layer_key(dst_layer))
        )

    def build_kernel_matrix(
        self,
        components: List[str],
        layers: List[Any],
        time_horizon_ns: int,
    ) -> np.ndarray:
        """
        Build full kernel matrix K for the measurement system.

        K[i, j, t] = how component j's state affects component i's boundary
        at layer l at time t.
        """
        if not self._local_kernels:
            self.build_all_kernels()

        n_comp = len(components)
        n_layers = len(layers)
        n_time = time_horizon_ns // self.config.time_step_ns
        n_rows = n_comp * n_layers

        comp_to_idx = {c: i for i, c in enumerate(components)}
        layer_to_idx = {_layer_key(layer): i for i, layer in enumerate(layers)}

        # The matrix is filled pair by pair: every local kernel writes into
        # the diagonal block of its own component, every cross kernel into
        # the block of the observable it reaches.
        #
        # A slot can be reached by more than one kernel: every edge into a
        # component carries one cross kernel per source layer, and they all
        # land on the same observable when the observable layer is the same.
        # The reference implementation resolves that by assignment - the
        # last kernel written wins.  The slots are therefore collected in a
        # mapping here, so that the device receives exactly one kernel per
        # slot and never has two threads writing the same address.
        slots: Dict[Tuple[int, int], np.ndarray] = {}

        for i, comp in enumerate(components):
            for l_idx, layer in enumerate(layers):
                kernel = self.get_local_kernel(comp, layer)
                if kernel is None:
                    continue
                slots[(i * n_layers + l_idx, i)] = kernel.kernel_values

        for edge in self.topology.causal_edges:
            if edge.source not in comp_to_idx or edge.target not in comp_to_idx:
                continue
            src_comp = self.topology.components[edge.source]
            dst_comp = self.topology.components[edge.target]
            for src_layer in src_comp.boundary_layers:
                for dst_layer in dst_comp.boundary_layers:
                    kernel = self.get_cross_kernel(
                        edge.source, edge.target, src_layer, dst_layer
                    )
                    if kernel is None:
                        continue
                    dst_obs_idx = (
                        comp_to_idx[edge.target] * n_layers
                        + layer_to_idx.get(_layer_key(dst_layer), 0)
                    )
                    slots[(dst_obs_idx, comp_to_idx[edge.source])] = kernel.kernel_values

        if not slots:
            return np.zeros((n_rows, n_comp, n_time), dtype=np.float32)

        values: List[np.ndarray] = list(slots.values())
        rows: List[int] = [key[0] for key in slots]
        cols: List[int] = [key[1] for key in slots]

        num_steps = max(len(v) for v in values)
        flat = np.concatenate(
            [
                np.pad(v, (0, num_steps - len(v)), mode="constant") if len(v) < num_steps else v
                for v in values
            ]
        ).astype(np.float32)

        if self._use_gpu:
            return _kernels.assemble_kernel_matrix(
                flat,
                np.asarray(rows, dtype=np.int32),
                np.asarray(cols, dtype=np.int32),
                int(num_steps),
                int(n_time),
                int(n_rows),
                int(n_comp),
            )
        return _assemble_kernel_matrix_numpy(
            flat, rows, cols, num_steps, n_time, n_rows, n_comp
        )

    def verify_causality(self) -> Dict[str, bool]:
        """
        Verify the causal properties of the built kernels.

        The checks are the same as the ones the reference implementation
        makes; they read the kernels, they do not need the GPU.
        """
        no_anticipation = True
        conservation = True
        peak_ordering = True

        for kernel in self._local_kernels.values():
            # No anticipation: the kernel must be zero before it starts.
            if np.any(kernel.kernel_values[:10] > 1e-6):
                no_anticipation = False
            # Conservation: the integral of a normalized kernel is one.
            if abs(kernel.integral - 1.0) > 0.15:
                conservation = False

        for (src, dst, src_layer, dst_layer), cross in self._cross_kernels.items():
            src_local = self._local_kernels.get((src, src_layer))
            dst_local = self._local_kernels.get((dst, dst_layer))
            if src_local and dst_local:
                if cross.total_latency_ns < (
                    src_local.peak_time_ns + dst_local.peak_time_ns
                ):
                    peak_ordering = False

        return {
            "no_anticipation": no_anticipation,
            "conservation": conservation,
            "peak_ordering": peak_ordering,
        }

    # ------------------------------------------------------------------
    # CPU path
    # ------------------------------------------------------------------

    def _build_all_kernels_cpu(self) -> Dict:
        """Build the kernels with the NumPy reference implementation."""
        from .heu_kernel import CausalKernelBuilder

        builder = CausalKernelBuilder(self.topology, self.config.to_cpu_config())
        return builder.build_all_kernels()

    # ------------------------------------------------------------------
    # GPU path
    # ------------------------------------------------------------------

    def _local_pairs(self) -> List[Tuple[str, str]]:
        """The (component, layer) pairs the topology actually exposes."""
        pairs: List[Tuple[str, str]] = []
        for comp_name, comp in self.topology.components.items():
            for layer in comp.boundary_layers:
                pairs.append((comp_name, _layer_key(layer)))
        return pairs

    def _build_all_kernels_gpu(self) -> Dict:
        """Build the local and cross kernels on the CUDA device."""
        config = self.config.to_cpp_config()
        device_id = self.config.gpu_device_id
        num_steps = int(self.config.num_steps)
        time_axis = np.arange(
            0, self.config.max_kernel_time_ns, self.config.time_step_ns, dtype=np.float64
        )

        pairs = self._local_pairs()
        if not pairs:
            return {"local": {}, "cross": {}}

        # The characteristic time of every pair comes from the reference
        # implementation, so the GPU and the CPU describe the same physics.
        tau = np.asarray(
            [
                compute_local_tau_ns(
                    self.topology.components[name].component_type, layer
                )
                for name, layer in pairs
            ],
            dtype=np.float64,
        )

        kernels, integral, peak_time, half_life = _kernels.build_local_kernels(
            tau, config, device_id
        )

        local_kernels: Dict[Tuple[str, str], LocalPropagationKernel] = {}
        for index, (name, layer) in enumerate(pairs):
            start = index * num_steps
            local_kernels[(name, layer)] = LocalPropagationKernel(
                component_name=self.topology.components[name].name,
                boundary_layer=layer,
                time_axis_ns=time_axis,
                kernel_values=np.array(
                    kernels[start : start + num_steps], dtype=np.float32
                ),
                integral=float(integral[index]),
                peak_time_ns=float(peak_time[index]),
                half_life_ns=float(half_life[index]),
            )

        cross_kernels = self._build_cross_kernels_gpu(local_kernels, config, device_id)

        return {"local": local_kernels, "cross": cross_kernels}

    def _build_cross_kernels_gpu(
        self,
        local_kernels: Dict[Tuple[str, str], LocalPropagationKernel],
        config,
        device_id: int,
    ) -> Dict[Tuple[str, str, str, str], CrossPropagationKernel]:
        """
        Convolve the local kernels into the cross kernels, on the device.

        The cross kernel of an edge is the transport of the source's local
        kernel to the target's boundary: the source kernel is delayed by the
        network and queueing latency of the edge and then convolved with the
        local kernel of the target.
        """
        dt = self.config.time_step_ns
        queue_service_time_ms = self.config.queue_service_time_ms

        src_chunks: List[np.ndarray] = []
        dst_chunks: List[np.ndarray] = []
        shifts: List[int] = []
        metadata: List[Dict[str, Any]] = []

        for edge in self.topology.causal_edges:
            if edge.source not in self.topology.components:
                continue
            if edge.target not in self.topology.components:
                continue
            src_comp = self.topology.components[edge.source]
            dst_comp = self.topology.components[edge.target]

            network_latency_ns = edge.latency_ms * 1_000_000
            queueing_latency_ns = edge.queue_depth * queue_service_time_ms * 1_000_000
            total_network_latency_ns = network_latency_ns + queueing_latency_ns
            shift_steps = int(total_network_latency_ns / dt)

            for src_layer in src_comp.boundary_layers:
                src_kernel = local_kernels.get((edge.source, _layer_key(src_layer)))
                if src_kernel is None:
                    continue
                for dst_layer in dst_comp.boundary_layers:
                    dst_kernel = local_kernels.get((edge.target, _layer_key(dst_layer)))
                    if dst_kernel is None:
                        continue
                    src_chunks.append(src_kernel.kernel_values)
                    dst_chunks.append(dst_kernel.kernel_values)
                    shifts.append(shift_steps)
                    metadata.append(
                        {
                            "edge": edge,
                            "src_layer": _layer_key(src_layer),
                            "dst_layer": _layer_key(dst_layer),
                            "src_kernel": src_kernel,
                            "dst_kernel": dst_kernel,
                            "network_latency_ns": network_latency_ns,
                            "queueing_latency_ns": queueing_latency_ns,
                            "total_network_latency_ns": total_network_latency_ns,
                        }
                    )

        if not metadata:
            return {}

        num_steps = int(self.config.num_steps)
        src_stack = np.concatenate(src_chunks).astype(np.float32)
        dst_stack = np.concatenate(dst_chunks).astype(np.float32)

        cross_values = _kernels.build_cross_kernels(
            src_stack,
            dst_stack,
            np.asarray(shifts, dtype=np.int32),
            config,
            device_id,
        )

        cross_kernels: Dict[Tuple[str, str, str, str], CrossPropagationKernel] = {}
        time_axis = np.arange(
            0, self.config.max_kernel_time_ns, self.config.time_step_ns, dtype=np.float64
        )
        for index, meta in enumerate(metadata):
            edge = meta["edge"]
            src_kernel = meta["src_kernel"]
            dst_kernel = meta["dst_kernel"]
            start = index * num_steps
            cross_kernels[
                (edge.source, edge.target, meta["src_layer"], meta["dst_layer"])
            ] = CrossPropagationKernel(
                source=edge.source,
                target=edge.target,
                edge_type=edge.edge_type,
                time_axis_ns=time_axis,
                kernel_values=np.array(
                    cross_values[start : start + num_steps], dtype=np.float32
                ),
                total_latency_ns=(
                    src_kernel.peak_time_ns
                    + meta["total_network_latency_ns"]
                    + dst_kernel.peak_time_ns
                ),
                network_latency_ns=meta["network_latency_ns"],
                queueing_latency_ns=meta["queueing_latency_ns"],
            )
        return cross_kernels


def _assemble_kernel_matrix_numpy(
    flat: np.ndarray,
    rows: List[int],
    cols: List[int],
    num_steps: int,
    n_time: int,
    n_rows: int,
    n_cols: int,
) -> np.ndarray:
    """The CPU equivalent of the device side matrix assembly."""
    matrix = np.zeros((n_rows, n_cols, n_time), dtype=np.float32)
    count = min(num_steps, n_time)
    for index, (row, col) in enumerate(zip(rows, cols)):
        values = flat[index * num_steps : index * num_steps + count]
        matrix[row, col, :count] = values
    return matrix


def create_gpu_kernel_builder(
    topology: SystemTopology,
    config: Optional[GPUConfig] = None,
) -> GPUAcceleratedKernelBuilder:
    """
    Create a kernel builder that uses the GPU when that is possible.

    Args:
        topology: System topology
        config: GPU configuration

    Returns:
        GPUAcceleratedKernelBuilder instance
    """
    return GPUAcceleratedKernelBuilder(topology, config)


def _query_nvidia_smi() -> Dict[str, Any]:
    """
    Ask the driver about the GPU without going through CUDA.

    Used when the extension cannot reach a device: the driver may still know
    about one, and saying "there is a driver but no usable device" is more
    useful than "no information at all".
    """
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {}
    query = (
        "name,compute_cap,memory.total,driver_version",
    )
    try:
        completed = subprocess.run(
            [
                executable,
                f"--query-gpu={query}",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("nvidia-smi could not be run: %s", exc)
        return {}
    lines = [line for line in completed.stdout.strip().splitlines() if line.strip()]
    if not lines:
        return {}
    fields = [field.strip() for field in lines[0].split(",")]
    if len(fields) < 4:
        return {}
    try:
        memory_mb = int(float(fields[2]))
    except ValueError:
        memory_mb = 0
    return {
        "device_name": fields[0],
        "compute_capability": fields[1],
        "total_memory_mb": memory_mb,
        "driver_version": fields[3],
        "source": "nvidia-smi",
    }


def get_gpu_info() -> Dict[str, Any]:
    """
    Describe the GPU the engine would run on.

    The answer comes from the CUDA runtime itself when the extension is
    available, and from the driver otherwise.  When there is no usable
    device, the reason is included - "no GPU" and "the extension is not
    installed" are different problems with different fixes.
    """
    if not EXTENSION_AVAILABLE:
        info: Dict[str, Any] = {"available": False}
        info["reason"] = "the cauveris_kernels_py extension is not installed"
        if _IMPORT_ERROR is not None:
            info["detail"] = str(_IMPORT_ERROR)
        driver = _query_nvidia_smi()
        if driver:
            info["driver"] = driver
        return info

    count = _device_count()
    if count <= 0:
        info = {"available": False}
        info["reason"] = "the CUDA runtime reports no usable device"
        driver = _query_nvidia_smi()
        if driver:
            info["driver"] = driver
        return info

    try:
        details = _kernels.device_info(0)
    except Exception as exc:  # pragma: no cover - depends on the driver
        return {"available": False, "reason": "the CUDA runtime failed", "detail": str(exc)}

    if details is None:
        return {
            "available": False,
            "reason": "the CUDA runtime reports no usable device",
        }

    info = dict(details)
    info["available"] = True
    info["device_count"] = count
    info["device_name"] = info.get("name", "unknown")
    info["total_memory_mb"] = int(info.get("total_memory_bytes", 0)) // (1024 * 1024)
    info["source"] = "cuda_runtime"
    return info

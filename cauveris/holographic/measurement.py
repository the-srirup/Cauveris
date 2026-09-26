"""
Holographic Measurement System - Linear operators M·x = b.

Implements the forward model that maps internal system state (bulk) to
boundary observations (HEUs). This is the measurement operator in the
holographic inverse problem.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .heu import HolographicEvidenceUnit, BoundaryLayer, convert_timeline_to_heus
from .topology import SystemTopology, ComponentInfo, CausalEdge
from .heu_kernel import CausalKernelBuilder


@dataclass(slots=True)
class StateDimension:
    """Maps a (component, dimension) pair to a state vector index."""
    component: str
    dimension: str  # cpu, memory, network, error, config, deploy, queue, etc.
    index: int

    def __str__(self) -> str:
        return f"{self.component}.{self.dimension}"


@dataclass(slots=True)
class MeasurementRow:
    """One row of the measurement matrix M (one HEU observation)."""
    heu_id: str
    boundary_layer: BoundaryLayer
    component: str
    dimension: str  # What state dimension this observation informs
    state_indices: List[int]  # Indices in state vector x
    coefficients: np.ndarray   # M[row, state_indices] values
    timestamp_ns: int
    observation_value: float   # Normalized observation b[row]
    noise_std: float = 0.1     # Expected noise standard deviation


@dataclass(slots=True)
class MeasurementSystem:
    """
    Complete measurement system M·x = b for holographic reconstruction.

    M: sparse measurement matrix (n_observations × n_state_dims)
    b: observation vector (n_observations)
    x: state vector (n_state_dims) - what we solve for
    """
    # Sparse measurement matrix
    M: sp.csr_matrix
    b: np.ndarray                    # Observation vector
    state_dims: List[StateDimension] # Mapping from state index to (component, dimension)
    measurements: List[MeasurementRow] # Per-observation metadata
    n_state: int                     # Total state dimensions
    n_obs: int                       # Total observations

    # Normalization info
    state_scales: Dict[int, float] = field(default_factory=dict)  # Per-dimension scaling
    obs_scales: Dict[int, float] = field(default_factory=dict)    # Per-observation scaling

    def to_dense(self) -> Tuple[np.ndarray, np.ndarray]:
        """Convert to dense arrays (for small systems or debugging)."""
        return self.M.toarray(), self.b.copy()

    def get_state_slice(self, component: str, dimension: str = None) -> np.ndarray:
        """Get indices for a specific component/dimension."""
        indices = []
        for i, sd in enumerate(self.state_dims):
            if sd.component == component and (dimension is None or sd.dimension == dimension):
                indices.append(i)
        return np.array(indices, dtype=int)

    def get_observations_for_component(self, component: str) -> List[MeasurementRow]:
        """Get all measurement rows for a component."""
        return [m for m in self.measurements if m.component == component]


class MeasurementSystemBuilder:
    """
    Builds the measurement system from HEUs, topology, and causal kernels.
    """

    def __init__(
        self,
        topology: SystemTopology,
        kernels: CausalKernelBuilder,
        config: Optional["MeasurementConfig"] = None,
    ):
        self.topology = topology
        self.kernels = kernels
        self.config = config or MeasurementConfig()

        # State dimension registry
        self._state_dims: List[StateDimension] = []
        self._state_index: Dict[Tuple[str, str], int] = {}  # (component, dimension) -> index

        # Predefined state dimensions per component
        self._base_dimensions = [
            "cpu_pressure",      # 0-1: CPU utilization / saturation
            "memory_pressure",   # 0-1: Memory utilization / saturation
            "network_latency",   # 0-1: Normalized latency (ms / 1000)
            "error_rate",        # 0-1: Error rate
            "config_change",     # 0-1: Configuration drift magnitude
            "deployment_activity", # 0-1: Active deployment coupling
            "resource_contention", # 0-1: Generic resource contention
            "service_dependency",  # 0-1: Downstream dependency pressure
        ]

    def build(
        self,
        heus: List[HolographicEvidenceUnit],
        incident_duration_ns: int,
    ) -> MeasurementSystem:
        """
        Build measurement system from HEUs.

        Args:
            heus: List of holographic evidence units
            incident_duration_ns: Total incident time window

        Returns:
            MeasurementSystem with M, b, and metadata
        """
        if not heus:
            return self._empty_system()

        # 1. Register all state dimensions seen in HEUs
        self._register_state_dimensions(heus)

        # 2. Build measurement rows for each HEU
        rows = []
        for heu in heus:
            row = self._build_measurement_row(heu, incident_duration_ns)
            if row is not None:
                rows.append(row)

        if not rows:
            return self._empty_system()

        # 3. Assemble sparse matrix M and vector b
        M, b, scales = self._assemble_matrix(rows)

        return MeasurementSystem(
            M=M,
            b=b,
            state_dims=self._state_dims,
            measurements=rows,
            n_state=len(self._state_dims),
            n_obs=len(rows),
            state_scales=scales[0],
            obs_scales=scales[1],
        )

    def _register_state_dimensions(self, heus: List[HolographicEvidenceUnit]) -> None:
        """Register all state dimensions from components and HEU encoded dimensions."""
        # Add base dimensions for each component
        for comp_name in self.topology.components:
            for dim in self._base_dimensions:
                self._get_or_create_state_index(comp_name, dim)

        # Add dimensions from HEU encoded_dimensions
        for heu in heus:
            comp = heu.source_component
            for dim in heu.encoded_dimensions:
                self._get_or_create_state_index(comp, dim)

    def _get_or_create_state_index(self, component: str, dimension: str) -> int:
        """Get or create state index for (component, dimension)."""
        key = (component, dimension)
        if key not in self._state_index:
            idx = len(self._state_dims)
            self._state_index[key] = idx
            self._state_dims.append(StateDimension(component, dimension, idx))
        return self._state_index[key]

    def _build_measurement_row(
        self,
        heu: HolographicEvidenceUnit,
        incident_duration_ns: int,
    ) -> Optional[MeasurementRow]:
        """Build measurement row(s) for a single HEU."""
        # Map HEU to which state dimensions it observes
        observed_dims = self._map_heu_to_state_dims(heu)
        if not observed_dims:
            return None

        # Normalize observation value from HEU payload
        obs_value = self._normalize_observation(heu)
        if obs_value is None:
            obs_value = 0.5  # Default mid-range

        # Build coefficients from encoded dimensions
        state_indices = []
        coefficients = []

        # Weight by reconstruction weight and kernel response
        weight = heu.reconstruction_weight

        for dim_name, dim_weight in heu.encoded_dimensions.items():
            idx = self._state_index.get((heu.source_component, dim_name))
            if idx is not None:
                state_indices.append(idx)
                # Coefficient combines encoded_dim weight, reconstruction weight, phase
                coeff = dim_weight * weight * (1.0 - heu.ambiguity_score)
                coefficients.append(coeff)

        if not state_indices:
            return None

        # If single observation informs multiple dimensions, distribute
        # For now, we create one row per state dimension informed
        rows = []
        for i, (idx, coeff) in enumerate(zip(state_indices, coefficients)):
            row = MeasurementRow(
                heu_id=f"{heu.heu_id}_dim{i}",
                boundary_layer=heu.boundary_layer,
                component=heu.source_component,
                dimension=list(heu.encoded_dimensions.keys())[i],
                state_indices=[idx],
                coefficients=np.array([coeff], dtype=np.float32),
                timestamp_ns=heu.timestamp_ns,
                observation_value=obs_value,
                noise_std=self._estimate_noise_std(heu),
            )
            rows.append(row)

        # For simplicity, return first row (we'll combine in assemble)
        # Actually, let's return a combined row for this HEU
        combined = MeasurementRow(
            heu_id=heu.heu_id,
            boundary_layer=heu.boundary_layer,
            component=heu.source_component,
            dimension="multi",  # Informs multiple dimensions
            state_indices=state_indices,
            coefficients=np.array(coefficients, dtype=np.float32),
            timestamp_ns=heu.timestamp_ns,
            observation_value=obs_value,
            noise_std=self._estimate_noise_std(heu),
        )
        return combined

    def _map_heu_to_state_dims(self, heu: HolographicEvidenceUnit) -> List[str]:
        """Map HEU's boundary layer and encoded dims to state dimensions."""
        # Direct mapping from encoded_dimensions
        return list(heu.encoded_dimensions.keys())

    def _normalize_observation(self, heu: HolographicEvidenceUnit) -> Optional[float]:
        """Normalize HEU payload to [0,1] observation value."""
        payload = heu.payload

        # Try various payload fields
        if "cpu_usage" in payload:
            val = payload["cpu_usage"]
            if isinstance(val, (int, float)):
                return float(np.clip(val, 0, 1))

        if "memory_usage" in payload:
            val = payload["memory_usage"]
            if isinstance(val, (int, float)):
                return float(np.clip(val, 0, 1))

        if "duration_ns" in payload:
            val = payload["duration_ns"]
            if isinstance(val, (int, float)) and val > 0:
                # Normalize: 1ms -> 0.001, 1s -> 1.0
                return float(np.clip(val / 1_000_000_000, 0, 1))

        if "latency_ms" in payload:
            val = payload["latency_ms"]
            if isinstance(val, (int, float)) and val > 0:
                return float(np.clip(val / 1000, 0, 1))

        # Log level based
        if "level" in payload:
            level = str(payload["level"]).upper()
            mapping = {"DEBUG": 0.0, "INFO": 0.1, "WARN": 0.3, "WARNING": 0.3,
                       "ERROR": 0.7, "FATAL": 0.9, "CRITICAL": 1.0}
            return mapping.get(level, 0.5)

        # Status based
        if "status" in payload:
            status = str(payload["status"]).lower()
            mapping = {"ok": 0.0, "success": 0.0, "warning": 0.3, "warn": 0.3,
                       "error": 0.7, "failed": 0.8, "fatal": 1.0}
            return mapping.get(status, 0.5)

        return None

    def _estimate_noise_std(self, heu: HolographicEvidenceUnit) -> float:
        """Estimate observation noise standard deviation for this HEU."""
        # Base noise by boundary layer
        layer_noise = {
            BoundaryLayer.DISTRIBUTED_TRACE: 0.05,   # Low noise, precise timestamps
            BoundaryLayer.METRICS_EXPORT: 0.1,       # Aggregated, some noise
            BoundaryLayer.APPLICATION_LOG: 0.15,     # Structured logs, moderate
            BoundaryLayer.INFRASTRUCTURE_LOG: 0.25,  # Mixed sources
            BoundaryLayer.CONFIG_STATE: 0.1,         # Sparse but precise
            BoundaryLayer.DEPLOYMENT_EVENT: 0.05,    # Clear events
            BoundaryLayer.NETWORK_FLOW: 0.2,         # Sampled flow data
        }
        base = layer_noise.get(heu.boundary_layer, 0.15)

        # Increase noise with ambiguity
        noise = base * (1.0 + heu.ambiguity_score)

        # Decrease noise with reconstruction weight
        noise = noise / (0.5 + heu.reconstruction_weight)

        return float(np.clip(noise, 0.01, 0.5))

    def _assemble_matrix(
        self,
        rows: List[MeasurementRow],
    ) -> Tuple[sp.csr_matrix, np.ndarray, Tuple[Dict[int, float], Dict[int, float]]]:
        """Assemble sparse measurement matrix and observation vector."""
        n_obs = len(rows)
        n_state = len(self._state_dims)

        # Build in COO format then convert to CSR
        row_indices = []
        col_indices = []
        data = []
        b = np.zeros(n_obs, dtype=np.float32)

        obs_scales = {}
        state_scales = defaultdict(list)

        for i, row in enumerate(rows):
            b[i] = row.observation_value
            obs_scales[i] = 1.0 / max(row.noise_std, 1e-6)  # Weight by inverse noise

            for j, idx in enumerate(row.state_indices):
                if idx < n_state:
                    row_indices.append(i)
                    col_indices.append(idx)
                    data.append(row.coefficients[j] if j < len(row.coefficients) else 1.0)
                    state_scales[idx].append(abs(row.coefficients[j]) if j < len(row.coefficients) else 1.0)

        M = sp.csr_matrix((data, (row_indices, col_indices)), shape=(n_obs, n_state), dtype=np.float32)

        # Compute per-dimension scales (max coefficient magnitude)
        final_state_scales = {}
        for idx, vals in state_scales.items():
            final_state_scales[idx] = max(vals) if vals else 1.0

        return M, b, (final_state_scales, obs_scales)

    def _empty_system(self) -> MeasurementSystem:
        """Return empty measurement system."""
        return MeasurementSystem(
            M=sp.csr_matrix((0, 0), dtype=np.float32),
            b=np.array([], dtype=np.float32),
            state_dims=[],
            measurements=[],
            n_state=0,
            n_obs=0,
        )


@dataclass
class MeasurementConfig:
    """Configuration for measurement system builder."""
    include_cross_component: bool = True      # Include cross-propagation effects
    time_window_ns: int = 60_000_000_000      # 60 second window for temporal context
    min_reconstruction_weight: float = 0.1    # Filter low-weight HEUs
    max_observations: int = 10000             # Cap for performance


def build_measurement_system(
    topology: SystemTopology,
    heus: List[HolographicEvidenceUnit],
    incident_duration_ns: int,
    kernels: Optional[CausalKernelBuilder] = None,
    config: Optional[MeasurementConfig] = None,
) -> MeasurementSystem:
    """
    Convenience function to build measurement system.

    Args:
        topology: System topology
        heus: Holographic evidence units
        incident_duration_ns: Incident duration
        kernels: Pre-built causal kernels (optional)
        config: Measurement configuration

    Returns:
        Complete measurement system
    """
    if kernels is None:
        kernels = CausalKernelBuilder(topology)
        kernels.build_all_kernels()

    builder = MeasurementSystemBuilder(topology, kernels, config)
    return builder.build(heus, incident_duration_ns)


if __name__ == "__main__":
    # Quick test
    from .topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge
    from .heu import HolographicEvidenceUnit, BoundaryLayer, convert_timeline_to_heus

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

    from .heu_kernel import CausalKernelBuilder
    kernel_builder = CausalKernelBuilder(topo)
    kernel_builder.build_all_kernels()

    system = build_measurement_system(topo, heus, 1_000_000_000, kernel_builder)
    print(f"Measurement system: {system.n_obs} obs, {system.n_state} state dims")
    print(f"State dims: {[str(s) for s in system.state_dims[:10]]}")
    print(f"M shape: {system.M.shape}, nnz: {system.M.nnz}")

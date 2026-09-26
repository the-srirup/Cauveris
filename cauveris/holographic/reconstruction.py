"""
Holographic Reconstruction data structures.

Contains the structured output of the holographic reconstruction engine:
reconstructed service states, network state, resource state, and ambiguity regions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

import numpy as np


@dataclass(slots=True)
class ReconstructedServiceState:
    """
    Reconstructed internal state of a single service/component.

    This represents the "bulk" state inferred from boundary evidence.
    All values are normalized to [0, 1] where 1.0 = maximum observed/expected.
    """
    component_name: str
    instance_id: str

    # Resource utilization (normalized)
    cpu_usage: float = 0.0          # 0=idle, 1=saturated
    memory_usage: float = 0.0       # 0=empty, 1=OOM risk
    network_usage: float = 0.0      # 0=idle, 1=saturated

    # Error/health state
    error_rate: float = 0.0         # 0=no errors, 1=constant errors
    latency_p99_ms: float = 0.0     # Reconstructed P99 latency

    # Configuration state
    config_version: str = ""
    config_changed_recently: bool = False

    # Deployment state
    deployment_version: str = ""
    deployment_time_ns: int = 0

    # Dependency health
    upstream_health: Dict[str, float] = field(default_factory=dict)  # service -> health [0,1]
    downstream_health: Dict[str, float] = field(default_factory=dict)

    # Reconstruction quality
    confidence: float = 0.0         # Overall confidence in this reconstruction [0,1]
    coverage: float = 0.0          # Boundary layer coverage [0,1]
    contributing_heus: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Clamp all float fields to [0,1]
        for field_name in ("cpu_usage", "memory_usage", "network_usage",
                          "error_rate", "confidence", "coverage"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                object.__setattr__(self, field_name, max(0.0, min(1.0, value)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_name": self.component_name,
            "instance_id": self.instance_id,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "network_usage": self.network_usage,
            "error_rate": self.error_rate,
            "latency_p99_ms": self.latency_p99_ms,
            "config_version": self.config_version,
            "config_changed_recently": self.config_changed_recently,
            "deployment_version": self.deployment_version,
            "deployment_time_ns": self.deployment_time_ns,
            "upstream_health": self.upstream_health,
            "downstream_health": self.downstream_health,
            "confidence": self.confidence,
            "coverage": self.coverage,
            "contributing_heus": self.contributing_heus,
        }

    @property
    def is_healthy(self) -> bool:
        """Quick health check based on reconstructed state."""
        return (
            self.cpu_usage < 0.85 and
            self.memory_usage < 0.85 and
            self.error_rate < 0.1 and
            self.confidence > 0.5
        )

    @property
    def primary_bottleneck(self) -> Optional[str]:
        """Identify the primary reconstructed bottleneck."""
        bottlenecks = []
        if self.cpu_usage > 0.8:
            bottlenecks.append(("cpu", self.cpu_usage))
        if self.memory_usage > 0.8:
            bottlenecks.append(("memory", self.memory_usage))
        if self.network_usage > 0.8:
            bottlenecks.append(("network", self.network_usage))
        if self.error_rate > 0.2:
            bottlenecks.append(("errors", self.error_rate))

        if bottlenecks:
            return max(bottlenecks, key=lambda x: x[1])[0]
        return None


@dataclass(slots=True)
class ReconstructedNetworkState:
    """
    Reconstructed network state between services.

    Captures latency, loss, and queue depth for each service-to-service edge.
    """
    edges: Dict[Tuple[str, str], "NetworkEdge"] = field(default_factory=dict)

    def add_edge(self, source: str, target: str, edge: "NetworkEdge") -> None:
        self.edges[(source, target)] = edge

    def get_edge(self, source: str, target: str) -> Optional["NetworkEdge"]:
        return self.edges.get((source, target))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edges": {
                f"{src}->{dst}": edge.to_dict()
                for (src, dst), edge in self.edges.items()
            }
        }


@dataclass(slots=True)
class NetworkEdge:
    """Single service-to-service network connection state."""
    source: str
    target: str
    latency_ms: float = 0.0
    loss_rate: float = 0.0
    queue_depth: float = 0.0
    bandwidth_mbps: float = 0.0
    confidence: float = 0.0

    def __post_init__(self) -> None:
        for field_name in ("loss_rate", "confidence"):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 1.0:
                object.__setattr__(self, field_name, max(0.0, min(1.0, value)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "latency_ms": self.latency_ms,
            "loss_rate": self.loss_rate,
            "queue_depth": self.queue_depth,
            "bandwidth_mbps": self.bandwidth_mbps,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class ReconstructedResourceState:
    """
    Cluster-wide reconstructed resource state.

    Aggregated view of all resources across the system.
    """
    total_cpu_cores: float = 0.0
    total_memory_gb: float = 0.0
    total_network_gbps: float = 0.0

    used_cpu_cores: float = 0.0
    used_memory_gb: float = 0.0
    used_network_gbps: float = 0.0

    # Per-component breakdown
    cpu_by_component: Dict[str, float] = field(default_factory=dict)
    memory_by_component: Dict[str, float] = field(default_factory=dict)

    # Saturation indicators
    cpu_saturated_components: List[str] = field(default_factory=list)
    memory_saturated_components: List[str] = field(default_factory=list)

    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cpu_cores": self.total_cpu_cores,
            "total_memory_gb": self.total_memory_gb,
            "total_network_gbps": self.total_network_gbps,
            "used_cpu_cores": self.used_cpu_cores,
            "used_memory_gb": self.used_memory_gb,
            "used_network_gbps": self.used_network_gbps,
            "cpu_by_component": self.cpu_by_component,
            "memory_by_component": self.memory_by_component,
            "cpu_saturated_components": self.cpu_saturated_components,
            "memory_saturated_components": self.memory_saturated_components,
            "confidence": self.confidence,
        }

    @property
    def cpu_utilization(self) -> float:
        if self.total_cpu_cores <= 0:
            return 0.0
        return self.used_cpu_cores / self.total_cpu_cores

    @property
    def memory_utilization(self) -> float:
        if self.total_memory_gb <= 0:
            return 0.0
        return self.used_memory_gb / self.total_memory_gb


@dataclass(slots=True)
class AmbiguityRegion:
    """
    A region of the reconstruction with high uncertainty.

    Indicates where the boundary evidence was insufficient to uniquely
    determine the bulk state. These are the "dark spots" in the hologram.
    """
    component: str
    time_range_ns: Tuple[int, int]  # (start, end)
    affected_dimensions: List[str]  # e.g., ["cpu_pressure", "memory_pressure"]
    ambiguity_score: float          # 0=certain, 1=completely ambiguous
    missing_layers: List[str]       # Boundary layers not observed
    description: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.ambiguity_score <= 1.0:
            raise ValueError(f"ambiguity_score must be in [0,1], got {self.ambiguity_score}")

    @property
    def duration_ms(self) -> float:
        start, end = self.time_range_ns
        return (end - start) / 1_000_000.0

    def to_dict(self) -> Dict[str, Any]:
        start, end = self.time_range_ns
        return {
            "component": self.component,
            "start_ns": start,
            "end_ns": end,
            "duration_ms": self.duration_ms,
            "affected_dimensions": self.affected_dimensions,
            "ambiguity_score": self.ambiguity_score,
            "missing_layers": self.missing_layers,
            "description": self.description,
        }


@dataclass(slots=True)
class HolographicReconstruction:
    """
    Complete holographic reconstruction result.

    This is the "3D image" reconstructed from the "2D hologram" of boundary HEUs.
    """
    incident_id: str
    reconstruction_timestamp_ns: int
    time_window_ns: Tuple[int, int]  # (start, end) of incident window

    # Reconstructed bulk state
    reconstructed_services: Dict[str, ReconstructedServiceState] = field(default_factory=dict)
    reconstructed_network: Optional[ReconstructedNetworkState] = None
    reconstructed_resources: Optional[ReconstructedResourceState] = None

    # Quality metrics
    overall_fidelity: float = 0.0           # 0-1, overall reconstruction accuracy
    per_component_fidelity: Dict[str, float] = field(default_factory=dict)
    coverage_map: Dict[str, Dict[str, float]] = field(default_factory=dict)  # component -> layer -> coverage
    ambiguity_regions: List[AmbiguityRegion] = field(default_factory=list)
    holographic_entropy: float = 0.0        # Information-theoretic uncertainty
    boundary_residual: float = 0.0          # ||M·x - b|| / ||b||
    constraint_violation: float = 0.0       # Physics constraint satisfaction

    # Evidence used
    boundary_heus: List[str] = field(default_factory=list)  # HEU IDs used
    missing_boundary_layers: List[str] = field(default_factory=list)

    # Observed HEUs grouped by component (for visualization / re-analysis).
    # Typed loosely to avoid a circular import on heu.py.
    observed_heus: Dict[str, List[Any]] = field(default_factory=dict)
    observed_layers: Dict[str, List[Any]] = field(default_factory=dict)  # component -> [BoundaryLayer]

    # Compression metadata
    compression_metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.reconstructed_network is None:
            self.reconstructed_network = ReconstructedNetworkState()
        if self.reconstructed_resources is None:
            self.reconstructed_resources = ReconstructedResourceState()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "reconstruction_timestamp_ns": self.reconstruction_timestamp_ns,
            "time_window_ns": self.time_window_ns,
            "reconstructed_services": {
                k: v.to_dict() for k, v in self.reconstructed_services.items()
            },
            "reconstructed_network": self.reconstructed_network.to_dict() if self.reconstructed_network else {},
            "reconstructed_resources": self.reconstructed_resources.to_dict() if self.reconstructed_resources else {},
            "overall_fidelity": self.overall_fidelity,
            "per_component_fidelity": self.per_component_fidelity,
            "coverage_map": self.coverage_map,
            "ambiguity_regions": [r.to_dict() for r in self.ambiguity_regions],
            "holographic_entropy": self.holographic_entropy,
            "boundary_residual": self.boundary_residual,
            "constraint_violation": self.constraint_violation,
            "boundary_heus": self.boundary_heus,
            "missing_boundary_layers": self.missing_boundary_layers,
            "compression_metadata": self.compression_metadata,
        }

    def get_service(self, component: str) -> Optional[ReconstructedServiceState]:
        """Get reconstructed state for a component (matches by prefix)."""
        for key, state in self.reconstructed_services.items():
            if key.startswith(component) or component in key:
                return state
        return None

    @property
    def unhealthy_services(self) -> List[ReconstructedServiceState]:
        """Get all services reconstructed as unhealthy."""
        return [s for s in self.reconstructed_services.values() if not s.is_healthy]

    @property
    def has_high_ambiguity(self) -> bool:
        """Check if any region has high ambiguity (>0.7)."""
        return any(r.ambiguity_score > 0.7 for r in self.ambiguity_regions)
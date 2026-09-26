"""
Holographic Evidence Units (HEUs) - Core data structures.

Each piece of boundary evidence becomes a holographic pixel that encodes
information about the system interior. Like a hologram pixel, each HEU
contains interference patterns from multiple internal state dimensions.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class BoundaryLayer(str, Enum):
    """
    Layers of the observability boundary (like holographic interference patterns).

    Each layer represents a different type of boundary signal that encodes
    bulk state information through different physical/informational channels.
    """
    APPLICATION_LOG = "application_log"        # Structured logs (JSONL, OTel)
    INFRASTRUCTURE_LOG = "infrastructure_log"  # System logs, kernel messages
    DISTRIBUTED_TRACE = "distributed_trace"    # OTel spans, Zipkin, Jaeger
    METRICS_EXPORT = "metrics_export"          # Prometheus, OpenMetrics, statsd
    NETWORK_FLOW = "network_flow"              # NetFlow, sFlow, PCAP headers
    CONFIG_STATE = "config_state"              # Deployed config, feature flags
    DEPLOYMENT_EVENT = "deployment_event"      # CI/CD, rollouts, scaling events


@dataclass(slots=True)
class HolographicEvidenceUnit:
    """
    A single boundary observation that encodes bulk state information.

    Like a hologram pixel: each HEU contains interference patterns from
    multiple internal state dimensions.

    Attributes:
        heu_id: Deterministic unique identifier
        timestamp_ns: Nanosecond-precision timestamp
        boundary_layer: Which boundary layer this observation comes from
        source_component: Service/component name (e.g., "navigation_controller")
        source_instance: Instance identifier (e.g., "nav-controller-3")
        payload: Raw observation data (log entry, metric sample, trace span)
        encoded_dimensions: Which bulk dimensions this HEU informs (0-1 weights)
        reconstruction_weight: How much this HEU constrains reconstruction (0-1)
        ambiguity_score: Uncertainty measure (0=unambiguous, 1=highly ambiguous)
        cross_layer_correlations: Related HEU IDs from other layers at same time
        phase_vector: 8D holographic phase encoding [time, causality, resource, error, config, deploy, network, dependency]
    """
    heu_id: str
    timestamp_ns: int
    boundary_layer: BoundaryLayer
    source_component: str
    source_instance: str

    # The raw observation (boundary data)
    payload: Dict[str, Any]

    # Holographic encoding: which internal dimensions this HEU informs
    encoded_dimensions: Dict[str, float] = field(default_factory=dict)
    # e.g., {"memory_pressure": 0.7, "cpu_contention": 0.3, "network_latency": 0.9}

    # Reconstruction metadata
    reconstruction_weight: float = 1.0      # How much this HEU constrains reconstruction
    ambiguity_score: float = 0.0            # 0=unambiguous, 1=highly ambiguous
    cross_layer_correlations: List[str] = field(default_factory=list)  # Other HEU IDs

    # Holographic phase (like interference phase in optical holography)
    # 8 dimensions: [time, causality, resource, error, config, deploy, network, dependency]
    phase_vector: np.ndarray = field(default_factory=lambda: np.zeros(8, dtype=np.float32))

    def __post_init__(self) -> None:
        """Validate and normalize after initialization."""
        if self.phase_vector.shape != (8,):
            raise ValueError(f"phase_vector must have shape (8,), got {self.phase_vector.shape}")
        if not 0.0 <= self.reconstruction_weight <= 1.0:
            raise ValueError(f"reconstruction_weight must be in [0,1], got {self.reconstruction_weight}")
        if not 0.0 <= self.ambiguity_score <= 1.0:
            raise ValueError(f"ambiguity_score must be in [0,1], got {self.ambiguity_score}")

        # Normalize encoded dimensions to [0,1]
        for k, v in self.encoded_dimensions.items():
            if not 0.0 <= v <= 1.0:
                logger.warning(f"encoded_dimensions['{k}']={v} outside [0,1], clamping")
                self.encoded_dimensions[k] = max(0.0, min(1.0, v))

    @property
    def timestamp_s(self) -> float:
        """Timestamp in seconds since epoch."""
        return self.timestamp_ns / 1_000_000_000.0

    @property
    def is_synthesized(self) -> bool:
        """Check if this HEU was synthesized (vs. observed)."""
        return self.source_instance == "synth" or self.heu_id.startswith("synth_")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for API/json."""
        return {
            "heu_id": self.heu_id,
            "timestamp_ns": self.timestamp_ns,
            "timestamp_s": self.timestamp_s,
            "boundary_layer": self.boundary_layer.value,
            "source_component": self.source_component,
            "source_instance": self.source_instance,
            "payload": self.payload,
            "encoded_dimensions": self.encoded_dimensions,
            "reconstruction_weight": self.reconstruction_weight,
            "ambiguity_score": self.ambiguity_score,
            "cross_layer_correlations": self.cross_layer_correlations,
            "phase_vector": self.phase_vector.tolist(),
            "is_synthesized": self.is_synthesized,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HolographicEvidenceUnit":
        """Deserialize from dictionary."""
        return cls(
            heu_id=data["heu_id"],
            timestamp_ns=data["timestamp_ns"],
            boundary_layer=BoundaryLayer(data["boundary_layer"]),
            source_component=data["source_component"],
            source_instance=data["source_instance"],
            payload=data["payload"],
            encoded_dimensions=data.get("encoded_dimensions", {}),
            reconstruction_weight=data.get("reconstruction_weight", 1.0),
            ambiguity_score=data.get("ambiguity_score", 0.0),
            cross_layer_correlations=data.get("cross_layer_correlations", []),
            phase_vector=np.array(data.get("phase_vector", [0.0]*8), dtype=np.float32),
        )

    def __hash__(self) -> int:
        return hash(self.heu_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HolographicEvidenceUnit):
            return NotImplemented
        return self.heu_id == other.heu_id


def _map_source_type_to_layer(source_type: str) -> BoundaryLayer:
    """
    Map Cauveris source_type to BoundaryLayer.

    Args:
        source_type: The source_type field from timeline events.

    Returns:
        Corresponding BoundaryLayer enum value.
    """
    mapping = {
        # Application logs from services
        "jsonl_log": BoundaryLayer.APPLICATION_LOG,
        "text_log": BoundaryLayer.INFRASTRUCTURE_LOG,

        # Distributed traces
        "otel_trace": BoundaryLayer.DISTRIBUTED_TRACE,
        "mcap_recording": BoundaryLayer.DISTRIBUTED_TRACE,

        # Metrics
        "csv_metrics": BoundaryLayer.METRICS_EXPORT,

        # Configuration and deployment
        "deployment_json": BoundaryLayer.DEPLOYMENT_EVENT,
        "operator_note": BoundaryLayer.CONFIG_STATE,

        # Network (if present in future)
        "netflow": BoundaryLayer.NETWORK_FLOW,
        "pcap": BoundaryLayer.NETWORK_FLOW,
    }
    return mapping.get(source_type, BoundaryLayer.APPLICATION_LOG)


def _compute_encoded_dimensions(
    event: Dict[str, Any],
    raw_signals: Dict[str, Any],
) -> Dict[str, float]:
    """
    Compute which bulk state dimensions this event informs.

    Analyzes event attributes to determine relevance to different
    internal state dimensions (CPU, memory, network, error, etc.).

    Args:
        event: Timeline event dictionary.
        raw_signals: Raw signals from RawSignalExtractor.

    Returns:
        Dictionary mapping dimension names to relevance weights [0,1].
    """
    dimensions = {}
    attributes = event.get("attributes", {})
    source_type = event.get("source_type", "")
    message = event.get("message", "").lower()

    # Also check attribute keys for dimension names
    attr_str = str(attributes).lower()

    # CPU pressure indicators
    cpu_score = 0.0
    if "cpu" in message:
        cpu_score += 0.5
    if "throttl" in message:
        cpu_score += 0.3
    if source_type == "csv_metrics" and "cpu" in attr_str:
        cpu_score += 0.4
    # Also check attributes for cpu-related keys (e.g., cpu_pressure, cpu_usage)
    if any(k in attr_str for k in ["cpu_pressure", "cpu_usage", "cpu_util", "throttl"]):
        cpu_score = max(cpu_score, 0.7)
    if cpu_score > 0:
        dimensions["cpu_pressure"] = min(1.0, cpu_score)

    # CPU pressure indicators
    cpu_score = 0.0
    if "cpu" in message:
        cpu_score += 0.5
    if "throttl" in message:
        cpu_score += 0.3
    if source_type == "csv_metrics" and "cpu" in str(attributes).lower():
        cpu_score += 0.4
    if cpu_score > 0:
        dimensions["cpu_pressure"] = min(1.0, cpu_score)

    # Memory pressure indicators
    mem_score = 0.0
    if any(kw in message for kw in ["memory", "mem", "oom", "swap", "page"]):
        mem_score += 0.5
    if "oom" in message or "out of memory" in message:
        mem_score += 0.4
    if source_type == "csv_metrics" and "mem" in attr_str:
        mem_score += 0.4
    # Also check attributes for memory-related keys (e.g., memory_pressure, memory_usage)
    if any(k in attr_str for k in ["memory_pressure", "memory_usage", "mem_util"]):
        mem_score = max(mem_score, 0.7)
    if mem_score > 0:
        dimensions["memory_pressure"] = min(1.0, mem_score)

    # Network latency/loss indicators
    net_score = 0.0
    if any(kw in message for kw in ["latency", "timeout", "rtt", "network", "packet loss", "retransmit"]):
        net_score += 0.5
    if source_type == "csv_metrics" and any(k in str(attributes).lower() for k in ["latency", "rtt", "loss"]):
        net_score += 0.4
    if source_type == "otel_trace":
        # Trace duration carries network latency info
        duration_ns = attributes.get("duration_ns", 0)
        if duration_ns > 100_000_000:  # > 100ms
            net_score += 0.3
    if net_score > 0:
        dimensions["network_latency"] = min(1.0, net_score)

    # Error/Anomaly indicators
    error_score = 0.0
    if any(kw in message for kw in ["error", "fail", "exception", "crash", "panic", "fatal"]):
        error_score += 0.6
    if event.get("status", "").lower() in ("error", "failed", "fatal"):
        error_score += 0.4
    if source_type == "jsonl_log":
        level = attributes.get("level", "").upper()
        if level in ("ERROR", "FATAL", "CRITICAL"):
            error_score += 0.5
        elif level == "WARN":
            error_score += 0.2
    if error_score > 0:
        dimensions["error_rate"] = min(1.0, error_score)

    # Deployment event indicators
    deploy_score = 0.0
    if source_type == "deployment_json":
        deploy_score = 1.0
    elif "deploy" in message or "rollout" in message or "scal" in message:
        deploy_score += 0.4
    if deploy_score > 0:
        dimensions["deployment_activity"] = min(1.0, deploy_score)

    # Configuration change indicators
    config_score = 0.0
    if source_type in ("deployment_json", "operator_note"):
        config_score = 0.9
    elif any(kw in message for kw in ["config", "parameter", "flag", "setting"]):
        config_score += 0.3
    # For operator_note with "scale", prefer deployment_activity over config_change
    if config_score > 0:
        # If it's operator_note and deployment_activity was detected, skip config_change
        if source_type == "operator_note" and "deployment_activity" in dimensions:
            pass  # Skip config_change for scaling events
        else:
            dimensions["config_change"] = min(1.0, config_score)

    # Dependency/cross-service indicators
    dep_score = 0.0
    if source_type == "otel_trace":
        # Spans inherently encode service dependencies
        dep_score = 0.8
    elif "service" in message and ("call" in message or "request" in message):
        dep_score += 0.3
    if dep_score > 0:
        dimensions["service_dependency"] = min(1.0, dep_score)

    # Resource contention (generic)
    resource_score = 0.0
    if any(kw in message for kw in ["contention", "bottleneck", "saturat", "queue", "backlog"]):
        resource_score += 0.4
    if source_type == "csv_metrics":
        resource_score += 0.2
    if resource_score > 0:
        dimensions["resource_contention"] = min(1.0, resource_score)

    return dimensions


def _compute_phase_vector(
    event: Dict[str, Any],
    incident_duration_ns: int,
    causal_depth: int = 0,
    max_causal_depth: int = 1,
    service_dependency_count: int = 0,
) -> np.ndarray:
    """
    Compute 8D holographic phase vector for an event.

    Phase vector dimensions:
    0. Time: Temporal position in incident [0,1]
    1. Causality: Position in causal chain [0,1]
    2. Resource: Resource pressure level [0,1]
    3. Error: Error/anomaly signal strength [0,1]
    4. Config: Configuration change proximity [0,1]
    5. Deploy: Deployment event coupling [0,1]
    4. Network: Network boundary signal [0,1]
    5. Dependency: Cross-service dependency depth [0,1]

    Args:
        event: Timeline event dictionary.
        incident_duration_ns: Total incident duration in nanoseconds.
        causal_depth: Depth in inferred causal graph (0 = root cause candidate).
        max_causal_depth: Maximum causal depth in incident.
        service_dependency_count: Number of transitive dependencies.

    Returns:
        8-element float32 numpy array.
    """
    phase = np.zeros(8, dtype=np.float32)

    # Dimension 0: Time - normalized position in incident
    ts = event.get("timestamp_ns", 0)
    if incident_duration_ns > 0:
        phase[0] = min(1.0, max(0.0, ts / incident_duration_ns))

    # Dimension 1: Causality - normalized causal depth
    if max_causal_depth > 0:
        phase[1] = min(1.0, causal_depth / max_causal_depth)

    # Dimensions 2-7: Derived from encoded dimensions
    encoded = _compute_encoded_dimensions(event, {})

    phase[2] = encoded.get("cpu_pressure", 0.0) + encoded.get("memory_pressure", 0.0) + encoded.get("resource_contention", 0.0)
    phase[2] = min(1.0, phase[2])

    phase[3] = encoded.get("error_rate", 0.0)
    phase[4] = encoded.get("config_change", 0.0)
    phase[5] = encoded.get("deployment_activity", 0.0)
    phase[6] = encoded.get("network_latency", 0.0)
    phase[7] = min(1.0, service_dependency_count / 10.0)  # Normalize to ~10 max deps

    return phase


def _synthesize_heu_id(
    boundary_layer: BoundaryLayer,
    source_component: str,
    source_instance: str,
    timestamp_ns: int,
    sequence: int,
) -> str:
    """
    Generate deterministic HEU ID.

    Format: heu_{layer}_{component}_{instance}_{timestamp}_{seq}.{hash8}
    """
    key = f"{boundary_layer.value}:{source_component}:{source_instance}:{timestamp_ns}:{sequence}"
    short_hash = hashlib.md5(key.encode()).hexdigest()[:8]
    return f"heu_{boundary_layer.value}_{source_component}_{source_instance}_{timestamp_ns}_{sequence:06d}.{short_hash}"


def convert_timeline_to_heus(
    timeline_events: List[Dict[str, Any]],
    raw_signals: Dict[str, Any],
    incident_duration_ns: int,
) -> List[HolographicEvidenceUnit]:
    """
    Convert Cauveris timeline events to Holographic Evidence Units.

    This is the main entry point for HEU generation from the existing
    Cauveris pipeline.

    Args:
        timeline_events: Sorted timeline events from TimelineBuilder.
        raw_signals: Raw signals from RawSignalExtractor.
        incident_duration_ns: Total incident window in nanoseconds.

    Returns:
        List of HEUs with phase vectors and encoded dimensions.
    """
    if not timeline_events:
        return []

    # First pass: compute causal depths for all events
    causal_depths = _compute_causal_depths(timeline_events)
    max_depth = max(causal_depths.values()) if causal_depths else 1

    # Second pass: compute service dependency counts
    dep_counts = _compute_dependency_counts(timeline_events)

    # Group by (source_type, source) for sequence numbers
    from collections import defaultdict
    seq_counters: Dict[Tuple[str, str], int] = defaultdict(int)

    heus = []
    for event in timeline_events:
        source_type = event.get("source_type", "unknown")
        source = event.get("source", "unknown")
        layer = _map_source_type_to_layer(source_type)

        # Get component/instance from attributes (including OTel standard attributes)
        attributes = event.get("attributes", {})
        component = attributes.get("service") or attributes.get("component") or attributes.get("service.name") or source
        instance = attributes.get("instance") or attributes.get("host") or "unknown"

        seq = seq_counters[(source_type, source)]
        seq_counters[(source_type, source)] = seq + 1

        heu_id = _synthesize_heu_id(layer, component, instance, event.get("timestamp_ns", 0), seq)

        encoded_dims = _compute_encoded_dimensions(event, raw_signals)

        phase = _compute_phase_vector(
            event,
            incident_duration_ns,
            causal_depth=causal_depths.get(event.get("event_id", ""), 0),
            max_causal_depth=max_depth,
            service_dependency_count=dep_counts.get(component, 0),
        )

        # Compute reconstruction weight based on layer informativeness
        weight = _compute_reconstruction_weight(layer, encoded_dims)

        # Compute ambiguity score
        ambiguity = _compute_ambiguity_score(event, layer, encoded_dims)

        heu = HolographicEvidenceUnit(
            heu_id=heu_id,
            timestamp_ns=event.get("timestamp_ns", 0),
            boundary_layer=layer,
            source_component=component,
            source_instance=instance,
            payload=event,
            encoded_dimensions=encoded_dims,
            reconstruction_weight=weight,
            ambiguity_score=ambiguity,
            phase_vector=phase,
        )
        heus.append(heu)

    # Third pass: add cross-layer correlations
    _add_cross_layer_correlations(heus)

    return heus


def _compute_causal_depths(timeline_events: List[Dict]) -> Dict[str, int]:
    """
    Compute causal depth for each event using simple temporal + attribute heuristics.
    Events that appear to be causes get depth 0, effects get higher depths.
    """
    depths = {}
    # Simple heuristic: deployment events are root causes (depth 0)
    # Events with error status are effects (higher depth)
    # OTel spans follow trace structure
    for event in timeline_events:
        event_id = event.get("event_id", event.get("evidence_id", ""))
        source_type = event.get("source_type", "")
        status = event.get("status", "").lower()

        if source_type == "deployment_json":
            depths[event_id] = 0
        elif status in ("error", "failed", "fatal"):
            depths[event_id] = 2
        elif source_type == "otel_trace":
            # Use span hierarchy if available
            parent_span = event.get("attributes", {}).get("parent_span_id")
            if parent_span:
                depths[event_id] = 1
            else:
                depths[event_id] = 0  # Root span
        else:
            depths[event_id] = 1

    return depths


def _compute_dependency_counts(timeline_events: List[Dict]) -> Dict[str, int]:
    """Count service dependencies from trace and log data."""
    service_calls: Dict[str, set] = {}
    for event in timeline_events:
        source_type = event.get("source_type", "")
        attributes = event.get("attributes", {})

        if source_type == "otel_trace":
            service = attributes.get("service.name", "unknown")
            # Destination service from span kind or attributes
            dest = attributes.get("peer.service", attributes.get("destination.service"))
            if dest:
                service_calls.setdefault(service, set()).add(dest)

    # Transitive closure for dependency count
    dep_counts = {}
    for service, deps in service_calls.items():
        dep_counts[service] = len(deps)
    return dep_counts


def _compute_reconstruction_weight(
    layer: BoundaryLayer,
    encoded_dims: Dict[str, float],
) -> float:
    """
    Compute how much this HEU should constrain the reconstruction.

    More informative layers and more specific signals get higher weights.
    """
    base_weights = {
        BoundaryLayer.DISTRIBUTED_TRACE: 1.0,    # Highest: causal structure
        BoundaryLayer.APPLICATION_LOG: 0.9,       # Structured, rich context
        BoundaryLayer.METRICS_EXPORT: 0.8,        # Quantitative, continuous
        BoundaryLayer.INFRASTRUCTURE_LOG: 0.6,    # Noisy, mixed domains
        BoundaryLayer.DEPLOYMENT_EVENT: 0.9,      # Clear causal anchors
        BoundaryLayer.CONFIG_STATE: 0.7,          # Important but sparse
        BoundaryLayer.NETWORK_FLOW: 0.5,          # Lower resolution
    }
    base = base_weights.get(layer, 0.5)

    # Boost if this HEU informs many dimensions
    dimension_boost = min(0.2, len(encoded_dims) * 0.03)

    # Boost if strong signal in any dimension
    signal_boost = max(encoded_dims.values()) * 0.2 if encoded_dims else 0.0

    return min(1.0, base + dimension_boost + signal_boost)


def _compute_ambiguity_score(
    event: Dict[str, Any],
    layer: BoundaryLayer,
    encoded_dims: Dict[str, float],
) -> float:
    """
    Compute ambiguity score [0,1] for this HEU.

    Higher ambiguity = less reliable for reconstruction.
    """
    score = 0.0

    # Layer-specific base ambiguity
    layer_ambiguity = {
        BoundaryLayer.INFRASTRUCTURE_LOG: 0.3,    # Mixed clock domains
        BoundaryLayer.NETWORK_FLOW: 0.4,          # Header-only, no payload
        BoundaryLayer.METRICS_EXPORT: 0.2,        # Aggregated, loses detail
        BoundaryLayer.APPLICATION_LOG: 0.1,       # Structured, detailed
        BoundaryLayer.DISTRIBUTED_TRACE: 0.05,    # Causal structure preserved
        BoundaryLayer.DEPLOYMENT_EVENT: 0.1,      # Clear timestamp, intent
        BoundaryLayer.CONFIG_STATE: 0.15,         # Sparse but clear
    }
    score += layer_ambiguity.get(layer, 0.2)

    # Timestamp precision
    original_ts = event.get("original_timestamp", "")
    if original_ts and "." not in original_ts and "T" in original_ts:
        # Second-precision only
        score += 0.2

    # Low information content
    if not encoded_dims:
        score += 0.3

    # Confidence from builder
    builder_confidence = event.get("confidence", 0.5)
    score += (1.0 - builder_confidence) * 0.2

    return min(1.0, score)


def _add_cross_layer_correlations(heus: List[HolographicEvidenceUnit]) -> None:
    """
    Add cross-layer correlations between HEUs.

    Events from different layers at the same timestamp (within 1ms)
    and same component are correlated.
    """
    # Group by component and millisecond
    from collections import defaultdict
    by_comp_ms: Dict[Tuple[str, int], List[HolographicEvidenceUnit]] = defaultdict(list)

    for heu in heus:
        ms_bucket = heu.timestamp_ns // 1_000_000
        by_comp_ms[(heu.source_component, ms_bucket)].append(heu)

    # Add correlations within each bucket
    for bucket_heus in by_comp_ms.values():
        if len(bucket_heus) > 1:
            ids = [h.heu_id for h in bucket_heus]
            for heu in bucket_heus:
                # Add other HEUs in same bucket as correlations
                heu.cross_layer_correlations = [
                    cid for cid in ids if cid != heu.heu_id
                ]
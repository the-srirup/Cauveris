"""
Holographic Anomaly Detection - Detects anomalies in reconstructed bulk state.

Analyzes reconstructed holographic state for deviations from expected patterns,
signatures of known failure modes, and statistical anomalies in the bulk dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
from enum import Enum
from collections import defaultdict

import numpy as np

from .topology import SystemTopology, ComponentInfo, CausalEdge, ResourceCapacity
from .heu import HolographicEvidenceUnit, BoundaryLayer
from .reconstruction import (
    HolographicReconstruction,
    ReconstructedServiceState,
    ReconstructedNetworkState,
    NetworkEdge,
    AmbiguityRegion,
)


class AnomalyType(Enum):
    """Types of anomalies detectable in holographic reconstruction."""
    # Resource anomalies
    CPU_SATURATION = "cpu_saturation"
    MEMORY_EXHAUSTION = "memory_exhaustion"
    NETWORK_CONGESTION = "network_congestion"
    DISK_PRESSURE = "disk_pressure"

    # Behavioral anomalies
    ERROR_SPIKE = "error_spike"
    LATENCY_DEGRADATION = "latency_degradation"
    THROUGHPUT_COLLAPSE = "throughput_collapse"
    CONNECTION_STORM = "connection_storm"

    # Structural anomalies
    CASCADING_FAILURE = "cascading_failure"
    FEEDBACK_LOOP = "feedback_loop"
    DEPENDENCY_CYCLE = "dependency_cycle"
    RESOURCE_STARVATION = "resource_starvation"

    # Temporal anomalies
    PERIODIC_OSCILLATION = "periodic_oscillation"
    SUDDEN_SHIFT = "sudden_shift"
    GRADUAL_DRIFT = "gradual_drift"

    # Configuration anomalies
    CONFIG_MISMATCH = "config_mismatch"
    DEPLOYMENT_ANOMALY = "deployment_anomaly"
    VERSION_SKEW = "version_skew"

    # Security-related
    UNUSUAL_ACCESS_PATTERN = "unusual_access_pattern"
    DATA_EXFILTRATION_SIGNATURE = "data_exfiltration_signature"

    # Reconstruction quality
    RECONSTRUCTION_AMBIGUITY = "reconstruction_ambiguity"
    MISSING_EVIDENCE = "missing_evidence"


class AnomalySeverity(Enum):
    """Severity levels for anomalies."""
    INFO = 0      # Informational, no immediate action
    LOW = 1       # Minor deviation, monitor
    MEDIUM = 2    # Notable anomaly, investigate
    HIGH = 3      # Significant issue, action needed
    CRITICAL = 4  # Critical failure, immediate response


@dataclass(slots=True)
class Anomaly:
    """A detected anomaly in the holographic reconstruction."""
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    component: str
    dimension: str
    value: float
    expected_range: Tuple[float, float]
    confidence: float
    description: str
    evidence: List[str] = field(default_factory=list)
    related_anomalies: List[str] = field(default_factory=list)
    timestamp_ns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.anomaly_type.value,
            "severity": self.severity.name,
            "component": self.component,
            "dimension": self.dimension,
            "value": self.value,
            "expected_range": list(self.expected_range),
            "confidence": self.confidence,
            "description": self.description,
            "evidence": self.evidence,
            "related": self.related_anomalies,
        }


@dataclass
class AnomalyReport:
    """Complete anomaly detection report."""
    anomalies: List[Anomaly] = field(default_factory=list)
    component_scores: Dict[str, float] = field(default_factory=dict)
    severity_counts: Dict[AnomalySeverity, int] = field(default_factory=dict)
    summary: str = ""
    timestamp_ns: int = 0
    incident_id: str = ""

    def get_critical_anomalies(self) -> List[Anomaly]:
        return [a for a in self.anomalies if a.severity == AnomalySeverity.CRITICAL]

    def get_high_anomalies(self) -> List[Anomaly]:
        return [a for a in self.anomalies if a.severity in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "timestamp_ns": self.timestamp_ns,
            "summary": self.summary,
            "severity_counts": {k.name: v for k, v in self.severity_counts.items()},
            "component_scores": self.component_scores,
            "anomalies": [a.to_dict() for a in self.anomalies],
        }


# Normal operating ranges for different component types
NORMAL_RANGES = {
    "service": {
        "cpu_usage": (0.0, 0.7),
        "memory_usage": (0.0, 0.75),
        "network_usage": (0.0, 0.6),
        "error_rate": (0.0, 0.01),
        "latency_p99_ms": (0.0, 200.0),
    },
    "database": {
        "cpu_usage": (0.0, 0.6),
        "memory_usage": (0.0, 0.8),
        "network_usage": (0.0, 0.5),
        "error_rate": (0.0, 0.005),
        "latency_p99_ms": (0.0, 100.0),
    },
    "cache": {
        "cpu_usage": (0.0, 0.5),
        "memory_usage": (0.0, 0.9),
        "network_usage": (0.0, 0.6),
        "error_rate": (0.0, 0.001),
        "latency_p99_ms": (0.0, 10.0),
    },
    "gateway": {
        "cpu_usage": (0.0, 0.7),
        "memory_usage": (0.0, 0.6),
        "network_usage": (0.0, 0.8),
        "error_rate": (0.0, 0.02),
        "latency_p99_ms": (0.0, 500.0),
    },
    "message_queue": {
        "cpu_usage": (0.0, 0.5),
        "memory_usage": (0.0, 0.7),
        "network_usage": (0.0, 0.7),
        "error_rate": (0.0, 0.005),
        "latency_p99_ms": (0.0, 50.0),
    },
}


class HolographicAnomalyDetector:
    """
    Detects anomalies in holographic reconstruction.

    Uses multi-dimensional analysis of reconstructed bulk state to identify
    signatures of known failure modes and statistical deviations.
    """

    def __init__(
        self,
        topology: SystemTopology,
        normal_ranges: Optional[Dict[str, Dict[str, Tuple[float, float]]]] = None,
        sensitivity: float = 1.0,
    ):
        self.topology = topology
        self.normal_ranges = normal_ranges or NORMAL_RANGES
        self.sensitivity = sensitivity  # 0.5 = less sensitive, 2.0 = more sensitive

        # Anomaly signatures (patterns that indicate specific failure modes)
        self._signatures = self._build_signatures()

    def _build_signatures(self) -> Dict[AnomalyType, Callable]:
        """Build anomaly detection signatures."""
        return {
            AnomalyType.CPU_SATURATION: self._detect_cpu_saturation,
            AnomalyType.MEMORY_EXHAUSTION: self._detect_memory_exhaustion,
            AnomalyType.NETWORK_CONGESTION: self._detect_network_congestion,
            AnomalyType.ERROR_SPIKE: self._detect_error_spike,
            AnomalyType.LATENCY_DEGRADATION: self._detect_latency_degradation,
            AnomalyType.THROUGHPUT_COLLAPSE: self._detect_throughput_collapse,
            AnomalyType.CASCADING_FAILURE: self._detect_cascading_failure,
            AnomalyType.FEEDBACK_LOOP: self._detect_feedback_loop,
            AnomalyType.RESOURCE_STARVATION: self._detect_resource_starvation,
            AnomalyType.DEPENDENCY_CYCLE: self._detect_dependency_cycle,
            AnomalyType.CONFIG_MISMATCH: self._detect_config_mismatch,
            AnomalyType.DEPLOYMENT_ANOMALY: self._detect_deployment_anomaly,
        }

    def detect(
        self,
        reconstruction: HolographicReconstruction,
        baseline: Optional[HolographicReconstruction] = None,
        temporal_data: Optional[Dict[str, Any]] = None,
    ) -> AnomalyReport:
        """
        Detect anomalies in holographic reconstruction.

        Args:
            reconstruction: Reconstructed bulk state
            baseline: Optional normal baseline for comparison
            temporal_data: Optional temporal analysis for cross-reference

        Returns:
            AnomalyReport with all detected anomalies
        """
        report = AnomalyReport(
            incident_id=reconstruction.incident_id,
            timestamp_ns=reconstruction.reconstruction_timestamp_ns,
        )

        # 1. Threshold-based anomalies (per-component)
        self._detect_threshold_anomalies(reconstruction, report, baseline)

        # 2. Signature-based anomalies (pattern matching)
        self._detect_signature_anomalies(reconstruction, report, temporal_data)

        # 3. Structural anomalies (topology-aware)
        self._detect_structural_anomalies(reconstruction, report)

        # 4. Cross-component correlation anomalies
        self._detect_correlation_anomalies(reconstruction, report)

        # 5. Ambiguity-based anomalies
        self._detect_ambiguity_anomalies(reconstruction, report)

        # Compute component scores
        report.component_scores = self._compute_component_scores(reconstruction, report)

        # Count by severity
        for severity in AnomalySeverity:
            report.severity_counts[severity] = sum(
                1 for a in report.anomalies if a.severity == severity
            )

        # Generate summary
        report.summary = self._generate_summary(report)

        return report

    def _detect_threshold_anomalies(
        self,
        reconstruction: HolographicReconstruction,
        report: AnomalyReport,
        baseline: Optional[HolographicReconstruction],
    ) -> None:
        """Detect threshold violations per component."""
        for comp_name, state in reconstruction.reconstructed_services.items():
            comp = self.topology.components.get(comp_name)
            if not comp:
                continue

            comp_type = comp.component_type
            ranges = self.normal_ranges.get(comp_type, self.normal_ranges["service"])

            dimensions = {
                "cpu_usage": state.cpu_usage,
                "memory_usage": state.memory_usage,
                "network_usage": state.network_usage,
                "error_rate": state.error_rate,
                "latency_p99_ms": state.latency_p99_ms,
            }

            for dim, value in dimensions.items():
                expected_min, expected_max = ranges.get(dim, (0.0, 1.0))
                # Higher sensitivity = lower threshold = more anomalies detected
                # sensitivity=0.5 means half the threshold (more sensitive)
                # sensitivity=2.0 means double the threshold (less sensitive)
                adjusted_max = expected_max / self.sensitivity

                if value > adjusted_max:
                    severity = self._compute_severity(value, expected_max)
                    anomaly = Anomaly(
                        anomaly_type=self._map_dimension_to_anomaly(dim),
                        severity=severity,
                        component=comp_name,
                        dimension=dim,
                        value=value,
                        expected_range=(expected_min, expected_max),
                        confidence=min(1.0, value / max(adjusted_max, 1e-6)),
                        description=f"{comp_name} {dim} = {value:.3f} exceeds normal max {expected_max:.3f}",
                        evidence=[f"Reconstructed {dim} = {value:.3f}"],
                    )
                    report.anomalies.append(anomaly)

                # Check baseline comparison
                if baseline and comp_name in baseline.reconstructed_services:
                    base_state = baseline.reconstructed_services[comp_name]
                    base_value = getattr(base_state, dim, 0.0)
                    if base_value > 0:
                        ratio = value / base_value
                        if ratio > 2.0 * self.sensitivity:  # 2x baseline
                            anomaly = Anomaly(
                                anomaly_type=AnomalyType.SUDDEN_SHIFT,
                                severity=AnomalySeverity.HIGH if ratio > 3 else AnomalySeverity.MEDIUM,
                                component=comp_name,
                                dimension=dim,
                                value=value,
                                expected_range=(base_value * 0.8, base_value * 1.2),
                                confidence=min(1.0, (ratio - 1.0) / 3.0),
                                description=f"{comp_name} {dim} shifted {ratio:.1f}x from baseline",
                                evidence=[f"Baseline: {base_value:.3f}, Current: {value:.3f}"],
                            )
                            report.anomalies.append(anomaly)

    def _detect_signature_anomalies(
        self,
        reconstruction: HolographicReconstruction,
        report: AnomalyReport,
        temporal_data: Optional[Dict[str, Any]],
    ) -> None:
        """Run signature-based anomaly detectors."""
        for anomaly_type, detector in self._signatures.items():
            try:
                anomalies = detector(reconstruction, temporal_data)
                report.anomalies.extend(anomalies)
            except Exception as e:
                # Don't let one detector failure stop others
                pass

    def _detect_structural_anomalies(
        self,
        reconstruction: HolographicReconstruction,
        report: AnomalyReport,
    ) -> None:
        """Detect topology-aware structural anomalies."""
        # Detect components with no inbound/outbound edges but high load
        for comp_name, state in reconstruction.reconstructed_services.items():
            in_edges = sum(1 for e in self.topology.causal_edges if e.target == comp_name)
            out_edges = sum(1 for e in self.topology.causal_edges if e.source == comp_name)

            if in_edges == 0 and out_edges == 0 and (state.cpu_usage > 0.5 or state.error_rate > 0.05):
                anomaly = Anomaly(
                    anomaly_type=AnomalyType.RESOURCE_STARVATION,
                    severity=AnomalySeverity.MEDIUM,
                    component=comp_name,
                    dimension="isolated_high_load",
                    value=state.cpu_usage,
                    expected_range=(0.0, 0.3),
                    confidence=0.7,
                    description=f"Isolated component {comp_name} showing high load ({state.cpu_usage:.2f})",
                    evidence=["No causal edges but high resource usage"],
                )
                report.anomalies.append(anomaly)

    def _detect_correlation_anomalies(
        self,
        reconstruction: HolographicReconstruction,
        report: AnomalyReport,
    ) -> None:
        """Detect anomalous cross-component correlations."""
        # Build correlation matrix from reconstruction
        components = list(reconstruction.reconstructed_services.keys())
        if len(components) < 2:
            return

        dims = ["cpu_usage", "memory_usage", "error_rate", "latency_p99_ms"]
        for dim in dims:
            values = [getattr(reconstruction.reconstructed_services[c], dim, 0) for c in components]
            if len(values) < 2:
                continue

            # Check for correlated high values - could indicate cascading failure
            # High correlation (low std) or high variance (high std) with high values both matter
            for edge in self.topology.causal_edges:
                if edge.source in components and edge.target in components:
                    src_idx = components.index(edge.source)
                    tgt_idx = components.index(edge.target)
                    # Flag if both are high on a causal edge (indicates potential cascade)
                    if values[src_idx] > 0.7 and values[tgt_idx] > 0.7:
                        anomaly = Anomaly(
                            anomaly_type=AnomalyType.CASCADING_FAILURE,
                            severity=AnomalySeverity.HIGH,
                            component=f"{edge.source}->{edge.target}",
                            dimension=dim,
                            value=(values[src_idx] + values[tgt_idx]) / 2,
                            expected_range=(0.0, 0.5),
                            confidence=0.8,
                            description=f"Correlated high {dim} on edge {edge.source}->{edge.target}",
                            evidence=[f"Source: {values[src_idx]:.2f}, Target: {values[tgt_idx]:.2f}"],
                        )
                        report.anomalies.append(anomaly)

    def _detect_ambiguity_anomalies(
        self,
        reconstruction: HolographicReconstruction,
        report: AnomalyReport,
    ) -> None:
        """Detect anomalies related to reconstruction ambiguity."""
        for region in reconstruction.ambiguity_regions:
            dims = ", ".join(region.affected_dimensions) or "unspecified"

            # High ambiguity: the boundary evidence could not pin the bulk state down.
            if region.ambiguity_score > 0.5:
                anomaly = Anomaly(
                    anomaly_type=AnomalyType.RECONSTRUCTION_AMBIGUITY,
                    severity=(
                        AnomalySeverity.MEDIUM
                        if region.ambiguity_score > 0.75
                        else AnomalySeverity.LOW
                    ),
                    component=region.component,
                    dimension="ambiguity",
                    value=region.ambiguity_score,
                    expected_range=(0.0, 0.3),
                    confidence=region.ambiguity_score,
                    description=(
                        f"High reconstruction ambiguity for {region.component} "
                        f"({dims}): score {region.ambiguity_score:.2f}"
                    ),
                    evidence=[
                        f"ambiguity_score={region.ambiguity_score:.3f}",
                        f"affected_dimensions=[{dims}]",
                        f"missing_layers={region.missing_layers}",
                    ],
                )
                report.anomalies.append(anomaly)

            # Missing boundary layers explain (and worsen) the ambiguity.
            if len(region.missing_layers) > 1:
                anomaly = Anomaly(
                    anomaly_type=AnomalyType.MISSING_EVIDENCE,
                    severity=AnomalySeverity.LOW,
                    component=region.component,
                    dimension="missing_layers",
                    value=float(len(region.missing_layers)),
                    expected_range=(0.0, 1.0),
                    confidence=0.6,
                    description=(
                        f"{len(region.missing_layers)} boundary layers unobserved for "
                        f"{region.component}: {', '.join(region.missing_layers)}"
                    ),
                    evidence=[f"missing_layers={region.missing_layers}"],
                )
                report.anomalies.append(anomaly)

    # Signature detectors
    def _detect_cpu_saturation(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect CPU saturation patterns."""
        anomalies = []
        for comp_name, state in recon.reconstructed_services.items():
            if state.cpu_usage > 0.9:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.CPU_SATURATION,
                    severity=AnomalySeverity.CRITICAL if state.cpu_usage > 0.95 else AnomalySeverity.HIGH,
                    component=comp_name,
                    dimension="cpu_usage",
                    value=state.cpu_usage,
                    expected_range=(0.0, 0.7),
                    confidence=state.cpu_usage,
                    description=f"CPU saturation: {state.cpu_usage:.1%} usage",
                    evidence=[f"cpu_usage={state.cpu_usage:.3f}"],
                ))
        return anomalies

    def _detect_memory_exhaustion(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect memory exhaustion patterns."""
        anomalies = []
        for comp_name, state in recon.reconstructed_services.items():
            if state.memory_usage > 0.9:
                severity = AnomalySeverity.CRITICAL if state.memory_usage > 0.95 else AnomalySeverity.HIGH
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.MEMORY_EXHAUSTION,
                    severity=severity,
                    component=comp_name,
                    dimension="memory_usage",
                    value=state.memory_usage,
                    expected_range=(0.0, 0.75),
                    confidence=state.memory_usage,
                    description=f"Memory exhaustion: {state.memory_usage:.1%} usage",
                    evidence=[f"memory_usage={state.memory_usage:.3f}"],
                ))
        return anomalies

    def _detect_network_congestion(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect network congestion."""
        anomalies = []
        if recon.reconstructed_network:
            for (src, dst), edge in recon.reconstructed_network.edges.items():
                if edge.loss_rate > 0.05 or edge.latency_ms > 500:
                    anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.NETWORK_CONGESTION,
                        severity=AnomalySeverity.HIGH if edge.loss_rate > 0.1 else AnomalySeverity.MEDIUM,
                        component=f"{src}->{dst}",
                        dimension="network",
                        value=edge.loss_rate,
                        expected_range=(0.0, 0.01),
                        confidence=edge.loss_rate * 10,
                        description=f"Network congestion: {edge.loss_rate:.1%} loss, {edge.latency_ms:.0f}ms latency",
                        evidence=[f"loss_rate={edge.loss_rate:.4f}", f"latency={edge.latency_ms:.0f}ms"],
                    ))
        return anomalies

    def _detect_error_spike(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect error rate spikes."""
        anomalies = []
        for comp_name, state in recon.reconstructed_services.items():
            if state.error_rate > 0.1:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.ERROR_SPIKE,
                    severity=AnomalySeverity.CRITICAL if state.error_rate > 0.5 else AnomalySeverity.HIGH,
                    component=comp_name,
                    dimension="error_rate",
                    value=state.error_rate,
                    expected_range=(0.0, 0.01),
                    confidence=state.error_rate * 2,
                    description=f"Error spike: {state.error_rate:.1%} error rate",
                    evidence=[f"error_rate={state.error_rate:.4f}"],
                ))
        return anomalies

    def _detect_latency_degradation(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect latency degradation."""
        anomalies = []
        for comp_name, state in recon.reconstructed_services.items():
            if state.latency_p99_ms > 2000:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.LATENCY_DEGRADATION,
                    severity=AnomalySeverity.HIGH,
                    component=comp_name,
                    dimension="latency_p99_ms",
                    value=state.latency_p99_ms,
                    expected_range=(0.0, 500.0),
                    confidence=min(1.0, state.latency_p99_ms / 5000.0),
                    description=f"Latency degradation: P99={state.latency_p99_ms:.0f}ms",
                    evidence=[f"latency_p99_ms={state.latency_p99_ms:.0f}"],
                ))
        return anomalies

    def _detect_throughput_collapse(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect throughput collapse (high CPU + low throughput = stuck)."""
        anomalies = []
        for comp_name, state in recon.reconstructed_services.items():
            if state.cpu_usage > 0.8 and state.error_rate > 0.2:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.THROUGHPUT_COLLAPSE,
                    severity=AnomalySeverity.CRITICAL,
                    component=comp_name,
                    dimension="throughput",
                    value=state.error_rate,
                    expected_range=(0.0, 0.05),
                    confidence=0.9,
                    description=f"Throughput collapse: high CPU ({state.cpu_usage:.0%}) + high errors ({state.error_rate:.0%})",
                    evidence=[f"cpu={state.cpu_usage:.2f}", f"errors={state.error_rate:.2f}"],
                ))
        return anomalies

    def _detect_cascading_failure(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect cascading failure pattern."""
        anomalies = []
        # Look for chain of high-error components along causal edges
        visited = set()
        for edge in self.topology.causal_edges:
            if edge.source in recon.reconstructed_services and edge.target in recon.reconstructed_services:
                src_state = recon.reconstructed_services[edge.source]
                tgt_state = recon.reconstructed_services[edge.target]
                if src_state.error_rate > 0.1 and tgt_state.error_rate > 0.1:
                    chain = self._find_cascade_chain(edge.source, recon, visited)
                    if len(chain) >= 3:
                        anomalies.append(Anomaly(
                            anomaly_type=AnomalyType.CASCADING_FAILURE,
                            severity=AnomalySeverity.CRITICAL,
                            component="->".join(chain),
                            dimension="cascade",
                            value=len(chain),
                            expected_range=(0.0, 2.0),
                            confidence=0.85,
                            description=f"Cascading failure chain: {' -> '.join(chain)}",
                            evidence=[f"Chain length: {len(chain)}"],
                        ))
        return anomalies

    def _find_cascade_chain(self, start: str, recon: HolographicReconstruction, visited: Set[str]) -> List[str]:
        """Find cascade chain starting from a component."""
        if start in visited:
            return []
        visited.add(start)

        chain = [start]
        for edge in self.topology.causal_edges:
            if edge.source == start and edge.target in recon.reconstructed_services:
                tgt_state = recon.reconstructed_services[edge.target]
                if tgt_state.error_rate > 0.1:
                    chain.extend(self._find_cascade_chain(edge.target, recon, visited))
                    break
        return chain

    def _detect_feedback_loop(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect feedback loops in causal graph."""
        anomalies = []
        # Simple cycle detection in high-load components
        high_load = {c for c, s in recon.reconstructed_services.items() if s.cpu_usage > 0.7}
        for edge in self.topology.causal_edges:
            if edge.source in high_load and edge.target in high_load:
                # Check for reverse edge
                rev_edge = next((e for e in self.topology.causal_edges
                                if e.source == edge.target and e.target == edge.source), None)
                if rev_edge:
                    anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.FEEDBACK_LOOP,
                        severity=AnomalySeverity.HIGH,
                        component=f"{edge.source}<->{edge.target}",
                        dimension="feedback",
                        value=1.0,
                        expected_range=(0.0, 0.0),
                        confidence=0.7,
                        description=f"Potential feedback loop: {edge.source} <-> {edge.target} both under high load",
                        evidence=[f"Edge {edge.source}->{edge.target}", f"Reverse edge exists"],
                    ))
        return anomalies

    def _detect_resource_starvation(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect resource starvation (dependency using all resources)."""
        anomalies = []
        for edge in self.topology.causal_edges:
            if edge.source in recon.reconstructed_services and edge.target in recon.reconstructed_services:
                src = recon.reconstructed_services[edge.source]
                tgt = recon.reconstructed_services[edge.target]
                # Source starved, target using resources
                if src.cpu_usage > 0.8 and tgt.cpu_usage < 0.3:
                    anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.RESOURCE_STARVATION,
                        severity=AnomalySeverity.HIGH,
                        component=f"{edge.source}->{edge.target}",
                        dimension="starvation",
                        value=src.cpu_usage,
                        expected_range=(0.0, 0.6),
                        confidence=0.75,
                        description=f"Resource starvation: {edge.source} starved ({src.cpu_usage:.0%}) while {edge.target} idle ({tgt.cpu_usage:.0%})",
                        evidence=[f"Source CPU: {src.cpu_usage:.2f}", f"Target CPU: {tgt.cpu_usage:.2f}"],
                    ))
        return anomalies

    def _detect_dependency_cycle(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect dependency cycles."""
        anomalies = []
        # Simplified: check for cycles in topology
        for comp in self.topology.components:
            if comp in self._find_cycles(comp, set(), set()):
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.DEPENDENCY_CYCLE,
                    severity=AnomalySeverity.MEDIUM,
                    component=comp,
                    dimension="cycle",
                    value=1.0,
                    expected_range=(0.0, 0.0),
                    confidence=0.6,
                    description=f"Dependency cycle involving {comp}",
                    evidence=["Cycle detected in causal graph"],
                ))
        return anomalies

    def _find_cycles(self, node: str, visited: Set[str], rec_stack: Set[str]) -> List[str]:
        """Find cycles in causal graph."""
        visited.add(node)
        rec_stack.add(node)

        cycles = []
        for edge in self.topology.causal_edges:
            if edge.source == node:
                if edge.target in rec_stack:
                    cycles.append(edge.target)
                elif edge.target not in visited:
                    cycles.extend(self._find_cycles(edge.target, visited, rec_stack))
        rec_stack.remove(node)
        return cycles

    def _detect_config_mismatch(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect configuration mismatches."""
        anomalies = []
        for comp_name, state in recon.reconstructed_services.items():
            if state.config_changed_recently and state.error_rate > 0.05:
                anomalies.append(Anomaly(
                    anomaly_type=AnomalyType.CONFIG_MISMATCH,
                    severity=AnomalySeverity.HIGH,
                    component=comp_name,
                    dimension="config",
                    value=state.error_rate,
                    expected_range=(0.0, 0.02),
                    confidence=0.8,
                    description=f"Config mismatch: recent config change + elevated errors ({state.error_rate:.1%})",
                    evidence=["config_changed=true", f"error_rate={state.error_rate:.3f}"],
                ))
        return anomalies

    def _detect_deployment_anomaly(self, recon: HolographicReconstruction, temporal: Optional[Dict]) -> List[Anomaly]:
        """Detect deployment-related anomalies."""
        anomalies = []
        deployed = [c for c, s in recon.reconstructed_services.items() if s.config_version]
        if len(deployed) >= 2:
            for comp_name in deployed:
                state = recon.reconstructed_services[comp_name]
                if state.error_rate > 0.1 and state.cpu_usage > 0.7:
                    anomalies.append(Anomaly(
                        anomaly_type=AnomalyType.DEPLOYMENT_ANOMALY,
                        severity=AnomalySeverity.HIGH,
                        component=comp_name,
                        dimension="deployment",
                        value=state.error_rate,
                        expected_range=(0.0, 0.05),
                        confidence=0.85,
                        description=f"Deployment anomaly: {comp_name} shows high errors post-deployment",
                        evidence=[f"error_rate={state.error_rate:.3f}", f"cpu_usage={state.cpu_usage:.2f}"],
                    ))
        return anomalies

    def _map_dimension_to_anomaly(self, dimension: str) -> AnomalyType:
        """Map dimension name to anomaly type."""
        mapping = {
            "cpu_usage": AnomalyType.CPU_SATURATION,
            "memory_usage": AnomalyType.MEMORY_EXHAUSTION,
            "network_usage": AnomalyType.NETWORK_CONGESTION,
            "error_rate": AnomalyType.ERROR_SPIKE,
            "latency_p99_ms": AnomalyType.LATENCY_DEGRADATION,
        }
        return mapping.get(dimension, AnomalyType.CPU_SATURATION)

    def _compute_severity(self, value: float, threshold: float) -> AnomalySeverity:
        """Compute severity from value vs threshold."""
        ratio = value / max(threshold, 1e-6)
        if ratio >= 2.0:
            return AnomalySeverity.CRITICAL
        elif ratio >= 1.5:
            return AnomalySeverity.HIGH
        elif ratio >= 1.2:
            return AnomalySeverity.MEDIUM
        else:
            return AnomalySeverity.LOW

    def _compute_component_scores(
        self,
        reconstruction: HolographicReconstruction,
        report: AnomalyReport,
    ) -> Dict[str, float]:
        """Compute anomaly score per component."""
        scores = {}
        for comp_name in reconstruction.reconstructed_services:
            comp_anomalies = [a for a in report.anomalies if a.component == comp_name]
            if not comp_anomalies:
                scores[comp_name] = 0.0
                continue

            score = sum(a.confidence * (a.severity.value + 1) for a in comp_anomalies)
            # Normalize
            max_possible = len(comp_anomalies) * 1.0 * 5.0
            scores[comp_name] = min(1.0, score / max_possible) if max_possible > 0 else 0.0

        return scores

    def _generate_summary(self, report: AnomalyReport) -> str:
        """Generate human-readable summary."""
        if not report.anomalies:
            return "No anomalies detected."

        critical = report.severity_counts.get(AnomalySeverity.CRITICAL, 0)
        high = report.severity_counts.get(AnomalySeverity.HIGH, 0)
        medium = report.severity_counts.get(AnomalySeverity.MEDIUM, 0)
        low = report.severity_counts.get(AnomalySeverity.LOW, 0)

        parts = []
        if critical:
            parts.append(f"{critical} critical")
        if high:
            parts.append(f"{high} high")
        if medium:
            parts.append(f"{medium} medium")
        if low:
            parts.append(f"{low} low")

        top_component = max(report.component_scores.items(), key=lambda x: x[1], default=(None, 0))
        if top_component[0]:
            parts.append(f"top: {top_component[0]} ({top_component[1]:.0%})")

        return f"Detected {len(report.anomalies)} anomalies: {', '.join(parts)}"


def create_anomaly_detector(topology: SystemTopology) -> HolographicAnomalyDetector:
    """Create anomaly detector with default configuration."""
    return HolographicAnomalyDetector(topology)


if __name__ == "__main__":
    # Quick test
    import sys
    sys.path.insert(0, 'tests/holographic')
    from synthetic import SyntheticIncidentGenerator, IncidentType
    from cauveris.holographic.integration import analyze_incident_holographically, HolographicConfig

    generator = SyntheticIncidentGenerator(seed=42)
    incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)

    config = HolographicConfig(enable_multiscale=False, enable_compression=False)
    result = analyze_incident_holographically(
        incident_id=incident.incident_id,
        timeline=incident.timeline,
        topology=incident.topology,
        config=config,
    )

    print(f"Original fidelity: {result.overall_fidelity:.3f}")

    # Create detector and run
    detector = create_anomaly_detector(incident.topology)
    report = detector.detect(result.reconstruction, temporal_data={"root_cause": "svc_0/cpu_pressure"})

    print(f"\nAnomaly Report:")
    print(f"  Summary: {report.summary}")
    print(f"  Total anomalies: {len(report.anomalies)}")
    for anomaly in report.get_high_anomalies():
        print(f"  [{anomaly.severity.name}] {anomaly.component} / {anomaly.dimension}: {anomaly.description}")
    print(f"  Component scores: {report.component_scores}")
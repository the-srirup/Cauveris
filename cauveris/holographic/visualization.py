"""
Holographic Reconstruction Visualization - Generates data for visualization.

Produces structured data for:
- 3D bulk state rendering
- Causal graph visualization
- Boundary layer heatmaps
- Ambiguity region display
- Counterfactual comparison
- Multi-scale hierarchy display
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import json

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
from .counterfactual import CounterfactualResult, Intervention
from .anomaly import AnomalyReport, Anomaly, AnomalyType, AnomalySeverity


class VisualizationFormat(Enum):
    """Output formats for visualization."""
    JSON = "json"
    MERMAID = "mermaid"
    PLOTLY = "plotly"
    D3 = "d3"
    THREEJS = "threejs"


@dataclass
class VisualizationData:
    """Complete visualization data package."""
    incident_id: str
    timestamp_ns: int
    format: VisualizationFormat = VisualizationFormat.JSON

    # Bulk state
    bulk_nodes: List[Dict[str, Any]] = field(default_factory=list)
    bulk_edges: List[Dict[str, Any]] = field(default_factory=list)

    # Boundary layers
    boundary_layers: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Multi-scale
    scale_hierarchy: List[Dict[str, Any]] = field(default_factory=list)

    # Ambiguity
    ambiguity_regions: List[Dict[str, Any]] = field(default_factory=list)

    # Counterfactual
    counterfactual: Optional[Dict[str, Any]] = None

    # Anomalies
    anomalies: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(asdict(self), default=str, indent=2)

    def save(self, path: str) -> None:
        """Save to file."""
        with open(path, 'w') as f:
            f.write(self.to_json())


class VisualizationDataGenerator:
    """
    Generates visualization data from holographic reconstruction.

    Produces data structures optimized for different visualization backends.
    """

    def __init__(
        self,
        topology: SystemTopology,
        incident_id: str = "",
        timestamp_ns: int = 0,
    ):
        self.topology = topology
        self.incident_id = incident_id
        self.timestamp_ns = timestamp_ns

        # Color schemes
        self.severity_colors = {
            AnomalySeverity.INFO: "#6b7280",
            AnomalySeverity.LOW: "#f59e0b",
            AnomalySeverity.MEDIUM: "#f97316",
            AnomalySeverity.HIGH: "#ef4444",
            AnomalySeverity.CRITICAL: "#7f1d1d",
        }

        self.component_colors = {
            "service": "#3b82f6",
            "database": "#8b5cf6",
            "cache": "#06b6d4",
            "gateway": "#ec4899",
            "message_queue": "#84cc16",
        }

        self.layer_colors = {
            BoundaryLayer.APPLICATION_LOG: "#10b981",
            BoundaryLayer.METRICS_EXPORT: "#3b82f6",
            BoundaryLayer.DISTRIBUTED_TRACE: "#8b5cf6",
            BoundaryLayer.NETWORK_FLOW: "#f59e0b",
            BoundaryLayer.INFRASTRUCTURE_LOG: "#6b7280",
        }

    def generate(
        self,
        reconstruction: HolographicReconstruction,
        counterfactual: Optional[CounterfactualResult] = None,
        anomalies: Optional[AnomalyReport] = None,
        scale_results: Optional[Dict] = None,
    ) -> VisualizationData:
        """
        Generate complete visualization data.

        Args:
            reconstruction: Main reconstruction
            counterfactual: Optional counterfactual result
            anomalies: Optional anomaly report
            scale_results: Optional multi-scale results

        Returns:
            VisualizationData with all visualization-ready structures
        """
        viz = VisualizationData(
            incident_id=self.incident_id or reconstruction.incident_id,
            timestamp_ns=self.timestamp_ns or reconstruction.reconstruction_timestamp_ns,
        )

        # Generate bulk state visualization
        viz.bulk_nodes = self._generate_bulk_nodes(reconstruction)
        viz.bulk_edges = self._generate_bulk_edges(reconstruction)

        # Generate boundary layer heatmaps
        viz.boundary_layers = self._generate_boundary_layers(reconstruction)

        # Generate multi-scale hierarchy
        if scale_results:
            viz.scale_hierarchy = self._generate_scale_hierarchy(scale_results)

        # Generate ambiguity regions
        viz.ambiguity_regions = self._generate_ambiguity_regions(reconstruction)

        # Generate counterfactual comparison
        if counterfactual:
            viz.counterfactual = self._generate_counterfactual(counterfactual)

        # Generate anomalies
        if anomalies:
            viz.anomalies = [a.to_dict() for a in anomalies.anomalies]

        # Metadata
        viz.metadata = {
            "overall_fidelity": reconstruction.overall_fidelity,
            "boundary_residual": reconstruction.boundary_residual,
            "num_components": len(reconstruction.reconstructed_services),
            "num_ambiguity_regions": len(reconstruction.ambiguity_regions),
            "time_window_ns": reconstruction.time_window_ns,
            "generation_timestamp_ns": self.timestamp_ns,
        }

        return viz

    def _generate_bulk_nodes(
        self,
        reconstruction: HolographicReconstruction,
    ) -> List[Dict[str, Any]]:
        """Generate 3D bulk node data."""
        nodes = []

        for comp_name, state in reconstruction.reconstructed_services.items():
            comp = self.topology.components.get(comp_name)
            if not comp:
                continue

            # Compute 3D position based on topology
            pos = self._compute_3d_position(comp_name)

            # Node size based on load
            size = 10 + (state.cpu_usage + state.memory_usage) * 30

            # Color based on health
            health = 1.0 - max(state.cpu_usage, state.memory_usage, state.error_rate * 5)
            color = self._health_to_color(health)

            node = {
                "id": comp_name,
                "name": comp_name,
                "type": comp.component_type,
                "position": pos,
                "size": size,
                "color": color,
                "health": health,
                "metrics": {
                    "cpu_usage": state.cpu_usage,
                    "memory_usage": state.memory_usage,
                    "network_usage": state.network_usage,
                    "error_rate": state.error_rate,
                    "latency_p99_ms": state.latency_p99_ms,
                },
                "confidence": state.confidence,
                "config_changed": state.config_changed_recently,
            }
            nodes.append(node)

        return nodes

    def _generate_bulk_edges(
        self,
        reconstruction: HolographicReconstruction,
    ) -> List[Dict[str, Any]]:
        """Generate 3D bulk edge data (causal dependencies)."""
        edges = []

        for edge in self.topology.causal_edges:
            if edge.source in reconstruction.reconstructed_services and edge.target in reconstruction.reconstructed_services:
                src_state = reconstruction.reconstructed_services[edge.source]
                tgt_state = reconstruction.reconstructed_services[edge.target]

                # Edge thickness based on interaction strength
                thickness = 1 + (src_state.cpu_usage + tgt_state.cpu_usage) * 3

                # Edge color based on health of connection
                if src_state.error_rate > 0.1 or tgt_state.error_rate > 0.1:
                    color = "#ef4444"
                elif src_state.cpu_usage > 0.8 or tgt_state.cpu_usage > 0.8:
                    color = "#f97316"
                else:
                    color = "#94a3b8"

                edge_data = {
                    "source": edge.source,
                    "target": edge.target,
                    "type": "causal",
                    "thickness": thickness,
                    "color": color,
                    "latency_ms": edge.latency_ms,
                    "source_health": 1.0 - max(src_state.cpu_usage, src_state.error_rate * 5),
                    "target_health": 1.0 - max(tgt_state.cpu_usage, tgt_state.error_rate * 5),
                }
                edges.append(edge_data)

        # Add network edges if available
        if reconstruction.reconstructed_network:
            for (src, dst), net_edge in reconstruction.reconstructed_network.edges.items():
                edge_data = {
                    "source": src,
                    "target": dst,
                    "type": "network",
                    "thickness": 2,
                    "color": "#06b6d4",
                    "latency_ms": net_edge.latency_ms,
                    "loss_rate": net_edge.loss_rate,
                    "bandwidth_mbps": net_edge.bandwidth_mbps,
                }
                edges.append(edge_data)

        return edges

    def _generate_boundary_layers(
        self,
        reconstruction: HolographicReconstruction,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate boundary layer heatmap data.

        Aggregates the observed HEUs per (component, layer) into signal
        intensities (from HEU payloads) and bulk-dimension weights (from the
        HEU holographic encoding).
        """
        layers = {}

        observed_heus = getattr(reconstruction, 'observed_heus', {}) or {}

        for comp_name, state in reconstruction.reconstructed_services.items():
            comp = self.topology.components.get(comp_name)
            if not comp:
                continue

            comp_heus = observed_heus.get(comp_name, [])
            if not comp_heus:
                continue

            layer_data = {}
            for layer in comp.boundary_layers:
                layer_name = layer.value if hasattr(layer, 'value') else str(layer)
                layer_heus = [h for h in comp_heus if h.boundary_layer == layer]

                if not layer_heus:
                    continue

                # Aggregate numeric payload signals across HEUs in this layer
                signal_values: Dict[str, List[float]] = {}
                for heu in layer_heus:
                    for key, raw in (heu.payload or {}).items():
                        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                            signal_values.setdefault(key, []).append(float(raw))

                signals = {
                    key: {
                        "value": float(np.mean(vals)),
                        "count": len(vals),
                        "min": float(np.min(vals)),
                        "max": float(np.max(vals)),
                    }
                    for key, vals in signal_values.items()
                }

                # Aggregate holographic encoding: which bulk dims this layer informs
                dim_weights: Dict[str, List[float]] = {}
                for heu in layer_heus:
                    for dim, weight in (heu.encoded_dimensions or {}).items():
                        dim_weights.setdefault(dim, []).append(float(weight))

                encoded = {
                    dim: float(np.mean(vals)) for dim, vals in dim_weights.items()
                }

                reconstruction_weight = float(
                    np.mean([h.reconstruction_weight for h in layer_heus])
                )
                ambiguity = float(np.mean([h.ambiguity_score for h in layer_heus]))

                layer_data[layer_name] = {
                    "layer": layer_name,
                    "component": comp_name,
                    "num_heus": len(layer_heus),
                    "signals": signals,
                    "encoded_dimensions": encoded,
                    "reconstruction_weight": reconstruction_weight,
                    "ambiguity_score": ambiguity,
                    "synthesized_ratio": float(
                        np.mean([1.0 if h.is_synthesized else 0.0 for h in layer_heus])
                    ),
                    "color": self.layer_colors.get(layer, "#6b7280"),
                }

            if layer_data:
                layers[comp_name] = layer_data

        return layers

    def _generate_scale_hierarchy(
        self,
        scale_results: Dict,
    ) -> List[Dict[str, Any]]:
        """Generate multi-scale hierarchy visualization."""
        hierarchy = []

        for scale, result in scale_results.items():
            scale_name = scale.name if hasattr(scale, 'name') else str(scale)
            hierarchy.append({
                "scale": scale_name,
                "time_window_ns": result.reconstruction.time_window_ns if hasattr(result.reconstruction, 'time_window_ns') else (0, 0),
                "fidelity": result.reconstruction.overall_fidelity,
                "num_components": len(result.reconstruction.reconstructed_services),
                "prior_chained": getattr(scale_results.get(scale), 'prior_chained_from', None) is not None,
            })

        return hierarchy

    def _generate_ambiguity_regions(
        self,
        reconstruction: HolographicReconstruction,
    ) -> List[Dict[str, Any]]:
        """Generate ambiguity region visualization data."""
        regions = []

        for region in reconstruction.ambiguity_regions:
            regions.append({
                "component": region.component,
                "dimension": region.dimension,
                "primary_value": region.primary_value,
                "ci_lower": region.primary_value - region.confidence_interval_width / 2,
                "ci_upper": region.primary_value + region.confidence_interval_width / 2,
                "ci_width": region.confidence_interval_width,
                "entropy": region.posterior_entropy,
                "num_alternatives": len(region.alternative_hypotheses),
                "alternatives": [
                    {"value": h.value, "probability": h.probability}
                    for h in region.alternative_hypotheses[:5]  # Top 5
                ],
                "severity": (
                    "high" if region.confidence_interval_width > 0.5
                    else "medium" if region.confidence_interval_width > 0.2
                    else "low"
                ),
            })

        return regions

    def _generate_counterfactual(
        self,
        counterfactual: CounterfactualResult,
    ) -> Dict[str, Any]:
        """Generate counterfactual comparison visualization."""
        orig = counterfactual.original_reconstruction
        interv = counterfactual.intervened_reconstruction

        # Compare states
        changes = []
        for comp_name in set(orig.reconstructed_services.keys()) | set(interv.reconstructed_services.keys()):
            if comp_name in orig.reconstructed_services and comp_name in interv.reconstructed_services:
                o = orig.reconstructed_services[comp_name]
                i = interv.reconstructed_services[comp_name]

                for dim in ["cpu_usage", "memory_usage", "error_rate", "latency_p99_ms"]:
                    o_val = getattr(o, dim, 0)
                    i_val = getattr(i, dim, 0)
                    diff = i_val - o_val

                    if abs(diff) > 0.01:
                        changes.append({
                            "component": comp_name,
                            "dimension": dim,
                            "original": o_val,
                            "intervened": i_val,
                            "change": diff,
                            "improvement": diff < 0,  # Lower is better for most dims
                        })

        return {
            "intervention": counterfactual.intervention.description,
            "intervention_type": counterfactual.intervention.intervention_type.value,
            "fidelity_improvement": counterfactual.fidelity_improvement,
            "cost_estimate": counterfactual.cost_estimate,
            "risk_score": counterfactual.risk_score,
            "changes": changes,
            "predicted_boundary": counterfactual.predicted_boundary,
        }

    def _compute_3d_position(self, comp_name: str) -> List[float]:
        """Compute 3D position for a component using force-directed layout."""
        # Simplified: arrange in grid based on topological order
        components = list(self.topology.components.keys())
        idx = components.index(comp_name) if comp_name in components else 0

        # Simple circular layout
        angle = (idx * 2 * np.pi) / max(1, len(components))
        radius = 100

        x = radius * np.cos(angle)
        y = radius * np.sin(angle)
        z = hash(comp_name) % 50  # Some variation in Z

        return [float(x), float(y), float(z)]

    def _health_to_color(self, health: float) -> str:
        """Convert health score (0-1) to color."""
        health = max(0.0, min(1.0, health))
        # Green to red gradient
        if health > 0.5:
            # Green to yellow
            r = int(255 * (1 - health) * 2)
            g = 255
            b = 0
        else:
            # Yellow to red
            r = 255
            g = int(255 * health * 2)
            b = 0
        return f"#{r:02x}{g:02x}{b:02x}"

    def generate_mermaid_graph(
        self,
        reconstruction: HolographicReconstruction,
        anomalies: Optional[AnomalyReport] = None,
    ) -> str:
        """Generate Mermaid graph for causal dependencies with anomalies."""
        lines = ["graph TD"]

        # Add nodes with styling
        for comp_name, state in reconstruction.reconstructed_services.items():
            comp = self.topology.components.get(comp_name)
            if not comp:
                continue

            health = 1.0 - max(state.cpu_usage, state.memory_usage, state.error_rate * 5)
            color = self._health_to_color(health)
            label = f"{comp_name}\\nCPU:{state.cpu_usage:.0%} MEM:{state.memory_usage:.0%} ERR:{state.error_rate:.1%}"

            # Determine shape based on component type
            if comp.component_type == "database":
                node_def = f'{comp_name}[("{label}")]'  # Stadium
            elif comp.component_type == "gateway":
                node_def = f'{comp_name}>{{{label}}}]'  # Subroutine
            else:
                node_def = f'{comp_name}["{label}"]'  # Rectangle

            lines.append(f"  {node_def}")
            lines.append(f"  style {comp_name} fill:{color},stroke:#333,stroke-width:2px")

        # Add anomaly indicators
        if anomalies:
            for anomaly in anomalies.get_high_anomalies():
                comp = anomaly.component.split("->")[0]  # Handle edge anomalies
                if comp in reconstruction.reconstructed_services:
                    color = self.severity_colors.get(anomaly.severity, "#ef4444")
                    lines.append(f"  style {comp} fill:{color},stroke:#7f1d1d,stroke-width:4px,stroke-dasharray: 5 5")

        # Add edges
        for edge in self.topology.causal_edges:
            if edge.source in reconstruction.reconstructed_services and edge.target in reconstruction.reconstructed_services:
                lines.append(f"  {edge.source} -->|{edge.latency_ms:.0f}ms| {edge.target}")

        # Add network edges
        if reconstruction.reconstructed_network:
            for (src, dst), net_edge in reconstruction.reconstructed_network.edges.items():
                lines.append(f"  {src} -.->|net {net_edge.latency_ms:.0f}ms| {dst}")

        return "\n".join(lines)

    def generate_plotly_3d(
        self,
        reconstruction: HolographicReconstruction,
    ) -> Dict[str, Any]:
        """Generate Plotly 3D scatter plot data."""
        bulk_nodes = self._generate_bulk_nodes(reconstruction)
        bulk_edges = self._generate_bulk_edges(reconstruction)

        # Nodes
        node_trace = {
            "type": "scatter3d",
            "mode": "markers+text",
            "x": [n["position"][0] for n in bulk_nodes],
            "y": [n["position"][1] for n in bulk_nodes],
            "z": [n["position"][2] for n in bulk_nodes],
            "text": [n["name"] for n in bulk_nodes],
            "marker": {
                "size": [n["size"] for n in bulk_nodes],
                "color": [n["color"] for n in bulk_nodes],
                "opacity": 0.8,
            },
            "hovertemplate": (
                "%{text}<br>CPU: %{customdata[0]:.1%}<br>MEM: %{customdata[1]:.1%}"
                "<br>ERR: %{customdata[2]:.1%}<br>LAT: %{customdata[3]:.0f}ms<extra></extra>"
            ),
            "customdata": [
                [n["metrics"]["cpu_usage"], n["metrics"]["memory_usage"],
                 n["metrics"]["error_rate"], n["metrics"]["latency_p99_ms"]]
                for n in bulk_nodes
            ],
        }

        # Edges
        edge_traces = []
        for edge in bulk_edges:
            src_idx = next(i for i, n in enumerate(bulk_nodes) if n["id"] == edge["source"])
            tgt_idx = next(i for i, n in enumerate(bulk_nodes) if n["id"] == edge["target"])

            src_pos = bulk_nodes[src_idx]["position"]
            tgt_pos = bulk_nodes[tgt_idx]["position"]

            edge_traces.append({
                "type": "scatter3d",
                "mode": "lines",
                "x": [src_pos[0], tgt_pos[0], None],
                "y": [src_pos[1], tgt_pos[1], None],
                "z": [src_pos[2], tgt_pos[2], None],
                "line": {"color": edge["color"], "width": edge["thickness"]},
                "showlegend": False,
                "hoverinfo": "none",
            })

        return {
            "data": [node_trace] + edge_traces,
            "layout": {
                "title": f"Holographic Reconstruction - {self.incident_id}",
                "scene": {
                    "xaxis": {"title": "X"},
                    "yaxis": {"title": "Y"},
                    "zaxis": {"title": "Z"},
                },
                "showlegend": False,
            }
        }


def generate_visualization_data(
    topology: SystemTopology,
    reconstruction: HolographicReconstruction,
    counterfactual: Optional[CounterfactualResult] = None,
    anomalies: Optional[AnomalyReport] = None,
    scale_results: Optional[Dict] = None,
    incident_id: str = "",
    timestamp_ns: int = 0,
) -> VisualizationData:
    """
    Convenience function to generate visualization data.

    Main integration point for PipelineOrchestrator.
    """
    generator = VisualizationDataGenerator(topology, incident_id, timestamp_ns)
    return generator.generate(reconstruction, counterfactual, anomalies, scale_results)


if __name__ == "__main__":
    # Quick test
    import sys
    sys.path.insert(0, 'tests/holographic')
    from synthetic import SyntheticIncidentGenerator, IncidentType
    from cauveris.holographic.integration import analyze_incident_holographically, HolographicConfig
    from cauveris.holographic.counterfactual import create_standard_interventions, CounterfactualHolographer, CausalKernelBuilder, Intervention, InterventionType
    from cauveris.holographic.anomaly import create_anomaly_detector

    generator = SyntheticIncidentGenerator(seed=42)
    incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)

    config = HolographicConfig(enable_multiscale=False, enable_compression=False)
    result = analyze_incident_holographically(
        incident_id=incident.incident_id,
        timeline=incident.timeline,
        topology=incident.topology,
        config=config,
    )

    print(f"Generating visualization for {incident.incident_id}...")

    # Build kernels
    kernel_builder = CausalKernelBuilder(incident.topology)
    kernel_builder.build_all_kernels()

    # Counterfactual
    holographer = CounterfactualHolographer(incident.topology, kernel_builder)
    intervention = Intervention(intervention_type=InterventionType.CPU_SCALING, target_component="svc_0", parameters={"scale_factor": 4.0})
    cf_result = holographer.simulate(result.reconstruction, intervention, result.time_window_ns)

    # Anomalies
    detector = create_anomaly_detector(incident.topology)
    anomaly_report = detector.detect(result.reconstruction)

    # Generate visualization
    viz_gen = VisualizationDataGenerator(incident.topology, incident.incident_id, result.reconstruction.reconstruction_timestamp_ns)
    viz_data = viz_gen.generate(result.reconstruction, cf_result, anomaly_report)

    print(f"Bulk nodes: {len(viz_data.bulk_nodes)}")
    print(f"Bulk edges: {len(viz_data.bulk_edges)}")
    print(f"Boundary layers: {len(viz_data.boundary_layers)} components")
    print(f"Ambiguity regions: {len(viz_data.ambiguity_regions)}")
    print(f"Anomalies: {len(viz_data.anomalies)}")

    # Generate Mermaid
    mermaid = viz_gen.generate_mermaid_graph(result.reconstruction, anomaly_report)
    print(f"\nMermaid graph ({len(mermaid)} chars)")

    # Save JSON
    output_path = "test_visualization.json"
    viz_data.save(output_path)
    print(f"\nSaved to {output_path}")
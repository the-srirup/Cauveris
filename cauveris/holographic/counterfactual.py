"""
Counterfactual Holography - What-if simulations for hypothesis testing.

Given a reconstructed bulk state, applies interventions and forward-projects
to predict how boundary observations would change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable
from enum import Enum
from copy import deepcopy

import numpy as np

from .topology import SystemTopology, ComponentInfo, CausalEdge, ResourceCapacity
from .heu import HolographicEvidenceUnit, BoundaryLayer
from .heu_kernel import CausalKernelBuilder, KernelConfig
from .measurement import build_measurement_system, MeasurementConfig
from .solver import HolographicSolver, SolverConfig, SolverMethod, solve_holographic_inverse
from .integration import HolographicAnalysisResult, analyze_incident_holographically
from .reconstruction import (
    HolographicReconstruction,
    ReconstructedServiceState,
    NetworkEdge,
)


class InterventionType(Enum):
    """Types of interventions for counterfactual analysis."""
    CPU_SCALING = "cpu_scaling"              # Scale CPU cores up/down
    MEMORY_SCALING = "memory_scaling"        # Scale memory up/down
    RESTART_SERVICE = "restart_service"      # Simulate service restart
    ROLLBACK_DEPLOYMENT = "rollback_deployment"  # Revert config
    INCREASE_CACHE = "increase_cache"        # Increase cache size
    SCALE_DEPENDENCY = "scale_dependency"    # Scale upstream dependency
    NETWORK_CAPACITY = "network_capacity"    # Increase network bandwidth
    TRAFFIC_REDUCTION = "traffic_reduction"  # Reduce incoming load
    CIRCUIT_BREAKER = "circuit_breaker"      # Enable circuit breaker


@dataclass(slots=True)
class Intervention:
    """A single intervention to apply to the bulk state."""
    intervention_type: InterventionType
    target_component: str
    parameters: Dict[str, float] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self):
        if not self.description:
            self.description = f"{self.intervention_type.value} on {self.target_component}"


@dataclass
class CounterfactualResult:
    """Result of a counterfactual simulation."""
    original_reconstruction: HolographicReconstruction
    intervened_reconstruction: HolographicReconstruction
    predicted_boundary: Dict[str, Any]  # Predicted HEUs after intervention
    intervention: Intervention
    fidelity_improvement: float
    boundary_changes: Dict[str, float]  # dimension -> change magnitude
    cost_estimate: float  # Relative cost of intervention
    risk_score: float  # Risk of intervention causing issues (0-1)


class CounterfactualHolographer:
    """
    Counterfactual simulation engine for holographic reconstructions.

    Given a reconstruction of current state, applies interventions to the
    bulk state and forward-projects through the causal kernels to predict
    what boundary evidence would look like.
    """

    def __init__(
        self,
        topology: SystemTopology,
        kernel_builder: CausalKernelBuilder,
        temporal_analysis: Optional[Dict[str, Any]] = None,
    ):
        self.topology = topology
        self.kernel_builder = kernel_builder
        self.temporal_analysis = temporal_analysis

    def simulate(
        self,
        reconstruction: HolographicReconstruction,
        intervention: Intervention,
        window_ns: Tuple[int, int],
    ) -> CounterfactualResult:
        """
        Run counterfactual simulation.

        Args:
            reconstruction: Current reconstructed state
            intervention: Intervention to apply
            window_ns: Time window for forward projection

        Returns:
            CounterfactualResult with predicted boundary and comparison
        """
        # Apply intervention to create modified bulk state
        intervened_state = self._apply_intervention(reconstruction, intervention)

        # Forward project to boundary using causal kernels
        predicted_boundary = self._forward_project_to_boundary(
            intervened_state, window_ns
        )

        # Compute metrics
        fidelity_improvement = self._compute_fidelity_improvement(
            reconstruction, intervened_state
        )
        boundary_changes = self._compute_boundary_changes(
            reconstruction, predicted_boundary
        )
        cost_estimate = self._estimate_cost(intervention)
        risk_score = self._estimate_risk(intervention)

        return CounterfactualResult(
            original_reconstruction=reconstruction,
            intervened_reconstruction=intervened_state,
            predicted_boundary=predicted_boundary,
            intervention=intervention,
            fidelity_improvement=fidelity_improvement,
            boundary_changes=boundary_changes,
            cost_estimate=cost_estimate,
            risk_score=risk_score,
        )

    def _apply_intervention(
        self,
        reconstruction: HolographicReconstruction,
        intervention: Intervention,
    ) -> HolographicReconstruction:
        """Apply intervention to create modified reconstruction."""
        intervened = deepcopy(reconstruction)

        if intervention.target_component not in intervened.reconstructed_services:
            return intervened

        service = intervened.reconstructed_services[intervention.target_component]
        params = intervention.parameters

        if intervention.intervention_type == InterventionType.CPU_SCALING:
            scale_factor = params.get("scale_factor", 2.0)
            service.cpu_usage = min(1.0, service.cpu_usage / scale_factor)
            service.confidence = max(0.5, service.confidence * 0.9)

        elif intervention.intervention_type == InterventionType.MEMORY_SCALING:
            scale_factor = params.get("scale_factor", 2.0)
            service.memory_usage = min(1.0, service.memory_usage / scale_factor)
            service.confidence = max(0.5, service.confidence * 0.9)

        elif intervention.intervention_type == InterventionType.RESTART_SERVICE:
            service.cpu_usage = min(service.cpu_usage * 0.3, 0.2)
            service.memory_usage = min(service.memory_usage * 0.5, 0.3)
            service.error_rate = min(service.error_rate * 0.1, 0.01)
            service.confidence = 0.8

        elif intervention.intervention_type == InterventionType.ROLLBACK_DEPLOYMENT:
            service.config_changed_recently = False
            service.config_version = params.get("previous_version", "prev")
            service.error_rate = min(service.error_rate * 0.2, 0.02)
            service.confidence = 0.9

        elif intervention.intervention_type == InterventionType.INCREASE_CACHE:
            # Cache increase reduces downstream pressure
            service.memory_usage = min(service.memory_usage + 0.1, 0.8)
            service.cpu_usage = max(service.cpu_usage - 0.1, 0.1)
            # Propagate to downstream
            self._propagate_to_downstream(intervened, intervention.target_component, scale=0.8)

        elif intervention.intervention_type == InterventionType.SCALE_DEPENDENCY:
            scale_factor = params.get("scale_factor", 2.0)
            # Find upstream dependencies
            for edge in self.topology.causal_edges:
                if edge.target == intervention.target_component:
                    upstream = intervened.reconstructed_services.get(edge.source)
                    if upstream:
                        upstream.cpu_usage = min(1.0, upstream.cpu_usage / scale_factor)
                        upstream.memory_usage = min(1.0, upstream.memory_usage / scale_factor)

        elif intervention.intervention_type == InterventionType.NETWORK_CAPACITY:
            bandwidth_factor = params.get("bandwidth_factor", 2.0)
            if intervened.reconstructed_network:
                for (src, dst), net_edge in intervened.reconstructed_network.edges.items():
                    if src == intervention.target_component or dst == intervention.target_component:
                        net_edge.bandwidth_mbps *= bandwidth_factor
                        net_edge.latency_ms *= 0.7

        elif intervention.intervention_type == InterventionType.TRAFFIC_REDUCTION:
            reduction = params.get("reduction_factor", 0.5)
            service.cpu_usage *= reduction
            service.network_usage *= reduction
            service.error_rate *= reduction

        elif intervention.intervention_type == InterventionType.CIRCUIT_BREAKER:
            # Circuit breaker reduces errors but may increase latency
            service.error_rate = min(service.error_rate * 0.1, 0.01)
            service.latency_p99_ms = service.latency_p99_ms * 1.5

        return intervened

    def _propagate_to_downstream(
        self,
        reconstruction: HolographicReconstruction,
        component: str,
        scale: float = 0.8,
    ) -> None:
        """Propagate improvements to downstream services."""
        for edge in self.topology.causal_edges:
            if edge.source == component and edge.target in reconstruction.reconstructed_services:
                downstream = reconstruction.reconstructed_services[edge.target]
                downstream.cpu_usage *= scale
                downstream.memory_usage *= scale
                downstream.error_rate *= scale
                # Recursively propagate
                self._propagate_to_downstream(reconstruction, edge.target, scale)

    def _forward_project_to_boundary(
        self,
        reconstruction: HolographicReconstruction,
        window_ns: Tuple[int, int],
    ) -> Dict[str, Any]:
        """
        Forward project bulk state to predicted boundary observations.

        Uses the causal kernels to compute what HEUs would be generated
        from the intervened bulk state.
        """
        predicted = {
            "service_predictions": {},
            "network_predictions": {},
            "layer_predictions": {},
        }

        start_ns, end_ns = window_ns
        duration = end_ns - start_ns

        # Predict for each service
        for svc_name, svc_state in reconstruction.reconstructed_services.items():
            comp = self.topology.components.get(svc_name)
            if not comp:
                continue

            predictions = {}
            for layer in comp.boundary_layers:
                layer_pred = self._predict_layer_obs(
                    comp, layer, svc_state, duration
                )
                predictions[layer.value if hasattr(layer, 'value') else str(layer)] = layer_pred

            predicted["service_predictions"][svc_name] = predictions

        # Predict network
        if reconstruction.reconstructed_network:
            for (src, dst), net_edge in reconstruction.reconstructed_network.edges.items():
                predicted["network_predictions"][f"{src}->{dst}"] = {
                    "latency_ms": net_edge.latency_ms,
                    "loss_rate": net_edge.loss_rate,
                    "bandwidth_mbps": net_edge.bandwidth_mbps,
                }

        return predicted

    def _predict_layer_obs(
        self,
        comp: ComponentInfo,
        layer: BoundaryLayer,
        state: ReconstructedServiceState,
        duration_ns: int,
    ) -> Dict[str, Any]:
        """Predict observations for a specific boundary layer."""
        layer_name = layer.value if hasattr(layer, 'value') else str(layer)

        # Get kernel for this component/layer
        kernel_key = (comp.name, layer_name)
        kernel = self.kernel_builder._local_kernels.get(kernel_key)

        if not kernel:
            return {"status": "no_kernel"}

        # Map reconstructed state to boundary signals
        # This is a simplified forward model
        pred = {
            "layer": layer_name,
            "component": comp.name,
            "predicted_signals": {},
        }

        if layer == BoundaryLayer.APPLICATION_LOG:
            pred["predicted_signals"]["cpu_usage"] = state.cpu_usage
            pred["predicted_signals"]["memory_usage"] = state.memory_usage
            pred["predicted_signals"]["error_rate"] = state.error_rate
            pred["predicted_signals"]["log_level"] = "ERROR" if state.error_rate > 0.1 else "WARN" if state.cpu_usage > 0.8 else "INFO"

        elif layer == BoundaryLayer.METRICS_EXPORT:
            pred["predicted_signals"]["cpu_usage"] = state.cpu_usage
            pred["predicted_signals"]["memory_usage"] = state.memory_usage
            pred["predicted_signals"]["latency_p99_ms"] = state.latency_p99_ms
            pred["predicted_signals"]["rps"] = max(100, 10000 * (1 - state.cpu_usage))

        elif layer == BoundaryLayer.DISTRIBUTED_TRACE:
            pred["predicted_signals"]["duration_ms"] = state.latency_p99_ms
            pred["predicted_signals"]["error"] = state.error_rate > 0.1
            pred["predicted_signals"]["span_count"] = max(10, 100 * (1 - state.error_rate))

        elif layer == BoundaryLayer.NETWORK_FLOW:
            pred["predicted_signals"]["bytes_per_sec"] = state.network_usage * 10_000_000
            pred["predicted_signals"]["latency_ms"] = state.latency_p99_ms
            pred["predicted_signals"]["retransmits"] = int(state.error_rate * 100)

        elif layer == BoundaryLayer.INFRASTRUCTURE_LOG:
            pred["predicted_signals"]["cpu_usage"] = state.cpu_usage
            pred["predicted_signals"]["memory_usage"] = state.memory_usage
            pred["predicted_signals"]["disk_io"] = 0.3 * state.memory_usage

        return pred

    def _compute_fidelity_improvement(
        self,
        original: HolographicReconstruction,
        intervened: HolographicReconstruction,
    ) -> float:
        """Compute how much intervention improves overall health fidelity."""
        orig_health = self._compute_system_health(original)
        int_health = self._compute_system_health(intervened)
        return int_health - orig_health

    def _compute_system_health(self, reconstruction: HolographicReconstruction) -> float:
        """Compute aggregate system health score."""
        if not reconstruction.reconstructed_services:
            return 0.0

        health_scores = []
        for svc in reconstruction.reconstructed_services.values():
            health = 1.0 - max(
                svc.cpu_usage * 0.4,
                svc.memory_usage * 0.3,
                svc.error_rate * 0.3,
            )
            health_scores.append(max(0.0, health))

        return float(np.mean(health_scores)) if health_scores else 0.0

    def _compute_boundary_changes(
        self,
        original: HolographicReconstruction,
        predicted: Dict[str, Any],
    ) -> Dict[str, float]:
        """Compute expected changes in boundary observations."""
        changes = {}

        for svc_name, layer_preds in predicted.get("service_predictions", {}).items():
            for layer, pred in layer_preds.items():
                signals = pred.get("predicted_signals", {})
                for signal, value in signals.items():
                    key = f"{svc_name}.{layer}.{signal}"
                    # Would compare with actual observed in real implementation
                    changes[key] = 0.0  # Placeholder

        return changes

    def _estimate_cost(self, intervention: Intervention) -> float:
        """Estimate relative cost of intervention (0-100)."""
        cost_map = {
            InterventionType.CPU_SCALING: 30.0,
            InterventionType.MEMORY_SCALING: 25.0,
            InterventionType.RESTART_SERVICE: 5.0,
            InterventionType.ROLLBACK_DEPLOYMENT: 10.0,
            InterventionType.INCREASE_CACHE: 15.0,
            InterventionType.SCALE_DEPENDENCY: 40.0,
            InterventionType.NETWORK_CAPACITY: 50.0,
            InterventionType.TRAFFIC_REDUCTION: 20.0,
            InterventionType.CIRCUIT_BREAKER: 5.0,
        }
        return cost_map.get(intervention.intervention_type, 20.0)

    def _estimate_risk(self, intervention: Intervention) -> float:
        """Estimate risk of intervention (0-1)."""
        risk_map = {
            InterventionType.CPU_SCALING: 0.2,
            InterventionType.MEMORY_SCALING: 0.15,
            InterventionType.RESTART_SERVICE: 0.4,  # Connection disruption
            InterventionType.ROLLBACK_DEPLOYMENT: 0.3,
            InterventionType.INCREASE_CACHE: 0.1,
            InterventionType.SCALE_DEPENDENCY: 0.3,
            InterventionType.NETWORK_CAPACITY: 0.25,
            InterventionType.TRAFFIC_REDUCTION: 0.1,
            InterventionType.CIRCUIT_BREAKER: 0.35,  # False positives
        }
        base_risk = risk_map.get(intervention.intervention_type, 0.2)

        # Increase risk for critical services
        comp = self.topology.components.get(intervention.target_component)
        if comp and comp.component_type in ["database", "gateway"]:
            base_risk *= 1.5

        return min(1.0, base_risk)

    def run_rollout(
        self,
        reconstruction: HolographicReconstruction,
        interventions: List[Intervention],
        window_ns: Tuple[int, int],
    ) -> Dict[str, CounterfactualResult]:
        """Run multiple interventions and rank by cost-effectiveness."""
        results = {}
        for intervention in interventions:
            result = self.simulate(reconstruction, intervention, window_ns)
            results[intervention.description] = result

        return results

    def get_recommendations(
        self,
        rollout: Dict[str, CounterfactualResult],
        max_cost: float = 50.0,
        max_risk: float = 0.5,
    ) -> List[Tuple[str, CounterfactualResult]]:
        """Get ranked intervention recommendations."""
        candidates = []
        for desc, result in rollout.items():
            if result.cost_estimate <= max_cost and result.risk_score <= max_risk:
                # Score = fidelity_improvement / (cost * risk)
                score = result.fidelity_improvement / (result.cost_estimate * result.risk_score + 1e-6)
                candidates.append((score, desc, result))

        candidates.sort(reverse=True, key=lambda x: x[0])
        return [(desc, result) for score, desc, result in candidates]


def create_standard_interventions(topology: SystemTopology) -> List[Intervention]:
    """Create standard intervention set for a topology."""
    interventions = []

    for comp_name, comp in topology.components.items():
        # Scale resources
        interventions.append(Intervention(
            intervention_type=InterventionType.CPU_SCALING,
            target_component=comp_name,
            parameters={"scale_factor": 2.0},
        ))

        interventions.append(Intervention(
            intervention_type=InterventionType.MEMORY_SCALING,
            target_component=comp_name,
            parameters={"scale_factor": 2.0},
        ))

        # Restart
        interventions.append(Intervention(
            intervention_type=InterventionType.RESTART_SERVICE,
            target_component=comp_name,
        ))

        # Circuit breaker for services
        if comp.component_type == "service":
            interventions.append(Intervention(
                intervention_type=InterventionType.CIRCUIT_BREAKER,
                target_component=comp_name,
            ))

    # Network capacity for gateway
    for comp_name, comp in topology.components.items():
        if comp.component_type == "gateway":
            interventions.append(Intervention(
                intervention_type=InterventionType.NETWORK_CAPACITY,
                target_component=comp_name,
                parameters={"bandwidth_factor": 2.0},
            ))

    return interventions


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

    # Build kernels for counterfactual
    kernel_builder = CausalKernelBuilder(incident.topology)
    kernel_builder.build_all_kernels()

    # Run counterfactual
    holographer = CounterfactualHolographer(
        incident.topology,
        kernel_builder,
    )

    intervention = Intervention(
        intervention_type=InterventionType.CPU_SCALING,
        target_component="svc_0",
        parameters={"scale_factor": 4.0},
    )

    cf_result = holographer.simulate(
        result.reconstruction,
        intervention,
        result.time_window_ns,
    )

    print(f"\nCounterfactual: {intervention.description}")
    print(f"  Fidelity improvement: {cf_result.fidelity_improvement:.3f}")
    print(f"  Cost: {cf_result.cost_estimate:.1f}")
    print(f"  Risk: {cf_result.risk_score:.2f}")
    print(f"  Predicted boundary signals: {len(cf_result.predicted_boundary.get('service_predictions', {}))} services")
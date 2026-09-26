"""
Multi-Scale Holographic Reconstruction - Hierarchical bulk reconstruction.

Implements hierarchical reconstruction across 4 scales:
- SYSTEMIC (hours-days): Chronic patterns, capacity trends
- INCIDENT (minutes-hours): Full incident reconstruction
- TRANSACTION (seconds-minutes): Business transaction flow
- REQUEST (milliseconds-seconds): Single trace span detail
"""
from __future__ import annotations

import numpy as np
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from .heu import HolographicEvidenceUnit, BoundaryLayer, convert_timeline_to_heus
from .topology import SystemTopology, ComponentInfo
from .reconstruction import HolographicReconstruction, ReconstructedServiceState, AmbiguityRegion
from .solver import HolographicSolver, SolverConfig, solve_holographic_inverse
from .measurement import build_measurement_system, MeasurementConfig
from .heu_kernel import CausalKernelBuilder, KernelConfig


class ReconstructionScale(Enum):
    """Temporal scales for multi-scale reconstruction."""
    SYSTEMIC = "systemic"       # Hours to days
    INCIDENT = "incident"       # Minutes to hours
    TRANSACTION = "transaction" # Seconds to minutes
    REQUEST = "request"         # Milliseconds to seconds

    @property
    def time_window_ns(self) -> int:
        """Time window in nanoseconds."""
        return {
            ReconstructionScale.SYSTEMIC: 24 * 60 * 60 * 1_000_000_000,  # 24 hours
            ReconstructionScale.INCIDENT: 60 * 60 * 1_000_000_000,       # 1 hour
            ReconstructionScale.TRANSACTION: 60 * 1_000_000_000,         # 1 minute
            ReconstructionScale.REQUEST: 1_000_000_000,                   # 1 second
        }[self]

    @property
    def target_heu_count(self) -> int:
        """Target HEU count for this scale."""
        return {
            ReconstructionScale.SYSTEMIC: 100,
            ReconstructionScale.INCIDENT: 1000,
            ReconstructionScale.TRANSACTION: 100,
            ReconstructionScale.REQUEST: 10,
        }[self]

    @property
    def solver_config(self) -> SolverConfig:
        """Solver configuration per scale."""
        configs = {
            ReconstructionScale.SYSTEMIC: SolverConfig(
                lambda_entropy=0.05,
                lambda_temporal=0.1,
                lambda_physics=5.0,
                max_iterations=200,
            ),
            ReconstructionScale.INCIDENT: SolverConfig(
                lambda_entropy=0.1,
                lambda_temporal=0.01,
                lambda_physics=10.0,
                max_iterations=500,
            ),
            ReconstructionScale.TRANSACTION: SolverConfig(
                lambda_entropy=0.15,
                lambda_temporal=0.005,
                lambda_physics=15.0,
                max_iterations=300,
            ),
            ReconstructionScale.REQUEST: SolverConfig(
                lambda_entropy=0.2,
                lambda_temporal=0.0,
                lambda_physics=20.0,
                max_iterations=200,
            ),
        }
        return configs[self]


@dataclass(slots=True)
class ScaleReconstruction:
    """Reconstruction result at a specific scale."""
    scale: ReconstructionScale
    time_window_ns: Tuple[int, int]          # (start, end)
    heus: List[HolographicEvidenceUnit]
    reconstruction: HolographicReconstruction
    solver_result: Any
    parent_scale: Optional["ScaleReconstruction"] = None
    child_scales: List["ScaleReconstruction"] = field(default_factory=list)

    def get_prior_for_child(self) -> Optional[np.ndarray]:
        """Get prior state for child scale from this scale's result."""
        if not self.solver_result or not self.solver_result.success:
            return None
        return self.solver_result.x


@dataclass
class MultiScaleConfig:
    """Configuration for multi-scale reconstruction."""
    target_scales: List[ReconstructionScale] = field(default_factory=lambda: [
        ReconstructionScale.SYSTEMIC,
        ReconstructionScale.INCIDENT,
        ReconstructionScale.TRANSACTION,
        ReconstructionScale.REQUEST,
    ])
    enable_prior_chaining: bool = True
    min_heus_per_scale: int = 5
    max_heus_per_scale: int = 5000


class MultiScaleReconstructor:
    """
    Hierarchical holographic reconstructor across multiple temporal scales.

    Reconstructs system state at each scale, using coarse-scale results
    as priors for finer scales (prior chaining).
    """

    def __init__(
        self,
        topology: SystemTopology,
        config: Optional[MultiScaleConfig] = None,
    ):
        self.topology = topology
        self.config = config or MultiScaleConfig()
        self._kernel_builder = CausalKernelBuilder(topology)
        self._kernel_builder.build_all_kernels()

    def reconstruct(
        self,
        timeline_events: List[Dict[str, Any]],
        incident_time_window: Tuple[int, int],
        raw_signals: Optional[Dict] = None,
    ) -> Dict[ReconstructionScale, ScaleReconstruction]:
        """
        Perform multi-scale holographic reconstruction.

        Args:
            timeline_events: Full timeline events from Cauveris
            incident_time_window: (start_ns, end_ns) of incident
            raw_signals: Raw signals from RawSignalExtractor

        Returns:
            Dict mapping scale to ScaleReconstruction
        """
        start_ns, end_ns = incident_time_window
        incident_duration = end_ns - start_ns

        # 1. Convert all timeline events to HEUs
        all_heus = convert_timeline_to_heus(timeline_events, raw_signals or {}, incident_duration)

        # 2. Reconstruct at each scale (coarsest to finest for prior chaining)
        results = {}
        prior_chain = None

        for scale in self.config.target_scales:
            if scale not in results:  # Only if not explicit scale order
                continue

        # Ensure correct order: systemic -> incident -> transaction -> request
        for scale in [
            ReconstructionScale.SYSTEMIC,
            ReconstructionScale.INCIDENT,
            ReconstructionScale.TRANSACTION,
            ReconstructionScale.REQUEST,
        ]:
            if scale not in self.config.target_scales:
                continue

            scale_result = self._reconstruct_at_scale(
                scale,
                all_heus,
                incident_time_window,
                prior_chain,
            )

            if scale_result:
                results[scale] = scale_result
                prior_chain = scale_result
            else:
                results[scale] = None

        return results

    def _reconstruct_at_scale(
        self,
        scale: ReconstructionScale,
        all_heus: List[HolographicEvidenceUnit],
        incident_window: Tuple[int, int],
        prior: Optional[ScaleReconstruction],
    ) -> Optional[ScaleReconstruction]:
        """Reconstruct at a single scale."""
        start_ns, end_ns = incident_window

        # Downsample HEUs for this scale
        scale_heus = self._downsample_heus(all_heus, scale, start_ns, end_ns)

        if len(scale_heus) < self.config.min_heus_per_scale:
            print(f"Scale {scale.value}: insufficient HEUs ({len(scale_heus)})")
            return None

        # Build measurement system
        measurement_config = MeasurementConfig(
            max_observations=self.config.max_heus_per_scale,
        )
        measurement_system = build_measurement_system(
            self.topology,
            scale_heus,
            end_ns - start_ns,
            self._kernel_builder,
            measurement_config,
        )

        # Solve
        solver_config = scale.solver_config
        x_prior = None
        if self.config.enable_prior_chaining and prior and prior.solver_result:
            x_prior = prior.get_prior_for_child()

        result = solve_holographic_inverse(
            measurement_system,
            self.topology,
            solver_config,
            x_prior,
        )

        # Build HolographicReconstruction from result
        reconstruction = self._build_reconstruction(result, measurement_system, scale, start_ns, end_ns)

        return ScaleReconstruction(
            scale=scale,
            time_window_ns=incident_window,
            heus=scale_heus,
            reconstruction=reconstruction,
            solver_result=result,
        )

    def _downsample_heus(
        self,
        heus: List[HolographicEvidenceUnit],
        scale: ReconstructionScale,
        start_ns: int,
        end_ns: int,
    ) -> List[HolographicEvidenceUnit]:
        """Downsample HEUs to target count for scale."""
        target = scale.target_heu_count
        window = end_ns - start_ns

        if len(heus) <= target:
            return heus

        # Strategy: stratified sampling by boundary layer and time
        # First, filter to time window
        in_window = [h for h in heus if start_ns <= h.timestamp_ns <= end_ns]

        # Group by boundary layer
        by_layer = defaultdict(list)
        for h in in_window:
            by_layer[h.boundary_layer].append(h)

        # Sample proportionally from each layer
        total = len(in_window)
        selected = []

        for layer, layer_heus in by_layer.items():
            layer_target = max(1, int(target * len(layer_heus) / total))
            # Temporal stratification within layer
            if len(layer_heus) <= layer_target:
                selected.extend(layer_heus)
            else:
                # Sample uniformly across time
                step = len(layer_heus) // layer_target
                selected.extend(layer_heus[::step][:layer_target])

        return selected

    def _build_reconstruction(
        self,
        solver_result,
        measurement_system,
        scale: ReconstructionScale,
        start_ns: int,
        end_ns: int,
    ) -> HolographicReconstruction:
        """Build HolographicReconstruction from solver result."""
        recon = HolographicReconstruction(
            incident_id=f"INC-{scale.value.upper()}-{start_ns // 1_000_000_000}",
            reconstruction_timestamp_ns=end_ns,
            time_window_ns=(start_ns, end_ns),
            overall_fidelity=1.0 - solver_result.boundary_residual,
        )

        if not solver_result.success:
            return recon

        # Decode state
        decoded = solver_result.x  # Direct state vector for now

        # Create service states
        from .reconstruction import ReconstructedServiceState, ReconstructedNetworkState
        import scipy.sparse as sp

        # Map state indices to components
        for i, sd in enumerate(measurement_system.state_dims):
            comp_name = sd.component
            dim = sd.dimension
            val = float(np.clip(decoded[i] if i < len(decoded) else 0, 0, 1))

            if comp_name not in recon.reconstructed_services:
                recon.reconstructed_services[comp_name] = ReconstructedServiceState(
                    component_name=comp_name,
                    instance_id=comp_name.split("_")[-1] if "_" in comp_name else "instance-1",
                )

            svc = recon.reconstructed_services[comp_name]
            if dim == "cpu_pressure":
                svc.cpu_usage = val
            elif dim == "memory_pressure":
                svc.memory_usage = val
            elif dim == "network_latency":
                svc.network_usage = val
            elif dim == "error_rate":
                svc.error_rate = val
            elif dim == "config_change":
                svc.config_version = f"changed_{val:.2f}"
            elif dim == "deployment_activity":
                svc.deployment_version = f"deploy_{val:.2f}"

        # Add ambiguity regions for low-confidence areas
        for i, sd in enumerate(measurement_system.state_dims):
            if i < len(decoded):
                val = decoded[i]
                # Low confidence if reconstruction weight was low or boundary residual high
                if val < 0.1 or val > 1.0:
                    recon.ambiguity_regions.append(AmbiguityRegion(
                        component=sd.component,
                        time_range_ns=(start_ns, end_ns),
                        affected_dimensions=[sd.dimension],
                        ambiguity_score=abs(val - 0.5) * 0.5,
                        missing_layers=[],
                        description=f"Ambiguous {sd.dimension} at scale {scale.value}",
                    ))

        return recon

    def compare_scales(self, results: Dict[ReconstructionScale, ScaleReconstruction]) -> Dict:
        """Compare reconstructions across scales."""
        comparison = {
            "fidelity_by_scale": {},
            "state_consistency": {},
            "ambiguity_by_scale": {},
        }

        for scale, scale_result in results.items():
            if not scale_result:
                continue

            comparison["fidelity_by_scale"][scale.value] = scale_result.reconstruction.overall_fidelity

            # Count ambiguous regions
            n_amb = len(scale_result.reconstruction.ambiguity_regions)
            comparison["ambiguity_by_scale"][scale.value] = n_amb

            # Service states
            services = scale_result.reconstruction.reconstructed_services
            comparison["state_consistency"][scale.value] = {
                k: {k2: v2 for k2, v2 in vars(v).items() if not k2.startswith('_')}
                for k, v in services.items()
            }

        return comparison


def reconstruct_multiscale(
    topology: SystemTopology,
    timeline_events: List[Dict[str, Any]],
    incident_time_window: Tuple[int, int],
    raw_signals: Optional[Dict] = None,
    config: Optional[MultiScaleConfig] = None,
) -> Dict[ReconstructionScale, ScaleReconstruction]:
    """
    Convenience function for multi-scale reconstruction.

    Args:
        topology: System topology
        timeline_events: Timeline events
        incident_time_window: (start_ns, end_ns)
        raw_signals: Raw signals
        config: Multi-scale configuration

    Returns:
        Dict of scale reconstructions
    """
    reconstructor = MultiScaleReconstructor(topology, config)
    return reconstructor.reconstruct(timeline_events, incident_time_window, raw_signals)


if __name__ == "__main__":
    from .topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge

    topo = SystemTopology()
    topo.add_component(ComponentInfo(name="svc_a", capacity=ResourceCapacity(cpu_cores=4.0), boundary_layers=["application_log", "metrics_export", "distributed_trace"]))
    topo.add_component(ComponentInfo(name="svc_b", capacity=ResourceCapacity(cpu_cores=2.0), boundary_layers=["application_log", "metrics_export"]))
    topo.add_causal_edge(CausalEdge(source="svc_a", target="svc_b", latency_ms=5.0))

    # Timeline with events across time scales
    timeline = []
    for i in range(100):
        timeline.append({
            "event_id": f"evt_{i}",
            "timestamp_ns": i * 10_000_000,  # 10ms steps
            "source_type": "jsonl_log" if i % 3 != 0 else "csv_metrics",
            "message": "Test event",
            "attributes": {"service": "svc_a" if i % 2 == 0 else "svc_b", "cpu_usage": 0.5 + 0.3 * np.sin(i * 0.1)},
            "status": "ok",
        })

    results = reconstruct_multiscale(topo, timeline, (0, 1_000_000_000))
    for scale, result in results.items():
        if result:
            print(f"{scale.value}: {len(result.heus)} HEUs, fidelity={result.reconstruction.overall_fidelity:.3f}")
        else:
            print(f"{scale.value}: SKIPPED")
"""
Holographic Analyzer - Main integration point for Cauveris pipeline.

Provides async analysis interface that connects holographic reconstruction
to the existing temporal analysis and pipeline infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .topology import SystemTopology, ComponentInfo, ResourceCapacity, CausalEdge, build_topology_from_timeline
from .heu import HolographicEvidenceUnit, BoundaryLayer, convert_timeline_to_heus
from .heu_kernel import CausalKernelBuilder, KernelConfig
from .measurement import build_measurement_system, MeasurementConfig
from .solver import HolographicSolver, SolverConfig, SolverMethod, solve_holographic_inverse
from .multiscale import MultiScaleReconstructor, MultiScaleConfig, ReconstructionScale, reconstruct_multiscale
from .compression import HolographicCompressor, CompressionConfig, CompressionMethod, compress_holographic, EvidenceSynthesizer
from .reconstruction import (
    HolographicReconstruction,
    ReconstructedServiceState,
    ReconstructedNetworkState,
    NetworkEdge,
    ReconstructedResourceState,
    AmbiguityRegion,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HolographicConfig:
    """Configuration for holographic analysis."""
    # Solver settings
    solver_method: SolverMethod = SolverMethod.SLSQP
    max_iterations: int = 200
    lambda_data: float = 1.0
    lambda_entropy: float = 0.1
    lambda_temporal: float = 0.01
    lambda_physics: float = 10.0

    # Multi-scale settings
    enable_multiscale: bool = True
    target_scales: List[ReconstructionScale] = field(default_factory=lambda: [
        ReconstructionScale.INCIDENT,
        ReconstructionScale.TRANSACTION,
    ])
    enable_prior_chaining: bool = True

    # Compression settings
    enable_compression: bool = True
    compression_method: CompressionMethod = CompressionMethod.HYBRID
    target_compression_ratio: float = 10.0
    min_fidelity_retention: float = 0.90

    # Synthesis settings
    enable_synthesis: bool = True

    # Phase 4: analysis layers
    enable_anomaly_detection: bool = True
    anomaly_sensitivity: float = 1.0
    enable_visualization_data: bool = True

    # Cross-reference with temporal analysis
    enable_temporal_crossref: bool = True

    # Performance
    max_heus_for_full_solve: int = 5000
    use_incremental_for_large: bool = True


@dataclass
class HolographicAnalysisResult:
    """Complete result of holographic analysis."""
    incident_id: str
    timestamp_ns: int
    time_window_ns: Tuple[int, int]

    # Core reconstruction
    reconstruction: HolographicReconstruction

    # Multi-scale results (if enabled)
    scale_results: Dict[ReconstructionScale, Any] = field(default_factory=dict)

    # Compression result (if enabled)
    compression_result: Optional[Any] = None

    # Synthesized evidence (if enabled)
    synthesized_heus: List[HolographicEvidenceUnit] = field(default_factory=list)

    # Phase 4 layers (if enabled)
    anomaly_report: Optional[Any] = None
    visualization_data: Optional[Any] = None

    # Quality metrics
    overall_fidelity: float = 0.0
    boundary_residual: float = 0.0
    solve_time_ms: float = 0.0
    compression_ratio: float = 1.0
    fidelity_retention: float = 1.0

    # Cross-references
    temporal_crossref: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    heu_count: int = 0
    compressed_heu_count: int = 0
    state_dimensions: int = 0
    solver_iterations: int = 0
    warnings: List[str] = field(default_factory=list)


class HolographicAnalyzer:
    """
    Main entry point for holographic evidence reconstruction.

    Integrates with Cauveris pipeline:
    - Takes timeline events + topology
    - Produces HolographicReconstruction
    - Cross-references with temporal analysis results
    """

    def __init__(
        self,
        config: Optional[HolographicConfig] = None,
    ):
        self.config = config or HolographicConfig()
        self._kernel_builder: Optional[CausalKernelBuilder] = None
        self._topology: Optional[SystemTopology] = None
        self._reconstructor: Optional[MultiScaleReconstructor] = None
        self._compressor: Optional[HolographicCompressor] = None
        self._synthesizer: Optional[EvidenceSynthesizer] = None

    def analyze_incident(
        self,
        incident_id: str,
        timeline: List[Dict[str, Any]],
        topology: Optional[SystemTopology] = None,
        bundle_config: Optional[Dict[str, Any]] = None,
        temporal_analysis: Optional[Dict[str, Any]] = None,
    ) -> HolographicAnalysisResult:
        """
        Analyze an incident holographically.

        Args:
            incident_id: Unique incident identifier
            timeline: List of timeline events (from TimelineBuilder)
            topology: Pre-built topology (optional, will be inferred from timeline if not provided)
            bundle_config: Full incident bundle config (for topology inference)
            temporal_analysis: Results from TemporalAnalyzer for cross-reference

        Returns:
            HolographicAnalysisResult with full reconstruction
        """
        import time
        start_time = time.time()

        # Build or use topology
        if topology is None:
            if bundle_config:
                topology = build_topology_from_timeline(timeline, bundle_config)
            else:
                topology = build_topology_from_timeline(timeline, {})
        self._topology = topology

        # Build HEUs
        window = self._infer_time_window(timeline)
        heus = convert_timeline_to_heus(timeline, temporal_analysis or {}, window[1])
        logger.info(f"Generated {len(heus)} HEUs from timeline")

        if len(heus) == 0:
            return self._empty_result(incident_id, window)

        # Check if compression needed
        original_heus = heus
        compression_result = None
        if self.config.enable_compression and len(heus) > self.config.max_heus_for_full_solve:
            comp_config = CompressionConfig(
                method=self.config.compression_method,
                target_compression_ratio=self.config.target_compression_ratio,
                min_fidelity_retention=self.config.min_fidelity_retention,
                verify_fidelity=True,
            )
            logger.info(f"Compressing {len(heus)} HEUs...")
            self._compressor = HolographicCompressor(topology, comp_config)
            compression_result = self._compressor.compress(heus, window[1])
            heus = compression_result.compressed_heus
            logger.info(f"Compressed to {len(heus)} HEUs (ratio: {compression_result.compression_ratio:.1f}x, "
                       f"fidelity: {compression_result.fidelity_retention:.3f})")

        # Build causal kernels
        kernel_config = KernelConfig()
        self._kernel_builder = CausalKernelBuilder(topology, kernel_config)
        self._kernel_builder.build_all_kernels()

        # Build measurement system
        measurement_config = MeasurementConfig()
        system = build_measurement_system(topology, heus, window[1], self._kernel_builder, measurement_config)
        logger.info(f"Measurement system: {system.n_obs} obs, {system.n_state} state dims")

        # Solve inverse problem
        solver_config = SolverConfig(
            method=self.config.solver_method,
            max_iterations=self.config.max_iterations,
            lambda_data=self.config.lambda_data,
            lambda_entropy=self.config.lambda_entropy,
            lambda_temporal=self.config.lambda_temporal,
            lambda_physics=self.config.lambda_physics,
        )
        solver = HolographicSolver(system, topology, solver_config)
        solver_result = solver.solve()

        # Decode reconstruction
        decoded = solver.decode_state(solver_result.x)
        reconstruction = self._build_reconstruction(incident_id, window, decoded, solver_result, topology)

        # Multi-scale reconstruction
        scale_results = {}
        if self.config.enable_multiscale:
            ms_config = MultiScaleConfig(
                target_scales=self.config.target_scales,
                enable_prior_chaining=self.config.enable_prior_chaining,
            )
            self._reconstructor = MultiScaleReconstructor(topology, ms_config)
            scale_results = reconstruct_multiscale(topology, timeline, window, {})
            # Update reconstruction fidelity from finest scale
            if scale_results:
                finest = min(scale_results.keys(), key=lambda s: s.time_window_ns)
                if scale_results[finest]:
                    reconstruction.overall_fidelity = scale_results[finest].reconstruction.overall_fidelity

        # Evidence synthesis for missing layers
        synthesized_heus = []
        if self.config.enable_synthesis:
            self._synthesizer = EvidenceSynthesizer(topology)
            observed_layers = self._get_observed_layers(heus)
            synthesized_heus = self._synthesizer.synthesize_missing_layers(
                reconstruction, observed_layers, window
            )
            logger.info(f"Synthesized {len(synthesized_heus)} HEUs for missing layers")

        # Temporal cross-reference
        temporal_crossref = {}
        if self.config.enable_temporal_crossref and temporal_analysis:
            temporal_crossref = self._cross_reference_temporal(reconstruction, temporal_analysis)

        # Attach observed evidence to the reconstruction for downstream consumers
        reconstruction.observed_heus = self._group_heus_by_component(heus)
        reconstruction.observed_layers = self._get_observed_layers(heus)
        reconstruction.missing_boundary_layers = [
            f"{comp}.{layer.value}" if hasattr(layer, "value") else f"{comp}.{layer}"
            for comp, layers in self._missing_layers(topology, reconstruction.observed_layers).items()
            for layer in layers
        ]

        # Phase 4: anomaly detection
        anomaly_report = None
        if self.config.enable_anomaly_detection:
            from .anomaly import HolographicAnomalyDetector

            detector = HolographicAnomalyDetector(
                topology, sensitivity=self.config.anomaly_sensitivity
            )
            anomaly_report = detector.detect(
                reconstruction, temporal_data=temporal_analysis
            )
            logger.info(f"Anomaly detection: {anomaly_report.summary}")

        # Phase 4: visualization data
        visualization_data = None
        if self.config.enable_visualization_data:
            from .visualization import generate_visualization_data

            visualization_data = generate_visualization_data(
                topology=topology,
                reconstruction=reconstruction,
                anomalies=anomaly_report,
                scale_results=scale_results or None,
                incident_id=incident_id,
                timestamp_ns=window[1],
            )

        solve_time_ms = (time.time() - start_time) * 1000

        return HolographicAnalysisResult(
            incident_id=incident_id,
            timestamp_ns=window[1],
            time_window_ns=window,
            reconstruction=reconstruction,
            scale_results=scale_results,
            compression_result=compression_result,
            synthesized_heus=synthesized_heus,
            anomaly_report=anomaly_report,
            visualization_data=visualization_data,
            overall_fidelity=reconstruction.overall_fidelity,
            boundary_residual=solver_result.boundary_residual,
            solve_time_ms=solve_time_ms,
            compression_ratio=compression_result.compression_ratio if compression_result else 1.0,
            fidelity_retention=compression_result.fidelity_retention if compression_result else 1.0,
            temporal_crossref=temporal_crossref,
            heu_count=len(original_heus),
            compressed_heu_count=len(heus),
            state_dimensions=system.n_state,
            solver_iterations=solver_result.iterations,
        )

    def _infer_time_window(self, timeline: List[Dict]) -> Tuple[int, int]:
        """Infer time window from timeline events."""
        if not timeline:
            return (0, 60_000_000_000)

        timestamps = [e.get("timestamp_ns", 0) for e in timeline if e.get("timestamp_ns")]
        if not timestamps:
            return (0, 60_000_000_000)

        start = min(timestamps)
        end = max(timestamps)
        # Add 10% padding
        padding = int((end - start) * 0.1 + 1_000_000_000)
        return (max(0, start - padding), end + padding)

    def _build_reconstruction(
        self,
        incident_id: str,
        window: Tuple[int, int],
        decoded: Dict,
        solver_result: Any,
        topology: SystemTopology,
    ) -> HolographicReconstruction:
        """Build HolographicReconstruction from solver output."""
        recon = HolographicReconstruction(
            incident_id=incident_id,
            reconstruction_timestamp_ns=window[1],
            time_window_ns=window,
        )

        # Service states
        for svc_name, svc_data in decoded.get("services", {}).items():
            recon.reconstructed_services[svc_name] = ReconstructedServiceState(
                component_name=svc_name,
                instance_id=f"{svc_name}-1",  # Would be resolved from topology
                cpu_usage=svc_data.get("cpu_pressure", 0.0),
                memory_usage=svc_data.get("memory_pressure", 0.0),
                network_usage=svc_data.get("network_latency", 0.0),
                error_rate=svc_data.get("error_rate", 0.0),
                config_version=svc_data.get("config_change", 0.0) > 0.5,
            )

        # Network edges
        if recon.reconstructed_network is None:
            recon.reconstructed_network = ReconstructedNetworkState()
        for edge in topology.causal_edges:
            # Simplified - would use measurement system in real implementation
            recon.reconstructed_network.add_edge(
                edge.source,
                edge.target,
                NetworkEdge(
                    source=edge.source,
                    target=edge.target,
                    latency_ms=edge.latency_ms,
                    loss_rate=0.0,  # Would be from reconstruction
                    bandwidth_mbps=1000.0,
                )
            )

        # Overall fidelity
        recon.overall_fidelity = max(0.0, 1.0 - solver_result.boundary_residual)
        recon.boundary_residual = solver_result.boundary_residual
        recon.constraint_violation = solver_result.constraint_violation

        return recon

    def _get_observed_layers(self, heus: List[HolographicEvidenceUnit]) -> Dict[str, List[BoundaryLayer]]:
        """Get observed boundary layers per component."""
        observed = {}
        for heu in heus:
            if heu.source_component not in observed:
                observed[heu.source_component] = []
            if heu.boundary_layer not in observed[heu.source_component]:
                observed[heu.source_component].append(heu.boundary_layer)
        return observed

    def _group_heus_by_component(
        self, heus: List[HolographicEvidenceUnit]
    ) -> Dict[str, List[HolographicEvidenceUnit]]:
        """Group HEU objects by their source component."""
        grouped: Dict[str, List[HolographicEvidenceUnit]] = {}
        for heu in heus:
            grouped.setdefault(heu.source_component, []).append(heu)
        return grouped

    def _missing_layers(
        self,
        topology: SystemTopology,
        observed_layers: Dict[str, List[BoundaryLayer]],
    ) -> Dict[str, List[BoundaryLayer]]:
        """Determine which declared boundary layers have no observed evidence."""
        missing: Dict[str, List[BoundaryLayer]] = {}
        for comp_name, comp in topology.components.items():
            observed = set(observed_layers.get(comp_name, []))
            absent = [layer for layer in comp.boundary_layers if layer not in observed]
            if absent:
                missing[comp_name] = absent
        return missing

    def _cross_reference_temporal(
        self,
        reconstruction: HolographicReconstruction,
        temporal_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Cross-reference holographic reconstruction with temporal analysis."""
        crossref = {
            "agreement": {},
            "discrepancies": [],
            "enhanced_confidence": [],
        }

        # Compare root causes
        temporal_root = temporal_analysis.get("root_cause", {})
        holographic_root = self._get_holographic_root_cause(reconstruction)

        if temporal_root and holographic_root:
            crossref["agreement"]["root_cause"] = temporal_root == holographic_root
            if temporal_root != holographic_root:
                crossref["discrepancies"].append({
                    "type": "root_cause_mismatch",
                    "temporal": temporal_root,
                    "holographic": holographic_root,
                })
            else:
                crossref["enhanced_confidence"].append("root_cause")

        # Compare component states
        temporal_components = temporal_analysis.get("component_states", {})
        for comp, holo_state in reconstruction.reconstructed_services.items():
            if comp in temporal_components:
                temp_state = temporal_components[comp]
                # Compare CPU
                holo_cpu = holo_state.cpu_usage
                temp_cpu = temp_state.get("cpu", 0)
                diff = abs(holo_cpu - temp_cpu)
                if diff < 0.2:
                    crossref["agreement"][f"{comp}_cpu"] = True
                    crossref["enhanced_confidence"].append(f"{comp}_cpu")
                else:
                    crossref["discrepancies"].append({
                        "type": "cpu_mismatch",
                        "component": comp,
                        "temporal": temp_cpu,
                        "holographic": holo_cpu,
                        "diff": diff,
                    })

        return crossref

    def _get_holographic_root_cause(self, reconstruction: HolographicReconstruction) -> Optional[str]:
        """Extract primary root cause from reconstruction."""
        max_pressure = 0
        root = None
        for svc, state in reconstruction.reconstructed_services.items():
            for dim, val in state.__dict__.items():
                if val > max_pressure:
                    max_pressure = val
                    root = f"{svc}/{dim}"
        return root

    def _empty_result(self, incident_id: str, window: Tuple[int, int]) -> HolographicAnalysisResult:
        """Return empty result for edge cases."""
        return HolographicAnalysisResult(
            incident_id=incident_id,
            timestamp_ns=window[1],
            time_window_ns=window,
            reconstruction=HolographicReconstruction(
                incident_id=incident_id,
                reconstruction_timestamp_ns=window[1],
                time_window_ns=window,
            ),
            warnings=["No HEUs generated from timeline"],
        )

    def simulate_counterfactuals(
        self,
        result: HolographicAnalysisResult,
        interventions: Optional[List[Any]] = None,
        max_cost: float = 50.0,
        max_risk: float = 0.5,
        limit: int = 10,
    ) -> List[Tuple[str, Any]]:
        """
        Run counterfactual what-if simulations against a completed analysis.

        Args:
            result: A completed HolographicAnalysisResult
            interventions: Explicit interventions; defaults to a standard sweep
            max_cost: Filter out interventions costlier than this
            max_risk: Filter out interventions riskier than this
            limit: Maximum number of recommendations to return

        Returns:
            Ranked list of (description, CounterfactualResult)
        """
        from .counterfactual import (
            CounterfactualHolographer,
            create_standard_interventions,
        )

        topology = self._topology
        if topology is None:
            raise RuntimeError("No topology available; run analyze_incident first")

        if self._kernel_builder is None:
            self._kernel_builder = CausalKernelBuilder(topology)
            self._kernel_builder.build_all_kernels()

        holographer = CounterfactualHolographer(topology, self._kernel_builder)

        if interventions is None:
            interventions = create_standard_interventions(topology)

        rollout = holographer.run_rollout(
            result.reconstruction,
            interventions,
            result.time_window_ns,
        )

        recommendations = holographer.get_recommendations(
            rollout, max_cost=max_cost, max_risk=max_risk
        )
        return recommendations[:limit]

    async def simulate_counterfactuals_async(self, *args, **kwargs):
        """Async wrapper for simulate_counterfactuals."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.simulate_counterfactuals(*args, **kwargs)
        )

    async def analyze_incident_async(
        self,
        incident_id: str,
        timeline: List[Dict[str, Any]],
        topology: Optional[SystemTopology] = None,
        bundle_config: Optional[Dict[str, Any]] = None,
        temporal_analysis: Optional[Dict[str, Any]] = None,
    ) -> HolographicAnalysisResult:
        """Async wrapper for analyze_incident."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.analyze_incident,
            incident_id,
            timeline,
            topology,
            bundle_config,
            temporal_analysis,
        )


def analyze_incident_holographically(
    incident_id: str,
    timeline: List[Dict[str, Any]],
    topology: Optional[SystemTopology] = None,
    bundle_config: Optional[Dict[str, Any]] = None,
    temporal_analysis: Optional[Dict[str, Any]] = None,
    config: Optional[HolographicConfig] = None,
) -> HolographicAnalysisResult:
    """
    Convenience function for holographic analysis.

    Main integration point for PipelineOrchestrator.
    """
    analyzer = HolographicAnalyzer(config)
    return analyzer.analyze_incident(
        incident_id=incident_id,
        timeline=timeline,
        topology=topology,
        bundle_config=bundle_config,
        temporal_analysis=temporal_analysis,
    )


if __name__ == "__main__":
    # Quick test
    from .synthetic import SyntheticIncidentGenerator, IncidentType

    generator = SyntheticIncidentGenerator(seed=42)
    incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)

    config = HolographicConfig(
        enable_multiscale=True,
        enable_compression=False,
        enable_synthesis=True,
    )

    analyzer = HolographicAnalyzer(config)
    result = analyzer.analyze_incident(
        incident_id=incident.incident_id,
        timeline=incident.timeline,
        topology=incident.topology,
    )

    print(f"Analysis complete:")
    print(f"  Fidelity: {result.overall_fidelity:.3f}")
    print(f"  Boundary residual: {result.boundary_residual:.3f}")
    print(f"  Solve time: {result.solve_time_ms:.1f}ms")
    print(f"  State dims: {result.state_dimensions}")
    print(f"  HEUs: {result.heu_count}")
    print(f"  Scales: {len(result.scale_results)}")
    print(f"  Synthesized: {len(result.synthesized_heus)}")
    print(f"  Cross-ref: {result.temporal_crossref}")
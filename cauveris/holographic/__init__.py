"""
Holographic Evidence Reconstruction for Cauveris.

This module applies the holographic principle from theoretical physics to
distributed systems debugging, reconstructing complete internal system state
from boundary evidence (logs, traces, metrics at system interfaces).

Pipeline stages:
    heu        -> encode boundary evidence as holographic evidence units
    topology   -> infer the causal graph of the system under study
    heu_kernel -> build causal Green's functions for boundary<->bulk propagation
    measurement-> assemble the linear measurement system M·x = b
    solver     -> solve the (regularized) holographic inverse problem
    multiscale -> reconstruct hierarchically across time scales
    compression-> reduce evidence volume while bounding fidelity loss
    integration-> orchestrate the above into a single analysis result

Phase 4 analysis layers:
    counterfactual -> what-if interventions and ranked recommendations
    anomaly        -> failure-mode signature and threshold detection
    visualization  -> render-ready data for graphs, heatmaps and 3D bulk views
"""

from .heu import (
    HolographicEvidenceUnit,
    BoundaryLayer,
    convert_timeline_to_heus,
)
from .reconstruction import (
    HolographicReconstruction,
    ReconstructedServiceState,
    ReconstructedNetworkState,
    NetworkEdge,
    ReconstructedResourceState,
    AmbiguityRegion,
)
from .topology import (
    SystemTopology,
    ComponentInfo,
    CausalEdge,
    ResourceCapacity,
    build_topology_from_timeline,
)

# Phase 1-3 pipeline
from .heu_kernel import (
    CausalKernelBuilder,
    KernelConfig,
    LocalPropagationKernel,
    build_causal_kernels,
)
from .measurement import (
    MeasurementSystem,
    MeasurementSystemBuilder,
    MeasurementConfig,
    StateDimension,
    build_measurement_system,
)
from .solver import (
    HolographicSolver,
    SolverConfig,
    SolverMethod,
    SolverResult,
    solve_holographic_inverse,
)
from .multiscale import (
    MultiScaleReconstructor,
    MultiScaleConfig,
    ReconstructionScale,
    reconstruct_multiscale,
)
from .compression import (
    HolographicCompressor,
    CompressionConfig,
    CompressionMethod,
    CompressionResult,
    EvidenceSynthesizer,
    compress_holographic,
)
from .integration import (
    HolographicAnalyzer,
    HolographicConfig,
    HolographicAnalysisResult,
    analyze_incident_holographically,
)

# Phase 4 analysis layers
from .counterfactual import (
    CounterfactualHolographer,
    CounterfactualResult,
    Intervention,
    InterventionType,
    create_standard_interventions,
)
from .anomaly import (
    HolographicAnomalyDetector,
    AnomalyReport,
    Anomaly,
    AnomalyType,
    AnomalySeverity,
    create_anomaly_detector,
)
from .visualization import (
    VisualizationDataGenerator,
    VisualizationData,
    VisualizationFormat,
    generate_visualization_data,
)

__all__ = [
    # Core data structures
    "HolographicEvidenceUnit",
    "BoundaryLayer",
    "convert_timeline_to_heus",
    "HolographicReconstruction",
    "ReconstructedServiceState",
    "ReconstructedNetworkState",
    "NetworkEdge",
    "ReconstructedResourceState",
    "AmbiguityRegion",
    "SystemTopology",
    "ComponentInfo",
    "CausalEdge",
    "ResourceCapacity",
    "build_topology_from_timeline",
    # Causal kernels
    "CausalKernelBuilder",
    "KernelConfig",
    "LocalPropagationKernel",
    "build_causal_kernels",
    # Measurement system
    "MeasurementSystem",
    "MeasurementSystemBuilder",
    "MeasurementConfig",
    "StateDimension",
    "build_measurement_system",
    # Inverse solver
    "HolographicSolver",
    "SolverConfig",
    "SolverMethod",
    "SolverResult",
    "solve_holographic_inverse",
    # Multi-scale
    "MultiScaleReconstructor",
    "MultiScaleConfig",
    "ReconstructionScale",
    "reconstruct_multiscale",
    # Compression
    "HolographicCompressor",
    "CompressionConfig",
    "CompressionMethod",
    "CompressionResult",
    "EvidenceSynthesizer",
    "compress_holographic",
    # Integration
    "HolographicAnalyzer",
    "HolographicConfig",
    "HolographicAnalysisResult",
    "analyze_incident_holographically",
    # Counterfactual
    "CounterfactualHolographer",
    "CounterfactualResult",
    "Intervention",
    "InterventionType",
    "create_standard_interventions",
    # Anomaly detection
    "HolographicAnomalyDetector",
    "AnomalyReport",
    "Anomaly",
    "AnomalyType",
    "AnomalySeverity",
    "create_anomaly_detector",
    # Visualization
    "VisualizationDataGenerator",
    "VisualizationData",
    "VisualizationFormat",
    "generate_visualization_data",
]

"""
Holographic Reconstruction API endpoints.

Provides REST API for serving holographic visualization data to the frontend.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import numpy as np

from cauveris.holographic.visualization import (
    generate_visualization_data,
)
from cauveris.holographic.integration import analyze_incident_holographically, HolographicConfig
from cauveris.holographic.gpu_kernels import GPUConfig, DecayType as GPuDecayType, NormalizationType as GpuNormalizationType
from cauveris.holographic.counterfactual import CounterfactualHolographer, CausalKernelBuilder, Intervention, InterventionType
from cauveris.holographic.anomaly import create_anomaly_detector
from cauveris.holographic.synthetic import SyntheticIncidentGenerator, IncidentType

router = APIRouter(prefix="/holographic", tags=["holographic"])


def _convert_numpy_types(obj: Any) -> Any:
    """Recursively convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return type(obj)(_convert_numpy_types(v) for v in obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


class VisualizationRequest(BaseModel):
    incident_id: str
    enable_counterfactual: bool = False
    enable_anomalies: bool = True
    enable_multiscale: bool = True
    intervention_type: Optional[str] = None
    intervention_params: Optional[Dict[str, Any]] = None
    # GPU acceleration options
    use_gpu: bool = True
    gpu_decay_type: str = "exponential"
    gpu_normalization: str = "l1"
    gpu_time_step_ns: int = 1000000
    gpu_max_kernel_time_ns: int = 10000000000


class VisualizationResponse(BaseModel):
    incident_id: str
    bulk_nodes: List[Dict[str, Any]]
    bulk_edges: List[Dict[str, Any]]
    boundary_layers: Dict[str, Dict[str, Any]]
    scale_hierarchy: List[Dict[str, Any]]
    ambiguity_regions: List[Dict[str, Any]]
    counterfactual: Optional[Dict[str, Any]]
    anomalies: List[Dict[str, Any]]
    metadata: Dict[str, Any]


def _create_holographic_config(request: VisualizationRequest) -> HolographicConfig:
    """Create HolographicConfig from request."""
    gpu_config = GPUConfig(
        time_step_ns=request.gpu_time_step_ns,
        max_kernel_time_ns=request.gpu_max_kernel_time_ns,
        decay_type=GPuDecayType[request.gpu_decay_type.upper()],
        normalization=GpuNormalizationType[request.gpu_normalization.upper()],
        use_gpu=request.use_gpu,
    )
    return HolographicConfig(
        enable_multiscale=request.enable_multiscale,
        enable_anomaly_detection=request.enable_anomalies,
        enable_synthesis=request.enable_counterfactual,
        enable_visualization_data=True,
        enable_temporal_crossref=True,
        use_gpu=request.use_gpu,
        gpu_config=gpu_config,
    )


@router.get("/reconstruction")
async def get_holographic_reconstruction(
    incident_id: str = Query(..., description="Incident ID to reconstruct"),
    enable_counterfactual: bool = Query(False, description="Include counterfactual simulation"),
    enable_anomalies: bool = Query(True, description="Include anomaly detection"),
    enable_multiscale: bool = Query(True, description="Include multi-scale analysis"),
    use_gpu: bool = Query(True, description="Use GPU acceleration"),
    gpu_decay_type: str = Query("exponential", description="GPU kernel decay type"),
    gpu_normalization: str = Query("l1", description="GPU kernel normalization"),
    gpu_time_step_ns: int = Query(1000000, description="GPU time step in nanoseconds"),
    gpu_max_kernel_time_ns: int = Query(10000000000, description="GPU max kernel time in nanoseconds"),
):
    """
    Get holographic reconstruction data for 3D visualization.

    Returns structured data optimized for Three.js rendering:
    - bulk_nodes: 3D positioned service components with health metrics
    - bulk_edges: Causal dependencies between components
    - boundary_layers: Per-component observability layer data
    - ambiguity_regions: Uncertainty regions in the reconstruction
    - counterfactual: Optional counterfactual simulation results
    - anomalies: Detected anomalies in the system
    """
    try:
        # Try to get real incident data
        reconstruction, timeline, topology = await _get_incident_data(incident_id)

        # Create request object for config generation
        from pydantic import BaseModel
        class _TempRequest(BaseModel):
            enable_counterfactual: bool
            enable_anomalies: bool
            enable_multiscale: bool
            use_gpu: bool
            gpu_decay_type: str
            gpu_normalization: str
            gpu_time_step_ns: int
            gpu_max_kernel_time_ns: int

        temp_request = _TempRequest(
            enable_counterfactual=enable_counterfactual,
            enable_anomalies=enable_anomalies,
            enable_multiscale=enable_multiscale,
            use_gpu=use_gpu,
            gpu_decay_type=gpu_decay_type,
            gpu_normalization=gpu_normalization,
            gpu_time_step_ns=gpu_time_step_ns,
            gpu_max_kernel_time_ns=gpu_max_kernel_time_ns,
        )
        config = _create_holographic_config(temp_request)

        if reconstruction is None:
            # Fallback to synthetic data for demo
            return await _generate_synthetic_visualization_with_config(incident_id, config)

        # Run holographic analysis
        result = analyze_incident_holographically(
            incident_id=incident_id,
            timeline=timeline,
            topology=topology,
            config=config,
        )

        # Build kernels for counterfactual - use the same kernel builder from analysis
        counterfactual_result = None
        if enable_counterfactual:
            from cauveris.holographic.gpu_kernels import create_gpu_kernel_builder, is_gpu_available
            if use_gpu and is_gpu_available():
                kernel_builder = create_gpu_kernel_builder(topology, config.gpu_config)
            else:
                kernel_builder = CausalKernelBuilder(topology)
            kernel_builder.build_all_kernels()

            holographer = CounterfactualHolographer(topology, kernel_builder)

            # Default intervention if none specified
            intervention = Intervention(
                intervention_type=InterventionType.CPU_SCALING,
                target_component=list(topology.components.keys())[0] if topology.components else "svc_0",
                parameters={"scale_factor": 2.0},
            )

            counterfactual_result = holographer.simulate(
                result.reconstruction,
                intervention,
                result.time_window_ns,
            )

        # Detect anomalies
        anomalies = None
        if enable_anomalies:
            detector = create_anomaly_detector(topology)
            anomalies = detector.detect(result.reconstruction)

        # Generate visualization data
        viz_data = generate_visualization_data(
            topology=topology,
            reconstruction=result.reconstruction,
            counterfactual=counterfactual_result,
            anomalies=anomalies,
            scale_results=result.scale_results if enable_multiscale else None,
            incident_id=incident_id,
            timestamp_ns=result.reconstruction.reconstruction_timestamp_ns,
        )

        viz_dict = _convert_numpy_types(viz_data.__dict__)
        return VisualizationResponse(**viz_dict)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reconstruction failed: {str(e)}")


@router.post("/reconstruction")
async def create_holographic_reconstruction(request: VisualizationRequest):
    """Create holographic reconstruction with custom parameters."""
    return await get_holographic_reconstruction(
        incident_id=request.incident_id,
        enable_counterfactual=request.enable_counterfactual,
        enable_anomalies=request.enable_anomalies,
        enable_multiscale=request.enable_multiscale,
        use_gpu=request.use_gpu,
        gpu_decay_type=request.gpu_decay_type,
        gpu_normalization=request.gpu_normalization,
        gpu_time_step_ns=request.gpu_time_step_ns,
        gpu_max_kernel_time_ns=request.gpu_max_kernel_time_ns,
    )


@router.get("/counterfactual")
async def simulate_counterfactual(
    incident_id: str = Query(..., description="Incident ID"),
    intervention_type: str = Query("CPU_SCALING", description="Intervention type"),
    target_component: str = Query(..., description="Component to intervene on"),
    scale_factor: float = Query(2.0, description="Scaling factor for CPU/Memory"),
    use_gpu: bool = Query(True, description="Use GPU acceleration"),
    gpu_decay_type: str = Query("exponential", description="GPU kernel decay type"),
    gpu_normalization: str = Query("l1", description="GPU kernel normalization"),
    gpu_time_step_ns: int = Query(1000000, description="GPU time step in nanoseconds"),
    gpu_max_kernel_time_ns: int = Query(10000000000, description="GPU max kernel time in nanoseconds"),
):
    """
    Run counterfactual simulation for an incident.

    Simulates "what-if" scenarios by modifying component parameters.
    """
    try:
        from cauveris.holographic.gpu_kernels import GPUConfig, DecayType as GPuDecayType, NormalizationType as GpuNormalizationType
        from cauveris.holographic.integration import HolographicConfig
        from cauveris.holographic.gpu_kernels import create_gpu_kernel_builder, is_gpu_available

        reconstruction, timeline, topology = await _get_incident_data(incident_id)

        if reconstruction is None:
            generator = SyntheticIncidentGenerator(seed=42)
            incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)
            topology = incident.topology
            timeline = incident.timeline

        # Create config with GPU settings
        gpu_config = GPUConfig(
            time_step_ns=gpu_time_step_ns,
            max_kernel_time_ns=gpu_max_kernel_time_ns,
            decay_type=GPuDecayType[gpu_decay_type.upper()],
            normalization=GpuNormalizationType[gpu_normalization.upper()],
            use_gpu=use_gpu,
        )
        config = HolographicConfig(
            enable_multiscale=False,
            enable_compression=False,
            use_gpu=use_gpu,
            gpu_config=gpu_config,
        )
        result = analyze_incident_holographically(
            incident_id=incident_id,
            timeline=timeline,
            topology=topology,
            config=config,
        )
        reconstruction = result.reconstruction

        # Build kernels with GPU if configured
        if use_gpu and is_gpu_available():
            kernel_builder = create_gpu_kernel_builder(topology, gpu_config)
        else:
            kernel_builder = CausalKernelBuilder(topology)
        kernel_builder.build_all_kernels()

        # Create intervention
        intervention_type_enum = InterventionType[intervention_type]
        intervention = Intervention(
            intervention_type=intervention_type_enum,
            target_component=target_component,
            parameters={"scale_factor": scale_factor},
        )

        holographer = CounterfactualHolographer(topology, kernel_builder)
        cf_result = holographer.simulate(reconstruction, intervention, result.time_window_ns)

        # Generate counterfactual visualization
        from cauveris.holographic.visualization import VisualizationDataGenerator

        viz_generator = VisualizationDataGenerator(topology, incident_id)
        cf_viz = viz_generator._generate_counterfactual(cf_result)

        return {
            "intervention": cf_viz["intervention"],
            "intervention_type": cf_viz["intervention_type"],
            "fidelity_improvement": cf_viz["fidelity_improvement"],
            "cost_estimate": cf_viz["cost_estimate"],
            "risk_score": cf_viz["risk_score"],
            "changes": cf_viz["changes"],
            "predicted_boundary": cf_viz["predicted_boundary"],
        }

    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid intervention type: {intervention_type}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Counterfactual simulation failed: {str(e)}")


@router.get("/anomalies")
async def get_anomalies(
    incident_id: str = Query(..., description="Incident ID"),
    use_gpu: bool = Query(True, description="Use GPU acceleration"),
    gpu_decay_type: str = Query("exponential", description="GPU kernel decay type"),
    gpu_normalization: str = Query("l1", description="GPU kernel normalization"),
    gpu_time_step_ns: int = Query(1000000, description="GPU time step in nanoseconds"),
    gpu_max_kernel_time_ns: int = Query(10000000000, description="GPU max kernel time in nanoseconds"),
):
    """Get detected anomalies for an incident."""
    try:
        from cauveris.holographic.gpu_kernels import GPUConfig, DecayType as GPuDecayType, NormalizationType as GpuNormalizationType
        from cauveris.holographic.integration import HolographicConfig

        reconstruction, timeline, topology = await _get_incident_data(incident_id)

        if reconstruction is None:
            generator = SyntheticIncidentGenerator(seed=42)
            incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)
            topology = incident.topology
            timeline = incident.timeline

        # Create config with GPU settings
        gpu_config = GPUConfig(
            time_step_ns=gpu_time_step_ns,
            max_kernel_time_ns=gpu_max_kernel_time_ns,
            decay_type=GPuDecayType[gpu_decay_type.upper()],
            normalization=GpuNormalizationType[gpu_normalization.upper()],
            use_gpu=use_gpu,
        )
        config = HolographicConfig(
            enable_multiscale=False,
            enable_compression=False,
            use_gpu=use_gpu,
            gpu_config=gpu_config,
        )
        result = analyze_incident_holographically(
            incident_id=incident_id,
            timeline=timeline,
            topology=topology,
            config=config,
        )
        reconstruction = result.reconstruction

        detector = create_anomaly_detector(topology)
        anomaly_report = detector.detect(reconstruction)
        anomalies_viz = [a.to_dict() for a in anomaly_report.anomalies]

        return {"anomalies": anomalies_viz}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anomaly detection failed: {str(e)}")


@router.get("/boundary-layers/{incident_id}")
async def get_boundary_layers(
    incident_id: str,
    use_gpu: bool = Query(True, description="Use GPU acceleration"),
    gpu_decay_type: str = Query("exponential", description="GPU kernel decay type"),
    gpu_normalization: str = Query("l1", description="GPU kernel normalization"),
    gpu_time_step_ns: int = Query(1000000, description="GPU time step in nanoseconds"),
    gpu_max_kernel_time_ns: int = Query(10000000000, description="GPU max kernel time in nanoseconds"),
):
    """Get boundary layer heatmap data for an incident."""
    try:
        from cauveris.holographic.gpu_kernels import GPUConfig, DecayType as GPuDecayType, NormalizationType as GpuNormalizationType
        from cauveris.holographic.integration import HolographicConfig

        reconstruction, timeline, topology = await _get_incident_data(incident_id)

        if reconstruction is None:
            generator = SyntheticIncidentGenerator(seed=42)
            incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)
            topology = incident.topology
            timeline = incident.timeline

        # Create config with GPU settings
        gpu_config = GPUConfig(
            time_step_ns=gpu_time_step_ns,
            max_kernel_time_ns=gpu_max_kernel_time_ns,
            decay_type=GPuDecayType[gpu_decay_type.upper()],
            normalization=GpuNormalizationType[gpu_normalization.upper()],
            use_gpu=use_gpu,
        )
        config = HolographicConfig(
            enable_multiscale=False,
            enable_compression=False,
            use_gpu=use_gpu,
            gpu_config=gpu_config,
        )
        result = analyze_incident_holographically(
            incident_id=incident_id,
            timeline=timeline,
            topology=topology,
            config=config,
        )
        reconstruction = result.reconstruction

        from cauveris.holographic.visualization import VisualizationDataGenerator
        viz_generator = VisualizationDataGenerator(topology, incident_id)
        boundary_layers = viz_generator._generate_boundary_layers(reconstruction)

        return {"boundary_layers": boundary_layers}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Boundary layer generation failed: {str(e)}")


async def _get_incident_data(incident_id: str):
    """Try to load real incident data from storage."""
    # TODO: Implement actual data loading from database/file storage
    # For now, return None to trigger synthetic data generation
    return None, None, None


async def _generate_synthetic_visualization(
    incident_id: str,
    enable_counterfactual: bool,
    enable_anomalies: bool,
    enable_multiscale: bool,
):
    """Generate synthetic visualization data for demo purposes (legacy)."""
    return await _generate_synthetic_visualization_with_config(
        incident_id,
        HolographicConfig(
            enable_multiscale=enable_multiscale,
            enable_compression=False,
        )
    )


async def _generate_synthetic_visualization_with_config(
    incident_id: str,
    config: HolographicConfig,
):
    """Generate synthetic visualization data for demo purposes with config."""
    from cauveris.holographic.gpu_kernels import create_gpu_kernel_builder, is_gpu_available
    from cauveris.holographic.counterfactual import CounterfactualHolographer, CausalKernelBuilder, Intervention, InterventionType
    from cauveris.holographic.anomaly import create_anomaly_detector
    from cauveris.holographic.synthetic import SyntheticIncidentGenerator, IncidentType

    generator = SyntheticIncidentGenerator(seed=42)
    incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)

    result = analyze_incident_holographically(
        incident_id=incident_id,
        timeline=incident.timeline,
        topology=incident.topology,
        config=config,
    )

    counterfactual_result = None
    if config.enable_synthesis:
        if config.use_gpu and is_gpu_available():
            kernel_builder = create_gpu_kernel_builder(incident.topology, config.gpu_config)
        else:
            kernel_builder = CausalKernelBuilder(incident.topology)
        kernel_builder.build_all_kernels()

        holographer = CounterfactualHolographer(incident.topology, kernel_builder)
        intervention = Intervention(
            intervention_type=InterventionType.CPU_SCALING,
            target_component="svc_0",
            parameters={"scale_factor": 2.0},
        )
        counterfactual_result = holographer.simulate(
            result.reconstruction,
            intervention,
            result.time_window_ns,
        )

    anomalies = None
    if config.enable_anomaly_detection:
        detector = create_anomaly_detector(incident.topology)
        anomalies = detector.detect(result.reconstruction)

    from cauveris.holographic.visualization import generate_visualization_data

    viz_data = generate_visualization_data(
        topology=incident.topology,
        reconstruction=result.reconstruction,
        counterfactual=counterfactual_result,
        anomalies=anomalies,
        scale_results=result.scale_results if config.enable_multiscale else None,
        incident_id=incident_id,
        timestamp_ns=result.reconstruction.reconstruction_timestamp_ns,
    )

    from cauveris.api.holographic import VisualizationResponse
    viz_dict = _convert_numpy_types(viz_data.__dict__)
    return VisualizationResponse(**viz_dict)

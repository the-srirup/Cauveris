"""
Holographic Reconstruction API endpoints.

Provides REST API for serving holographic visualization data to the frontend.
"""

from __future__ import annotations

import json
import asyncio
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from typing import Optional, Dict, Any, List, Tuple, Set
from pydantic import BaseModel
import numpy as np

from cauveris.holographic.visualization import (
    generate_visualization_data,
    build_provenance,
    summarize_boundary_coverage,
    scoped_boundary_layer_gaps,
)
from cauveris.holographic.integration import analyze_incident_holographically, HolographicConfig
from cauveris.holographic.gpu_kernels import (
    GPUConfig,
    DecayType as GPUDecayType,
    NormalizationType as GPUNormalizationType,
)
from cauveris.holographic.counterfactual import (
    CounterfactualHolographer,
    CausalKernelBuilder,
    Intervention,
    InterventionType,
)
from cauveris.holographic.anomaly import create_anomaly_detector
from cauveris.holographic.synthetic import SyntheticIncidentGenerator, IncidentType
from cauveris.holographic.topology import SystemTopology, build_topology_from_timeline
from cauveris.holographic.calibration import CalibrationProfile
from cauveris.attribution import canonical_component, load_component_aliases
from cauveris.ingestion.controller import IngestionController
from cauveris.timeline.builder import TimelineBuilder
from cauveris.schemas.incident import Incident

router = APIRouter(prefix="/holographic", tags=["holographic"])

logger = logging.getLogger(__name__)


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
        decay_type=GPUDecayType[request.gpu_decay_type.upper()],
        normalization=GPUNormalizationType[request.gpu_normalization.upper()],
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
    gpu_max_kernel_time_ns: int = Query(
        10000000000, description="GPU max kernel time in nanoseconds"
    ),
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
        timeline, temporal_analysis, topology, bundle, calibration, aliases = (
            await _get_incident_data(incident_id)
        )

        # Create request object for config generation
        from pydantic import BaseModel

        def _val(x, default=None):
            if hasattr(x, "default"):
                return x.default
            return x if x is not None else default

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
            enable_counterfactual=_val(enable_counterfactual, False),
            enable_anomalies=_val(enable_anomalies, True),
            enable_multiscale=_val(enable_multiscale, True),
            use_gpu=_val(use_gpu, True),
            gpu_decay_type=_val(gpu_decay_type, "exponential"),
            gpu_normalization=_val(gpu_normalization, "l1"),
            gpu_time_step_ns=_val(gpu_time_step_ns, 1000000),
            gpu_max_kernel_time_ns=_val(gpu_max_kernel_time_ns, 10000000000),
        )
        config = _create_holographic_config(temp_request)

        if timeline is None or topology is None:
            # No bundle on disk. Synthesize a scenario so the view still
            # renders, but label it as synthetic in the payload — the caller
            # must not present a fabricated reconstruction as the real one.
            return await _generate_synthetic_visualization_with_config(
                incident_id,
                config,
                provenance=_synthetic_provenance(
                    bundle, incident_type=IncidentType.CPU_SPIKE_CASCADE.name
                ),
            )

        # Run holographic analysis
        result = analyze_incident_holographically(
            incident_id=incident_id,
            timeline=timeline,
            topology=topology,
            config=config,
            temporal_analysis=temporal_analysis,
            calibration=calibration,
            aliases=aliases,
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
                target_component=list(topology.components.keys())[0]
                if topology.components
                else "svc_0",
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
            provenance=_bundle_provenance(
                bundle, timeline=timeline, reconstruction=result.reconstruction
            ),
        )

        viz_dict = _convert_numpy_types(viz_data.__dict__)
        return VisualizationResponse(**viz_dict)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reconstruction failed: {str(e)}")


@router.get("/timeline")
async def get_holographic_timeline(
    incident_id: str = Query(..., description="Incident ID to reconstruct over time"),
    frames: int = Query(
        6, ge=1, le=24, description="Number of evidence slices to reconstruct"
    ),
    use_gpu: bool = Query(True, description="Use GPU acceleration for the kernels"),
):
    """
    Reconstruct the incident repeatedly, once per slice of its own evidence.

    Each frame is a genuine holographic inversion over the telemetry that had
    actually arrived by that point in the incident — not a re-colouring of one
    reconstruction, and not an interpolation between two drawings. A slice with
    thin evidence therefore reconstructs *worse*, and says so, which is the
    honest shape of the data.

    The slices are cut by event count rather than by wall-clock, so every
    frame is backed by at least one real event whenever the incident has
    enough events to go around.
    """
    try:
        timeline, temporal_analysis, topology, bundle, calibration, aliases = (
            await _get_incident_data(incident_id)
        )

        synthetic = timeline is None or topology is None
        if synthetic:
            # No bundle: fall back to the same fixed synthetic scenario the
            # reconstruction endpoint uses, and label the frames as such.
            generator = SyntheticIncidentGenerator(seed=42)
            incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)
            topology = incident.topology
            timeline = incident.timeline
            temporal_analysis = {}
            provenance = _synthetic_provenance(
                bundle, incident_type=IncidentType.CPU_SPIKE_CASCADE.name
            )
        else:
            provenance = _bundle_provenance(bundle, timeline=timeline)

        ordered = sorted(
            timeline,
            key=lambda e: e.get("timestamp_ns", 0) if isinstance(e, dict) else 0,
        )
        slice_count = max(1, min(frames, len(ordered)))
        groups = _balanced_slices(ordered, slice_count)

        frame_payloads: List[Dict[str, Any]] = []
        for index, group in enumerate(groups):
            frame_payloads.append(
                _reconstruct_slice(
                    incident_id=incident_id,
                    topology=topology,
                    events=group,
                    temporal_analysis=temporal_analysis or {},
                    index=index,
                    use_gpu=use_gpu,
                    calibration=calibration,
                    aliases=aliases,
                )
            )

        return {
            "incident_id": incident_id,
            "frames": frame_payloads,
            "frame_count": len(frame_payloads),
            "event_count": len(ordered),
            "slices_requested": slice_count,
            "provenance": provenance,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Timeline reconstruction failed: {str(e)}")


def _balanced_slices(events: List[Dict[str, Any]], count: int) -> List[List[Dict[str, Any]]]:
    """Cut an ordered event list into ``count`` contiguous, non-empty groups.

    The groups are balanced by event count rather than by elapsed time: a
    window that contains no evidence cannot be reconstructed, so a time-based
    cut would produce empty frames and hide the incident's actual sparsity.
    """
    if not events:
        return []
    count = max(1, min(count, len(events)))
    base, extra = divmod(len(events), count)
    slices: List[List[Dict[str, Any]]] = []
    cursor = 0
    for index in range(count):
        size = base + (1 if index < extra else 0)
        slices.append(events[cursor : cursor + size])
        cursor += size
    return slices


def _reconstruct_slice(
    *,
    incident_id: str,
    topology: SystemTopology,
    events: List[Dict[str, Any]],
    temporal_analysis: Dict[str, Any],
    index: int,
    use_gpu: bool,
    calibration: Optional[CalibrationProfile] = None,
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run one holographic inversion over a slice of the incident's evidence."""
    timestamps = [
        e.get("timestamp_ns", 0) for e in events if isinstance(e, dict)
    ]
    window = (min(timestamps), max(timestamps)) if timestamps else (0, 0)

    frame: Dict[str, Any] = {
        "stage_id": f"T{index}",
        "index": index,
        "timestamp_ns": window[0],
        "window_ns": [window[0], window[1]],
        "event_count": len(events),
        "nodes": [],
        "links": [],
        "fidelity": 0.0,
        "boundary_residual": 0.0,
        "status": "ok",
        "error": None,
    }

    if not events:
        frame["status"] = "empty"
        frame["error"] = "This slice of the incident window contains no evidence."
        return frame

    config = HolographicConfig(
        enable_multiscale=False,
        enable_compression=False,
        enable_synthesis=False,
        enable_anomaly_detection=False,
        use_gpu=use_gpu,
    )

    try:
        result = analyze_incident_holographically(
            incident_id=incident_id,
            timeline=events,
            topology=topology,
            config=config,
            temporal_analysis=temporal_analysis,
            calibration=calibration,
            aliases=aliases,
        )
        viz = generate_visualization_data(
            topology=topology,
            reconstruction=result.reconstruction,
            incident_id=incident_id,
            timestamp_ns=result.reconstruction.reconstruction_timestamp_ns,
        )
        frame["nodes"] = viz.bulk_nodes
        frame["links"] = viz.bulk_edges
        frame["fidelity"] = result.reconstruction.overall_fidelity
        frame["boundary_residual"] = result.reconstruction.boundary_residual
    except Exception as exc:  # pragma: no cover - defensive: one bad slice must not lose the rest
        frame["status"] = "failed"
        frame["error"] = f"Reconstruction failed for this slice: {exc}"

    return _convert_numpy_types(frame)


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
    gpu_max_kernel_time_ns: int = Query(
        10000000000, description="GPU max kernel time in nanoseconds"
    ),
):
    """
    Run counterfactual simulation for an incident.

    Simulates "what-if" scenarios by modifying component parameters.
    """
    try:
        from cauveris.holographic.gpu_kernels import (
            GPUConfig,
            DecayType as GPUDecayType,
            NormalizationType as GPUNormalizationType,
        )
        from cauveris.holographic.integration import HolographicConfig
        from cauveris.holographic.gpu_kernels import create_gpu_kernel_builder, is_gpu_available

        timeline, temporal_analysis, topology, bundle, calibration, aliases = (
            await _get_incident_data(incident_id)
        )

        if timeline is None or topology is None:
            generator = SyntheticIncidentGenerator(seed=42)
            incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)
            topology = incident.topology
            timeline = incident.timeline
        else:
            temporal_analysis = temporal_analysis or {}

        # Create config with GPU settings
        gpu_config = GPUConfig(
            time_step_ns=gpu_time_step_ns,
            max_kernel_time_ns=gpu_max_kernel_time_ns,
            decay_type=GPUDecayType[gpu_decay_type.upper()],
            normalization=GPUNormalizationType[gpu_normalization.upper()],
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
            temporal_analysis=temporal_analysis,
            calibration=calibration,
            aliases=aliases,
        )
        reconstruction = result.reconstruction

        # A counterfactual is only meaningful against real evidence: the
        # response carries the same provenance record so the caller can see
        # that a "what-if" here was computed on a fabricated system.
        provenance = (
            _bundle_provenance(bundle, timeline=timeline, reconstruction=reconstruction)
            if bundle.get("found")
            else _synthetic_provenance(
                bundle, incident_type=IncidentType.CPU_SPIKE_CASCADE.name
            )
        )

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
            "provenance": provenance,
        }

    except KeyError:
        raise HTTPException(
            status_code=400, detail=f"Invalid intervention type: {intervention_type}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Counterfactual simulation failed: {str(e)}")


@router.get("/anomalies")
async def get_anomalies(
    incident_id: str = Query(..., description="Incident ID"),
    use_gpu: bool = Query(True, description="Use GPU acceleration"),
    gpu_decay_type: str = Query("exponential", description="GPU kernel decay type"),
    gpu_normalization: str = Query("l1", description="GPU kernel normalization"),
    gpu_time_step_ns: int = Query(1000000, description="GPU time step in nanoseconds"),
    gpu_max_kernel_time_ns: int = Query(
        10000000000, description="GPU max kernel time in nanoseconds"
    ),
):
    """Get detected anomalies for an incident."""
    try:
        from cauveris.holographic.gpu_kernels import (
            GPUConfig,
            DecayType as GPUDecayType,
            NormalizationType as GPUNormalizationType,
        )
        from cauveris.holographic.integration import HolographicConfig

        timeline, temporal_analysis, topology, bundle, calibration, aliases = (
            await _get_incident_data(incident_id)
        )

        if timeline is None or topology is None:
            generator = SyntheticIncidentGenerator(seed=42)
            incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)
            topology = incident.topology
            timeline = incident.timeline
            temporal_analysis = {}

        # Create config with GPU settings
        gpu_config = GPUConfig(
            time_step_ns=gpu_time_step_ns,
            max_kernel_time_ns=gpu_max_kernel_time_ns,
            decay_type=GPUDecayType[gpu_decay_type.upper()],
            normalization=GPUNormalizationType[gpu_normalization.upper()],
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
            temporal_analysis=temporal_analysis,
            calibration=calibration,
            aliases=aliases,
        )
        reconstruction = result.reconstruction

        detector = create_anomaly_detector(topology)
        anomaly_report = detector.detect(reconstruction)
        anomalies_viz = [a.to_dict() for a in anomaly_report.anomalies]

        # Anomaly dicts carry numpy types (e.g. timestamp_ns is a numpy.int64
        # inherited from the reconstruction) — FastAPI's encoder cannot
        # serialize those, so every other route wraps with _convert_numpy_types;
        # this route must too.
        return _convert_numpy_types(
            {
                "anomalies": anomalies_viz,
                "provenance": (
                    _bundle_provenance(
                        bundle, timeline=timeline, reconstruction=reconstruction
                    )
                    if bundle.get("found")
                    else _synthetic_provenance(
                        bundle, incident_type=IncidentType.CPU_SPIKE_CASCADE.name
                    )
                ),
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anomaly detection failed: {str(e)}")


@router.get("/boundary-layers/{incident_id}")
async def get_boundary_layers(
    incident_id: str,
    use_gpu: bool = Query(True, description="Use GPU acceleration"),
    gpu_decay_type: str = Query("exponential", description="GPU kernel decay type"),
    gpu_normalization: str = Query("l1", description="GPU kernel normalization"),
    gpu_time_step_ns: int = Query(1000000, description="GPU time step in nanoseconds"),
    gpu_max_kernel_time_ns: int = Query(
        10000000000, description="GPU max kernel time in nanoseconds"
    ),
):
    """Get boundary layer heatmap data for an incident."""
    try:
        from cauveris.holographic.gpu_kernels import (
            GPUConfig,
            DecayType as GPUDecayType,
            NormalizationType as GPUNormalizationType,
        )
        from cauveris.holographic.integration import HolographicConfig

        timeline, temporal_analysis, topology, bundle, calibration, aliases = (
            await _get_incident_data(incident_id)
        )

        if timeline is None or topology is None:
            generator = SyntheticIncidentGenerator(seed=42)
            incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)
            topology = incident.topology
            timeline = incident.timeline
            temporal_analysis = {}

        # Create config with GPU settings
        gpu_config = GPUConfig(
            time_step_ns=gpu_time_step_ns,
            max_kernel_time_ns=gpu_max_kernel_time_ns,
            decay_type=GPUDecayType[gpu_decay_type.upper()],
            normalization=GPUNormalizationType[gpu_normalization.upper()],
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
            temporal_analysis=temporal_analysis,
            calibration=calibration,
            aliases=aliases,
        )
        reconstruction = result.reconstruction

        from cauveris.holographic.visualization import VisualizationDataGenerator

        viz_generator = VisualizationDataGenerator(topology, incident_id)
        boundary_layers = viz_generator._generate_boundary_layers(reconstruction)

        return {
            "boundary_layers": boundary_layers,
            "provenance": (
                _bundle_provenance(bundle, timeline=timeline, reconstruction=reconstruction)
                if bundle.get("found")
                else _synthetic_provenance(
                    bundle, incident_type=IncidentType.CPU_SPIKE_CASCADE.name
                )
            ),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Boundary layer generation failed: {str(e)}")


# Directories probed for an incident bundle, in priority order. Named because
# the search paths are reported back to the client when nothing is found — the
# message and the search itself must not drift apart.
_BUNDLE_SEARCH_TEMPLATES = (
    str(Path("evidence_store") / "{incident_id}"),
    "./incident-{incident_id}",
    "./{incident_id}",
    "./golden_incident/incident-{incident_id}",
    "./golden_incident/{incident_id}",
)


def _bundle_search_paths(incident_id: str) -> List[str]:
    return [t.format(incident_id=incident_id) for t in _BUNDLE_SEARCH_TEMPLATES]


def _missing_bundle(incident_id: str) -> Dict[str, Any]:
    """The evidence record for an incident whose bundle could not be resolved."""
    return {"found": False, "path": None, "search_paths": _bundle_search_paths(incident_id)}


def _bundle_provenance(
    bundle: Dict[str, Any],
    *,
    timeline: Optional[List[Dict[str, Any]]],
    reconstruction: Optional[Any] = None,
) -> Dict[str, Any]:
    """Provenance for a reconstruction built from a real bundle.

    Boundary-layer coverage is read off the reconstruction itself (which
    layers actually reached the inversion), so it reflects what was observed
    rather than what the bundle declared.

    The two layer gaps are reported separately and must not be merged. The
    scoped list — layers a component's topology declares but the bundle
    delivered nothing for — is a real deficiency. The undeclared list is the
    complement of the modelled enum, which for any system that does not
    instrument all seven dimensions is simply the shape of its telemetry
    surface, not a defect in the bundle.
    """
    observed: List[str] = []
    undeclared: List[str] = []
    missing: List[str] = []
    if reconstruction is not None:
        observed, undeclared = summarize_boundary_coverage(reconstruction)
        missing = scoped_boundary_layer_gaps(reconstruction)

    return build_provenance(
        bundle_found=bool(bundle.get("found")),
        bundle_path=bundle.get("path"),
        bundle_search_paths=bundle.get("search_paths") or [],
        timeline_event_count=len(timeline or []),
        observed_boundary_layers=observed,
        missing_boundary_layers=missing,
        undeclared_boundary_layers=undeclared,
    )


def _synthetic_provenance(
    bundle: Dict[str, Any],
    *,
    incident_type: str,
    seed: int = 42,
    timeline: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Provenance for a reconstruction synthesized because no bundle existed.

    Records the synthetic scenario's identity as well, so a reviewer can tell
    *which* fabricated incident they are looking at instead of having to
    recognise the shape of the graph.
    """
    return build_provenance(
        bundle_found=False,
        bundle_path=bundle.get("path"),
        bundle_search_paths=bundle.get("search_paths") or [],
        timeline_event_count=len(timeline or []),
        synthetic_seed=seed,
        synthetic_incident_type=incident_type,
    )


async def _get_incident_data(
    incident_id: str,
) -> Tuple[
    Optional[List[Dict[str, Any]]],
    Optional[Dict[str, Any]],
    Optional[SystemTopology],
    Dict[str, Any],
    Optional[CalibrationProfile],
    Optional[Dict[str, str]],
]:
    """
    Load real incident data from storage using the ingestion pipeline.

    Returns:
        Tuple of (timeline_events, temporal_analysis, topology, bundle,
        calibration, aliases).

        ``bundle`` records where the evidence came from:
        ``{"found": bool, "path": str | None, "search_paths": [str]}``. It is
        returned on the failure path too — a caller that has to tell the user
        "your incident could not be found" also needs to say *where* we looked.

        ``calibration`` holds the scales the incident's own declarations put
        its measurements on, and ``aliases`` the names the bundle says are the
        same component.  Both are ``None`` when there is no bundle to read
        them from.
    """
    import logging

    logger = logging.getLogger(__name__)
    missing = _missing_bundle(incident_id)
    try:
        # Try to load incident from evidence store
        controller = IngestionController()

        # Look for incident bundle in standard locations
        evidence_store = None
        for template in _BUNDLE_SEARCH_TEMPLATES:
            cand = Path(template.format(incident_id=incident_id))
            if cand.exists() and cand.is_dir():
                evidence_store = cand
                break

        if evidence_store is None:
            logger.warning(
                f"Incident bundle not found for {incident_id} in "
                f"{missing['search_paths']}, falling back to synthetic data"
            )
            return None, None, None, missing, None, None

        bundle = {
            "found": True,
            "path": str(evidence_store),
            "search_paths": missing["search_paths"],
        }

        # Create a minimal incident object to load the bundle
        incident = Incident(
            id=incident_id,
            title=incident_id,
            description="Loaded from storage",
            system_name="unknown",
            bundle_path=str(evidence_store),
        )

        # Process the incident bundle
        incident = await controller.process(incident)

        # Build the timeline with the real builder: it parses every evidence
        # channel the bundle ships — traces, logs, metric exports, deployment
        # records, operator notes, ROS recordings — and attributes each
        # observation to the component it describes.
        incident = await TimelineBuilder().build(incident)
        timeline_events = incident.timeline_events

        # If the builder found nothing (a bundle laid out in a way it does not
        # know), fall back to the flat evidence scan.  It sees fewer channels,
        # so the reconstruction it produces is the weaker of the two.
        if not timeline_events:
            timeline_events = _extract_timeline_from_evidence(incident, evidence_store)

        # The scales the incident's own declarations put its measurements on,
        # and the names it says are the same component.
        calibration = CalibrationProfile.from_bundle(evidence_store)
        if timeline_events:
            calibration.learn_from_events(timeline_events)
        aliases = load_component_aliases(evidence_store)

        # Temporal analysis over the same timeline (clock skew, causality).
        temporal_analysis = await _analyze_temporally(incident, evidence_store)

        # Build topology from timeline if not in manifest
        topology = None
        if incident.manifest and "topology" in incident.manifest:
            topology = _build_topology_from_manifest(incident.manifest["topology"], aliases)
        elif timeline_events:
            # Infer topology from timeline using the same resolver the evidence
            # units use, so the graph and the measurements describe the same
            # components.
            topology = build_topology_from_timeline(timeline_events, evidence_store, aliases)

        logger.info(
            f"Loaded real incident {incident_id} from {evidence_store}: "
            f"{len(timeline_events)} timeline events, topology: {topology is not None}"
        )
        return timeline_events, temporal_analysis, topology, bundle, calibration, aliases

    except Exception as e:
        logger.error(f"Failed to load incident {incident_id}: {e}")
        return None, None, None, missing, None, None


async def _analyze_temporally(
    incident: Incident, bundle_path: Path
) -> Dict[str, Any]:
    """Run the temporal analyzer over the incident's own timeline.

    The analyzer is real work — clock-skew estimation, causality checks,
    freshness budgets — but it is not on the critical path of a
    reconstruction: when it cannot run, the reconstruction proceeds without
    the cross-reference instead of failing.
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        from cauveris.temporal.integration import TemporalAnalyzer

        return TemporalAnalyzer().analyze_incident(incident, bundle_path) or {}
    except Exception as exc:
        logger.warning(f"Temporal analysis unavailable for {incident.id}: {exc}")
        return {}


def _extract_timeline_from_evidence(incident: Incident, bundle_path: Path) -> List[Dict[str, Any]]:
    """Extract timeline events from evidence files in the bundle."""
    timeline = []
    for evidence in incident.evidence_items:
        file_path = bundle_path / evidence.file_path
        if not file_path.exists():
            continue

        # Parse based on file type and content
        if evidence.file_type in ["application/json", "application/x-jsonlines"] or (
            evidence.file_type == "text/plain"
            and file_path.suffix == ".log"
            and _is_jsonl_file(file_path)
        ):
            timeline.extend(_parse_jsonl_logs(file_path))
        elif evidence.file_type == "text/plain" and file_path.suffix == ".log":
            timeline.extend(_parse_plain_logs(file_path))
        elif evidence.file_type == "application/json" and "trace" in evidence.file_path.lower():
            timeline.extend(_parse_traces(file_path))
        elif evidence.file_type == "text/csv" and "metric" in evidence.file_path.lower():
            timeline.extend(_parse_metrics_csv(file_path))

    return timeline


def _is_jsonl_file(file_path: Path) -> bool:
    """Check if a file contains JSONL format by reading first non-empty line."""
    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    # Try to parse as JSON
                    import json

                    json.loads(line)
                    return True
    except Exception:
        pass
    return False


def _parse_jsonl_logs(file_path: Path) -> List[Dict[str, Any]]:
    """Parse JSONL log files into timeline events."""
    import logging

    logger = logging.getLogger(__name__)
    events = []
    try:
        with open(file_path, "r") as f:
            for line_num, line in enumerate(f):
                if not line.strip():
                    continue
                try:
                    log_entry = json.loads(line)

                    # Parse timestamp - handle both ISO strings and Unix timestamps
                    ts_raw = log_entry.get("timestamp", log_entry.get("@timestamp", 0))
                    if isinstance(ts_raw, str):
                        # Try ISO format
                        timestamp_ns = _parse_iso_timestamp(ts_raw)
                    elif isinstance(ts_raw, (int, float)):
                        # Unix timestamp (seconds or milliseconds)
                        if ts_raw < 1e12:
                            timestamp_ns = int(ts_raw * 1_000_000_000)
                        else:
                            timestamp_ns = int(ts_raw * 1_000_000) if ts_raw > 1e15 else int(ts_raw)
                    else:
                        timestamp_ns = 0

                    events.append(
                        {
                            "event_id": f"{file_path.name}:{line_num}",
                            "timestamp_ns": timestamp_ns,
                            "source_type": "jsonl_log",
                            "message": log_entry.get("message", log_entry.get("msg", "")),
                            "attributes": {
                                k: v
                                for k, v in log_entry.items()
                                if k not in ["timestamp", "@timestamp", "message", "msg"]
                            },
                            "status": log_entry.get(
                                "level", log_entry.get("severity", "info")
                            ).lower(),
                        }
                    )
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")
    return events


def _parse_plain_logs(file_path: Path) -> List[Dict[str, Any]]:
    """Parse plain text logs into timeline events with robust timestamp extraction."""
    events = []
    try:
        with open(file_path, "r") as f:
            for line_num, line in enumerate(f):
                line = line.rstrip("\n")
                if not line.strip():
                    continue

                # Try multiple timestamp patterns
                timestamp_ns = _extract_timestamp_from_line(line)
                if timestamp_ns is None:
                    # Fallback: use file modification time + line offset
                    timestamp_ns = _fallback_timestamp(file_path, line_num)

                # Extract log level
                level = _extract_log_level(line)

                # Extract service/component name
                service = _extract_service_name(line)

                events.append(
                    {
                        "event_id": f"{file_path.name}:{line_num}",
                        "timestamp_ns": timestamp_ns,
                        "source_type": "plain_log",
                        "message": line.strip()[:500],
                        "attributes": {
                            "raw_line": line.strip(),
                            "service": service,
                            "line_number": line_num,
                        },
                        "status": level,
                    }
                )
    except Exception as e:
        logger.warning(f"Failed to parse {file_path}: {e}")
    return events


def _extract_timestamp_from_line(line: str) -> int | None:
    """Extract timestamp from log line using multiple common formats."""
    import re

    # Pattern 1: ISO 8601 with microseconds: 2024-01-15T10:30:45.123456Z
    iso_pattern = r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
    # Pattern 2: Syslog: Jan 15 10:30:45
    syslog_pattern = r"([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
    # Pattern 3: Unix timestamp: 1705315845.123
    unix_pattern = r"(\d{10}\.\d+|\d{10})"
    # Pattern 4: Log4j: 2024-01-15 10:30:45,123
    log4j_pattern = r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})"

    patterns = [
        (iso_pattern, _parse_iso_timestamp),
        (syslog_pattern, _parse_syslog_timestamp),
        (unix_pattern, _parse_unix_timestamp),
        (log4j_pattern, _parse_log4j_timestamp),
    ]

    for pattern, parser in patterns:
        match = re.search(pattern, line)
        if match:
            try:
                return parser(match.group(1))
            except Exception:
                continue
    return None


def _fallback_timestamp(file_path: Path, line_num: int) -> int:
    """Generate fallback timestamp from file mtime and line number."""
    try:
        mtime = file_path.stat().st_mtime
        return int(mtime * 1_000_000_000) + line_num * 1_000_000
    except Exception:
        return line_num * 1_000_000_000


def _parse_iso_timestamp(ts_str: str) -> int:
    """Parse ISO 8601 timestamp to nanoseconds."""
    from datetime import datetime, timezone

    ts_str = ts_str.replace("Z", "+00:00")
    if "." not in ts_str.split("T")[-1].split("+")[0].split("-")[-1]:
        # No fractional seconds
        dt = datetime.fromisoformat(ts_str)
    else:
        dt = datetime.fromisoformat(ts_str.replace(",", "."))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _parse_syslog_timestamp(ts_str: str) -> int:
    """Parse syslog timestamp (assumes current year)."""
    from datetime import datetime, timezone

    current_year = datetime.now().year
    dt = datetime.strptime(f"{current_year} {ts_str}", "%Y %b %d %H:%M:%S")
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def _parse_unix_timestamp(ts_str: str) -> int:
    """Parse Unix timestamp to nanoseconds."""
    return int(float(ts_str) * 1_000_000_000)


def _parse_log4j_timestamp(ts_str: str) -> int:
    """Parse Log4j timestamp to nanoseconds."""
    from datetime import datetime, timezone

    ts_str = ts_str.replace(",", ".")
    dt = datetime.fromisoformat(ts_str)
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def _extract_log_level(line: str) -> str:
    """Extract log level from line."""
    import re

    # Common patterns: ERROR, WARN, INFO, DEBUG, TRACE, CRITICAL, FATAL
    level_pattern = r"\b(ERROR|WARN|WARNING|INFO|DEBUG|TRACE|CRITICAL|FATAL|ERR|DBG)\b"
    match = re.search(level_pattern, line, re.IGNORECASE)
    if match:
        level = match.group(1).upper()
        if level in ("ERR", "ERROR", "FATAL", "CRITICAL"):
            return "error"
        elif level in ("WARN", "WARNING"):
            return "warn"
        elif level in ("DEBUG", "DBG", "TRACE"):
            return "debug"
        else:
            return "info"
    return "info"


def _extract_service_name(line: str) -> str:
    """Extract service/component name from log line."""
    import re

    # Pattern: [service-name] or service-name: or <service-name>
    patterns = [
        r"\[([a-zA-Z][a-zA-Z0-9_-]*)\]",  # [service-name]
        r"^([a-zA-Z][a-zA-Z0-9_-]*):\s",  # service-name: at start
        r"<([a-zA-Z][a-zA-Z0-9_-]*)>",  # <service-name>
    ]
    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return match.group(1)
    return "unknown"


def _parse_traces(file_path: Path) -> List[Dict[str, Any]]:
    """Parse distributed trace files (OTEL/Jaeger format)."""
    events = []
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            # Handle both array of spans and Jaeger/OTEL format
            spans = data if isinstance(data, list) else data.get("spans", data.get("data", []))
            for span in spans:
                events.append(
                    {
                        "event_id": span.get("spanID", span.get("span_id", "")),
                        "timestamp_ns": span.get("startTime", span.get("start_time", 0)),
                        "source_type": "otel_trace",
                        "message": f"Span: {span.get('name', 'unknown')}",
                        "attributes": {
                            "service": span.get("serviceName", span.get("service_name", "unknown")),
                            "trace_id": span.get("traceID", span.get("trace_id", "")),
                            "span_id": span.get("spanID", span.get("span_id", "")),
                            "parent_span_id": span.get(
                                "parentSpanID", span.get("parent_span_id", "")
                            ),
                            "duration_ns": span.get("duration", span.get("duration_ns", 0)),
                            "status": span.get("status", {}).get("code", "ok")
                            if isinstance(span.get("status"), dict)
                            else "ok",
                        },
                        "status": "error"
                        if span.get("status", {}).get("code") == "ERROR"
                        else "ok",
                    }
                )
    except Exception as e:
        logger.warning(f"Failed to parse traces from {file_path}: {e}")
    return events


def _parse_metrics_csv(file_path: Path) -> List[Dict[str, Any]]:
    """Parse Prometheus/CSV metrics into timeline events."""
    import logging

    logger = logging.getLogger(__name__)
    events = []
    try:
        import csv

        with open(file_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts_raw = row.get("timestamp", 0)
                if isinstance(ts_raw, str) and "T" in ts_raw:
                    # ISO format
                    timestamp_ns = _parse_iso_timestamp(ts_raw)
                else:
                    try:
                        timestamp_ns = int(float(ts_raw) * 1_000_000_000)
                    except (ValueError, TypeError):
                        timestamp_ns = 0

                events.append(
                    {
                        "event_id": f"{file_path.name}:{row.get('__name__', 'metric')}",
                        "timestamp_ns": timestamp_ns,
                        "source_type": "csv_metrics",
                        "message": "Prometheus scrape",
                        "attributes": {
                            k: float(v) if v.replace(".", "", 1).isdigit() else v
                            for k, v in row.items()
                            if k != "timestamp"
                        },
                        "status": "ok",
                    }
                )
    except Exception as e:
        logger.warning(f"Failed to parse metrics from {file_path}: {e}")
    return events


def _build_topology_from_manifest(
    topology_config: Dict[str, Any],
    aliases: Optional[Dict[str, str]] = None,
) -> SystemTopology:
    """Build SystemTopology from manifest configuration.

    Component names are canonicalised through the bundle's declared aliases,
    so a manifest that names a component one way and the evidence another
    way still ends up describing one component.
    """
    from cauveris.holographic.topology import ComponentInfo, ResourceCapacity, CausalEdge

    topology = SystemTopology()

    # Add components
    for comp_name, comp_data in topology_config.get("components", {}).items():
        topology.add_component(
            ComponentInfo(
                name=canonical_component(comp_name, aliases) or comp_name,
                component_type=comp_data.get("type", "service"),
                capacity=ResourceCapacity(
                    cpu_cores=comp_data.get("cpu_cores", 4.0),
                    memory_gb=comp_data.get("memory_gb", 8.0),
                    max_rps=comp_data.get("max_rps", 5000),
                ),
                boundary_layers=comp_data.get(
                    "boundary_layers", ["application_log", "metrics_export", "distributed_trace"]
                ),
            )
        )

    # Add edges
    for edge_data in topology_config.get("edges", []):
        topology.add_causal_edge(
            CausalEdge(
                source=canonical_component(edge_data["source"], aliases) or edge_data["source"],
                target=canonical_component(edge_data["target"], aliases) or edge_data["target"],
                latency_ms=edge_data.get("latency_ms", 5.0),
                edge_type=edge_data.get("type", "rpc"),
            )
        )

    return topology


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
        ),
        provenance=_synthetic_provenance(
            _missing_bundle(incident_id),
            incident_type=IncidentType.CPU_SPIKE_CASCADE.name,
        ),
    )


# ============================================================================
# INCIDENT COMPARISON ENDPOINT
# ============================================================================


class ComparisonRequest(BaseModel):
    incident_id_a: str
    incident_id_b: str
    include_visualization: bool = True


class NodeComparison(BaseModel):
    node_id: str
    in_a: bool
    in_b: bool
    cpu_delta: float
    memory_delta: float
    error_rate_delta: float
    latency_delta: float
    health_delta: float
    metrics_a: Dict[str, float]
    metrics_b: Dict[str, float]


class IncidentComparisonResponse(BaseModel):
    incident_a: str
    incident_b: str
    timestamp_ns: int
    node_comparisons: List[NodeComparison]
    summary: Dict[str, Any]


async def _load_incident_full(incident_id: str) -> Optional[VisualizationResponse]:
    """Load full visualization data for an incident (used by comparison endpoint)."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        timeline, temporal_analysis, topology, bundle, calibration, aliases = (
            await _get_incident_data(incident_id)
        )
        if timeline is None or topology is None:
            # A comparison is a claim about two real incidents — unlike the
            # single-incident view there is nothing meaningful to synthesize
            # here, so the caller gets a 404 instead of a fabricated diff.
            return None

        config = HolographicConfig(
            enable_multiscale=False,
            enable_compression=False,
            enable_visualization_data=True,
        )
        result = analyze_incident_holographically(
            incident_id=incident_id,
            timeline=timeline,
            topology=topology,
            config=config,
            temporal_analysis=temporal_analysis,
            calibration=calibration,
            aliases=aliases,
        )

        from cauveris.holographic.visualization import generate_visualization_data

        viz_data = generate_visualization_data(
            topology=topology,
            reconstruction=result.reconstruction,
            incident_id=incident_id,
            timestamp_ns=result.reconstruction.reconstruction_timestamp_ns,
            provenance=_bundle_provenance(
                bundle, timeline=timeline, reconstruction=result.reconstruction
            ),
        )

        viz_dict = _convert_numpy_types(viz_data.__dict__)
        return VisualizationResponse(**viz_dict)
    except Exception as e:
        logger.error(f"Failed to load incident {incident_id} for comparison: {e}")
        return None


@router.post("/comparison", response_model=IncidentComparisonResponse)
async def compare_incidents(request: ComparisonRequest):
    """
    Compare two incidents side-by-side with detailed metrics diff.

    Returns structured comparison data optimized for side-by-side 3D visualization.
    """
    import time

    # Load both incidents
    viz_a = await _load_incident_full(request.incident_id_a)
    viz_b = await _load_incident_full(request.incident_id_b)

    if not viz_a or not viz_b:
        raise HTTPException(
            status_code=404,
            detail=f"One or both incidents not found: {request.incident_id_a}, {request.incident_id_b}",
        )

    # Build node maps (bulk_nodes entries are plain dicts — see visualization._generate_bulk_nodes)
    nodes_a = {n["id"]: n for n in viz_a.bulk_nodes}
    nodes_b = {n["id"]: n for n in viz_b.bulk_nodes}
    all_node_ids = set(nodes_a.keys()) | set(nodes_b.keys())

    node_comparisons = []
    for node_id in sorted(all_node_ids):
        n_a = nodes_a.get(node_id)
        n_b = nodes_b.get(node_id)

        if n_a and n_b:
            # Both exist - compute deltas
            metrics_a = n_a["metrics"]
            metrics_b = n_b["metrics"]

            cpu_a = metrics_a["cpu_usage"]
            cpu_b = metrics_b["cpu_usage"]
            mem_a = metrics_a["memory_usage"]
            mem_b = metrics_b["memory_usage"]
            err_a = metrics_a["error_rate"]
            err_b = metrics_b["error_rate"]
            lat_a = metrics_a["latency_p99_ms"]
            lat_b = metrics_b["latency_p99_ms"]

            health_a = max(0.0, 1.0 - max(cpu_a * 0.4, mem_a * 0.3, err_a * 0.3))
            health_b = max(0.0, 1.0 - max(cpu_b * 0.4, mem_b * 0.3, err_b * 0.3))

            node_comparisons.append(
                NodeComparison(
                    node_id=node_id,
                    in_a=True,
                    in_b=True,
                    cpu_delta=cpu_b - cpu_a,
                    memory_delta=mem_b - mem_a,
                    error_rate_delta=err_b - err_a,
                    latency_delta=lat_b - lat_a,
                    health_delta=health_b - health_a,
                    metrics_a={
                        "cpu_usage": cpu_a,
                        "memory_usage": mem_a,
                        "error_rate": err_a,
                        "latency_p99_ms": lat_a,
                    },
                    metrics_b={
                        "cpu_usage": cpu_b,
                        "memory_usage": mem_b,
                        "error_rate": err_b,
                        "latency_p99_ms": lat_b,
                    },
                )
            )
        elif n_a:
            # Only in A
            metrics_a = n_a["metrics"]
            node_comparisons.append(
                NodeComparison(
                    node_id=node_id,
                    in_a=True,
                    in_b=False,
                    cpu_delta=0.0,
                    memory_delta=0.0,
                    error_rate_delta=0.0,
                    latency_delta=0.0,
                    health_delta=0.0,
                    metrics_a={
                        "cpu_usage": metrics_a["cpu_usage"],
                        "memory_usage": metrics_a["memory_usage"],
                        "error_rate": metrics_a["error_rate"],
                        "latency_p99_ms": metrics_a["latency_p99_ms"],
                    },
                    metrics_b={},
                )
            )
        else:
            # Only in B
            metrics_b = n_b["metrics"]
            node_comparisons.append(
                NodeComparison(
                    node_id=node_id,
                    in_a=False,
                    in_b=True,
                    cpu_delta=0.0,
                    memory_delta=0.0,
                    error_rate_delta=0.0,
                    latency_delta=0.0,
                    health_delta=0.0,
                    metrics_a={},
                    metrics_b={
                        "cpu_usage": metrics_b["cpu_usage"],
                        "memory_usage": metrics_b["memory_usage"],
                        "error_rate": metrics_b["error_rate"],
                        "latency_p99_ms": metrics_b["latency_p99_ms"],
                    },
                )
            )

    # Summary statistics
    in_both = sum(1 for c in node_comparisons if c.in_a and c.in_b)
    only_a = sum(1 for c in node_comparisons if c.in_a and not c.in_b)
    only_b = sum(1 for c in node_comparisons if c.in_b and not c.in_a)

    health_improved = sum(1 for c in node_comparisons if c.health_delta > 0.05)
    health_degraded = sum(1 for c in node_comparisons if c.health_delta < -0.05)

    summary = {
        "total_nodes_a": len(nodes_a),
        "total_nodes_b": len(nodes_b),
        "nodes_in_both": in_both,
        "nodes_only_in_a": only_a,
        "nodes_only_in_b": only_b,
        "health_improved_count": health_improved,
        "health_degraded_count": health_degraded,
        "avg_cpu_delta": sum(c.cpu_delta for c in node_comparisons) / len(node_comparisons)
        if node_comparisons
        else 0,
        "avg_memory_delta": sum(c.memory_delta for c in node_comparisons) / len(node_comparisons)
        if node_comparisons
        else 0,
        "avg_error_delta": sum(c.error_rate_delta for c in node_comparisons) / len(node_comparisons)
        if node_comparisons
        else 0,
        "avg_latency_delta": sum(c.latency_delta for c in node_comparisons) / len(node_comparisons)
        if node_comparisons
        else 0,
        "edge_count_a": len(viz_a.bulk_edges),
        "edge_count_b": len(viz_b.bulk_edges),
        "anomaly_count_a": len(viz_a.anomalies),
        "anomaly_count_b": len(viz_b.anomalies),
    }

    return IncidentComparisonResponse(
        incident_a=request.incident_id_a,
        incident_b=request.incident_id_b,
        timestamp_ns=int(time.time() * 1_000_000_000),
        node_comparisons=node_comparisons,
        summary=summary,
    )


async def _generate_synthetic_visualization_with_config(
    incident_id: str,
    config: HolographicConfig,
    provenance: Optional[Dict[str, Any]] = None,
):
    """Generate synthetic visualization data for demo purposes with config.

    ``provenance`` should describe the synthetic scenario (see
    :func:`_synthetic_provenance`). It defaults to the pessimistic
    "unverified synthetic" record so the payload is never silently presented
    as bundle-backed.
    """
    from cauveris.holographic.gpu_kernels import create_gpu_kernel_builder, is_gpu_available
    from cauveris.holographic.counterfactual import (
        CounterfactualHolographer,
        CausalKernelBuilder,
        Intervention,
        InterventionType,
    )
    from cauveris.holographic.anomaly import create_anomaly_detector
    from cauveris.holographic.synthetic import SyntheticIncidentGenerator, IncidentType

    generator = SyntheticIncidentGenerator(seed=42)
    incident = generator.generate(IncidentType.CPU_SPIKE_CASCADE)

    if provenance is None:
        provenance = _synthetic_provenance(
            _missing_bundle(incident_id),
            incident_type=IncidentType.CPU_SPIKE_CASCADE.name,
            timeline=incident.timeline,
        )

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
        provenance=provenance,
    )

    from cauveris.api.holographic import VisualizationResponse

    viz_dict = _convert_numpy_types(viz_data.__dict__)
    return VisualizationResponse(**viz_dict)


class ConnectionManager:
    """Manages WebSocket connections for live holographic updates."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.incident_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, incident_id: str):
        await websocket.accept()
        if incident_id not in self.active_connections:
            self.active_connections[incident_id] = set()
        self.active_connections[incident_id].add(websocket)
        logger.info(
            f"WebSocket connected for incident {incident_id}, total connections: {len(self.active_connections[incident_id])}"
        )

    def disconnect(self, websocket: WebSocket, incident_id: str):
        if incident_id in self.active_connections:
            self.active_connections[incident_id].discard(websocket)
            if not self.active_connections[incident_id]:
                del self.active_connections[incident_id]
                # Stop monitoring task if no more connections
                if incident_id in self.incident_tasks:
                    self.incident_tasks[incident_id].cancel()
                    del self.incident_tasks[incident_id]
        logger.info(f"WebSocket disconnected for incident {incident_id}")

    async def broadcast_to_incident(self, incident_id: str, message: Dict[str, Any]):
        """Broadcast message to all connections for an incident."""
        if incident_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[incident_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.add(connection)

            # Clean up disconnected
            for conn in disconnected:
                self.disconnect(conn, incident_id)

    async def start_monitoring(self, incident_id: str, interval_seconds: float = 5.0):
        """Start background task to monitor for new evidence and push updates."""
        if incident_id in self.incident_tasks:
            return  # Already monitoring

        async def monitor():
            try:
                controller = IngestionController()
                last_evidence_count = 0

                while (
                    incident_id in self.active_connections and self.active_connections[incident_id]
                ):
                    await asyncio.sleep(interval_seconds)

                    # Check for new evidence. Resolves through the same
                    # template list the request path uses, so a bundle the
                    # API can serve is never invisible to live monitoring.
                    evidence_store = Path(
                        _BUNDLE_SEARCH_TEMPLATES[0].format(incident_id=incident_id)
                    )
                    for template in _BUNDLE_SEARCH_TEMPLATES[1:]:
                        if evidence_store.exists():
                            break
                        evidence_store = Path(template.format(incident_id=incident_id))

                    if not evidence_store.exists():
                        continue

                    bundle = {
                        "found": True,
                        "path": str(evidence_store),
                        "search_paths": _bundle_search_paths(incident_id),
                    }

                    # Create incident and process
                    incident = Incident(
                        id=incident_id,
                        title=incident_id,
                        description="Live monitoring",
                        system_name="unknown",
                        bundle_path=str(evidence_store),
                    )

                    try:
                        incident = await controller.process(incident)
                    except Exception as e:
                        logger.warning(f"Failed to process incident during live monitoring: {e}")
                        continue

                    current_evidence_count = len(incident.evidence_items)
                    if current_evidence_count > last_evidence_count:
                        last_evidence_count = current_evidence_count

                        # Re-run holographic analysis with new data
                        try:
                            # Rebuild the timeline from the bundle: new
                            # evidence may have landed in any channel.
                            incident = await TimelineBuilder().build(incident)
                            timeline_events = incident.timeline_events
                            temporal_analysis = await _analyze_temporally(
                                incident, evidence_store
                            )

                            if not timeline_events:
                                timeline_events = _extract_timeline_from_evidence(
                                    incident, evidence_store
                                )

                            calibration = CalibrationProfile.from_bundle(evidence_store)
                            if timeline_events:
                                calibration.learn_from_events(timeline_events)
                            aliases = load_component_aliases(evidence_store)

                            topology = None
                            if incident.manifest and "topology" in incident.manifest:
                                topology = _build_topology_from_manifest(
                                    incident.manifest["topology"], aliases
                                )
                            elif timeline_events:
                                topology = build_topology_from_timeline(
                                    timeline_events, evidence_store, aliases
                                )

                            if topology and timeline_events:
                                # Run quick analysis
                                from cauveris.holographic.integration import HolographicConfig

                                config = HolographicConfig(
                                    enable_multiscale=False,
                                    enable_compression=False,
                                    enable_visualization_data=True,
                                )
                                result = analyze_incident_holographically(
                                    incident_id=incident_id,
                                    timeline=timeline_events,
                                    topology=topology,
                                    config=config,
                                    temporal_analysis=temporal_analysis,
                                    calibration=calibration,
                                    aliases=aliases,
                                )

                                # Generate visualization data
                                from cauveris.holographic.visualization import (
                                    generate_visualization_data,
                                )

                                viz_data = generate_visualization_data(
                                    topology=topology,
                                    reconstruction=result.reconstruction,
                                    incident_id=incident_id,
                                    timestamp_ns=result.reconstruction.reconstruction_timestamp_ns,
                                    provenance=_bundle_provenance(
                                        bundle,
                                        timeline=timeline_events,
                                        reconstruction=result.reconstruction,
                                    ),
                                )

                                viz_dict = _convert_numpy_types(viz_data.__dict__)

                                # Broadcast update
                                await self.broadcast_to_incident(
                                    incident_id,
                                    {
                                        "type": "reconstruction_update",
                                        "incident_id": incident_id,
                                        "data": viz_dict,
                                        "evidence_count": current_evidence_count,
                                        "timestamp": result.reconstruction.reconstruction_timestamp_ns,
                                    },
                                )

                        except Exception as e:
                            logger.error(f"Error during live reconstruction update: {e}")

            except asyncio.CancelledError:
                logger.info(f"Monitoring cancelled for incident {incident_id}")
            except Exception as e:
                logger.error(f"Monitoring task failed for incident {incident_id}: {e}")

        task = asyncio.create_task(monitor())
        self.incident_tasks[incident_id] = task


manager = ConnectionManager()


@router.websocket("/stream/{incident_id}")
async def websocket_holographic_stream(websocket: WebSocket, incident_id: str):
    """
    WebSocket endpoint for live holographic reconstruction updates.

    Connects to receive real-time updates as new evidence is ingested.
    Sends reconstruction updates when new evidence arrives.

    Message format:
    {
        "type": "reconstruction_update" | "connected" | "error",
        "incident_id": string,
        "data": VisualizationData | null,
        "evidence_count": number,
        "timestamp": number
    }
    """
    await manager.connect(websocket, incident_id)

    try:
        # Send initial connection confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "incident_id": incident_id,
                "message": f"Connected to live holographic stream for {incident_id}",
            }
        )

        # Start monitoring for this incident
        await manager.start_monitoring(incident_id, interval_seconds=5.0)

        # Keep connection alive and handle incoming messages
        while True:
            try:
                message = await websocket.receive_text()
                # Handle client messages if needed (e.g., config changes)
                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error receiving WebSocket message: {e}")
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for incident {incident_id}: {e}")
        try:
            await websocket.send_json(
                {"type": "error", "incident_id": incident_id, "message": str(e)}
            )
        except Exception:
            pass
    finally:
        manager.disconnect(websocket, incident_id)

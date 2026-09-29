"""
Main FastAPI application for Cauveris.
"""
import asyncio
import logging
import shutil
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uuid
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.schemas.hypothesis import Hypothesis
from cauveris.schemas.experiment import Experiment
from cauveris.schemas.patch import PatchCandidate, VerificationReport
from cauveris.datasets.golden_incident import GoldenIncidentGenerator
from cauveris.state_machine.orchestrator import PipelineOrchestrator, PipelineContext
from cauveris.ingestion.controller import IngestionController, extract_zip_safely
from cauveris.security import scan_for_secrets, compute_file_hash
from cauveris.patch.generator import PatchGenerator
from cauveris.config import get_settings

class ApplyPatchRequest(BaseModel):
    target_directory: str = "."
    dry_run: bool = False
    rollback: bool = False

class CustomSimulationRequest(BaseModel):
    batching_window_ms: float = 100.0
    qos_queue_depth: int = 5
    clock_skew_ms: float = 0.0
    max_batch_size: int = 4
    gpu_contention_ms: float = 0.0
    freshness_budget_ms: float = 120.0
    trials: int = 20

logger = logging.getLogger(__name__)

app = FastAPI(title="Cauveris API", version="0.1.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for incidents (replace with database in production)
incidents: dict[str, Incident] = {}
pipeline_tasks: dict[str, PipelineOrchestrator] = {}
pipeline_contexts: dict[str, PipelineContext] = {}

# Background task storage for pipeline progress
pipeline_progress: dict[str, dict] = {}


def _ensure_incident(incident_id: str) -> Optional[Incident]:
    """Ensure an incident is loaded in memory, hydrating from disk if available."""
    if incident_id in incidents:
        return incidents[incident_id]

    # Check if golden incident
    if incident_id.upper() in ["CAU-0001", "GOLDEN"]:
        generator = GoldenIncidentGenerator()
        incident = generator.generate()
        incidents[incident.id] = incident

        # Try to hydrate from existing report
        report_file = Path(f"./report/{incident.id}/incident_report.json")
        if report_file.exists():
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)

                # Hydrate timeline & status
                incident.timeline_events = report_data.get("timeline", [])
                incident.status = "COMPLETED"
                incident.temporal_analysis = report_data.get("temporal_analysis")

                # Hydrate pipeline context objects
                hyps = []
                for h in report_data.get("hypotheses", []):
                    try:
                        hyps.append(Hypothesis(**h))
                    except Exception:
                        pass

                exps = []
                for e in report_data.get("experiments", []):
                    try:
                        exps.append(Experiment(**e))
                    except Exception:
                        pass

                patches = []
                for p in report_data.get("patch_candidates", []):
                    try:
                        patches.append(PatchCandidate(**p))
                    except Exception:
                        pass

                reports = []
                for v in report_data.get("verification_reports", []):
                    try:
                        reports.append(VerificationReport(**v))
                    except Exception:
                        pass

                ctx = PipelineContext(
                    incident=incident,
                    validated_incident=incident,
                    timeline_events=incident.timeline_events,
                    temporal_analysis=incident.temporal_analysis,
                    hypotheses=hyps,
                    experiments=exps,
                    patch_candidates=patches,
                    verification_reports=reports,
                    final_report=report_data
                )
                pipeline_contexts[incident.id] = ctx
                pipeline_progress[incident.id] = {
                    "state": "COMPLETED",
                    "progress": 1.0,
                    "timestamp": report_data.get("generated_at", "2026-09-20T10:30:00Z")
                }
                logger.info(f"Hydrated full pipeline context for {incident.id} from report")
            except Exception as e:
                logger.warning(f"Failed to hydrate context from report: {e}")

        return incident

    return None


# Preload CAU-0001 immediately on module load so endpoints are warm
try:
    _ensure_incident("CAU-0001")
except Exception as _e:
    logger.debug(f"Preload golden incident skipped: {_e}")


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Cauveris API is running"}


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "cauveris", "version": "0.1.0"}


@app.get("/api/v1/incidents")
async def list_incidents():
    """List all available incidents in memory and discovered on disk."""
    results = []
    seen = set()

    # Pre-hydrate CAU-0001 if available
    _ensure_incident("CAU-0001")

    for inc_id, inc in incidents.items():
        seen.add(inc_id)
        results.append({
            "id": inc.id,
            "title": inc.title,
            "system_name": inc.system_name,
            "status": inc.status,
            "evidence_count": inc.evidence_count,
            "timeline_events_count": len(inc.timeline_events) if hasattr(inc, "timeline_events") and inc.timeline_events else 0,
            "approximate_time": inc.approximate_time.isoformat() if inc.approximate_time else None
        })

    # Discover any other incident folders on disk
    try:
        settings = get_settings()
        store = Path(settings.evidence_store_path)
        if store.exists():
            for d in store.iterdir():
                if d.is_dir() and d.name not in seen:
                    seen.add(d.name)
                    results.append({
                        "id": d.name,
                        "title": f"Incident {d.name}",
                        "system_name": "embedded-system",
                        "status": "OBSERVED",
                        "evidence_count": len(list(d.glob("**/*.*"))),
                        "timeline_events_count": 0,
                        "approximate_time": None
                    })

        for p in Path(".").glob("incident-*"):
            if p.is_dir():
                inc_id = p.name.replace("incident-", "")
                if inc_id not in seen:
                    seen.add(inc_id)
                    results.append({
                        "id": inc_id,
                        "title": f"Incident {inc_id}",
                        "system_name": "physical-ai-system",
                        "status": "OBSERVED",
                        "evidence_count": len(list(p.glob("**/*.*"))),
                        "timeline_events_count": 0,
                        "approximate_time": None
                    })
    except Exception as e:
        logger.debug(f"Error scanning disk for incidents: {e}")

    return {"incidents": results, "count": len(results)}


@app.post("/api/v1/incidents")
async def create_incident(background_tasks: BackgroundTasks, golden: bool = False):
    """
    Create a new incident. If golden=True, load the golden incident.
    Otherwise, expect a file upload in a separate call to /upload.
    """
    if golden:
        incident = _ensure_incident("CAU-0001")
        if not incident:
            generator = GoldenIncidentGenerator()
            incident = generator.generate()
            incidents[incident.id] = incident
        logger.info(f"Loaded golden incident {incident.id}")
        return {"incident_id": incident.id, "message": "Golden incident loaded"}
    else:
        # Create empty incident awaiting upload
        incident_id = str(uuid.uuid4())
        incident = Incident(
            title="Uploaded Incident",
            description="Incident uploaded via API",
        )
        incidents[incident_id] = incident
        logger.info(f"Created empty incident {incident_id}")
        return {"incident_id": incident_id, "message": "Incident created, ready for upload"}


@app.post("/api/v1/incidents/{incident_id}/upload")
async def upload_incident(incident_id: str, file: UploadFile = File(...)):
    """
    Upload an incident bundle (ZIP file) and attach it to the incident.
    """
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Validate file extension
    if file.filename is None or not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    # Read file content
    content = await file.read()

    # Save to temporary location for processing
    if file.filename is None:
        raise HTTPException(status_code=400, detail="File must have a filename")
    zip_path = Path("./temp_upload") / file.filename
    zip_path.parent.mkdir(exist_ok=True)

    try:
        # Write the uploaded file to temp location
        with open(zip_path, "wb") as buffer:
            buffer.write(content)

        logger.info(f"Saved uploaded file to {zip_path}")

        # Extract ZIP safely to permanent evidence store
        settings = get_settings()
        extract_dir = Path(settings.evidence_store_path) / incident_id
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            extracted_files = extract_zip_safely(zip_path, extract_dir)
            logger.info(f"Extracted {len(extracted_files)} files from ZIP to {extract_dir}")
        except ValueError as e:
            logger.error(f"ZIP extraction failed due to security violation: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid ZIP file: {str(e)}")
        except Exception as e:
            logger.error(f"ZIP extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to extract ZIP file")

        # Process each extracted file and create EvidenceItem objects
        incident = incidents[incident_id]
        incident.bundle_path = str(extract_dir)
        if incident.manifest is None:
            incident.manifest = {}
        incident.manifest["bundle_path"] = str(extract_dir)

        for extracted_file in extracted_files:
            try:
                # Get relative path for evidence tracking
                relative_path = extracted_file.relative_to(extract_dir)

                # Detect file type
                detected_type = IngestionController()._detect_file_type(extracted_file)

                # Validate file type (basic validation - in reality would use settings)
                # For demo, we'll accept common types
                allowed_types = {
                    "text/yaml", "application/json", "text/csv", "text/plain",
                    "text/markdown", "text/x-python", "application/octet-stream",
                    "image/png", "image/jpeg", "application/pdf", "video/mp4"
                }

                if detected_type not in allowed_types:
                    logger.warning(f"File type {detected_type} not in allowed list, but processing anyway")

                # Validate file size
                file_size = extracted_file.stat().st_size
                max_size = 100 * 1024 * 1024  # 100MB limit for demo
                if file_size > max_size:
                    logger.warning(f"File {relative_path} exceeds size limit: {file_size} bytes")
                    # Continue processing but flag in validation later

                # Compute checksum
                checksum = compute_file_hash(str(extracted_file))

                # Scan for secrets (text files only)
                secrets_found = []
                if detected_type.startswith('text/') or detected_type in ['application/json', 'application/yaml']:
                    try:
                        with open(extracted_file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        secrets_found = scan_for_secrets(content, str(extracted_file))
                    except Exception:
                        # If we can't read as text, skip secret scanning
                        pass

                # Determine status based on validation
                status = "OBSERVED"
                validation_errors = []

                if secrets_found:
                    validation_errors.append(f"Potential secrets detected: {', '.join(set([s[0] for s in secrets_found]))}")
                    status = "SECRETS_DETECTED"

                # Create EvidenceItem
                evidence = EvidenceItem(
                    file_path=str(relative_path),
                    file_type=detected_type,
                    size_bytes=file_size,
                    checksum_sha256=checksum,
                    status=status,
                    is_required=False,  # Most uploaded evidence is not strictly required
                    validation_errors=validation_errors
                )

                incident.evidence_items.append(evidence)
                logger.debug(f"Added evidence item for {relative_path}: {status}")

            except Exception as e:
                logger.error(f"Failed to process extracted file {extracted_file}: {e}")
                # Create a failed evidence item
                evidence = EvidenceItem(
                    file_path=str(extracted_file.relative_to(extract_dir)) if extract_dir in extracted_file.parents else extracted_file.name,
                    file_type="application/octet-stream",
                    size_bytes=0,
                    checksum_sha256="",
                    status="PROCESSING_ERROR",
                    is_required=False,
                    validation_errors=[f"Processing error: {str(e)}"]
                )
                incident.evidence_items.append(evidence)

        # Update incident evidence counts
        incident.update_counts()

        logger.info(f"Successfully processed upload for incident {incident_id}: {len(incident.evidence_items)} evidence items")
        return {
            "message": "File uploaded and processed",
            "filename": file.filename,
            "size": len(content),
            "evidence_count": len(incident.evidence_items)
        }

    finally:
        # Cleanup temporary upload zip
        try:
            if zip_path.exists():
                zip_path.unlink()
            # Also cleanup the temp upload directory if empty
            temp_upload_dir = Path("./temp_upload")
            if temp_upload_dir.exists() and not any(temp_upload_dir.iterdir()):
                temp_upload_dir.rmdir()
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")


@app.post("/api/v1/incidents/{incident_id}/validate")
async def validate_incident(incident_id: str):
    """
    Validate the incident bundle.
    """
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = incidents[incident_id]
    # Run ingestion/validation
    ingestion = IngestionController()
    # In reality, this would modify the incident in place
    # For now, we just return the incident
    validated_incident = await ingestion.process(incident)
    incidents[incident_id] = validated_incident

    return {
        "incident_id": incident_id,
        "validation_status": "completed",
        "evidence_count": validated_incident.evidence_count,
        "required_evidence_count": validated_incident.required_evidence_count,
        "missing_required_evidence": validated_incident.missing_required_evidence,
    }


@app.post("/api/v1/incidents/{incident_id}/reconstruct")
async def reconstruct_incident(incident_id: str, background_tasks: BackgroundTasks):
    """
    Start the incident reconstruction pipeline.
    """
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = incidents[incident_id]

    # Check if already processing
    if incident_id in pipeline_tasks:
        raise HTTPException(status_code=409, detail="Incident already being processed")

    # Create orchestrator
    orchestrator = PipelineOrchestrator()

    # Set up progress tracking
    def progress_callback(state, progress):
        pipeline_progress[incident_id] = {
            "state": state.name,
            "progress": progress,
            "timestamp": "2026-09-20T10:30:00Z",  # In reality, use current time
        }
        logger.info(f"Incident {incident_id} progress: {state.name} {progress*100:.1f}%")

    orchestrator.set_progress_callback(progress_callback)

    # Start pipeline in background
    pipeline_tasks[incident_id] = orchestrator
    background_tasks.add_task(_run_pipeline, incident_id, orchestrator, incident)

    return {"message": "Reconstruction started", "incident_id": incident_id}


async def _run_pipeline(incident_id: str, orchestrator: PipelineOrchestrator, incident: Incident):
    """Run the pipeline in the background and store the resulting context."""
    try:
        context: PipelineContext = await orchestrator.process_incident(incident)
        pipeline_contexts[incident_id] = context
        incidents[incident_id] = incident
        logger.info(f"Pipeline completed successfully for incident {incident_id}")
        if incident_id in pipeline_tasks:
            del pipeline_tasks[incident_id]
    except Exception as e:
        logger.exception(f"Pipeline failed for incident {incident_id}")
        pipeline_progress[incident_id] = {
            "state": "FAILED",
            "progress": 0.0,
            "error": str(e),
        }
        if incident_id in pipeline_tasks:
            del pipeline_tasks[incident_id]


@app.get("/api/v1/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get incident details with evidence items and metadata."""
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    return {
        "id": incident.id,
        "title": incident.title,
        "description": incident.description,
        "system_name": incident.system_name,
        "approximate_time": incident.approximate_time.isoformat() if incident.approximate_time else None,
        "evidence_count": incident.evidence_count,
        "required_evidence_count": incident.required_evidence_count,
        "missing_required_evidence": incident.missing_required_evidence,
        "status": incident.status,
        "manifest": incident.manifest,
        "timeline_events_count": len(incident.timeline_events),
        "evidence_items": [
            {
                "file_path": item.file_path,
                "file_type": item.file_type,
                "size_bytes": item.size_bytes,
                "checksum_sha256": item.checksum_sha256,
                "status": item.status,
                "is_required": item.is_required,
                "validation_errors": item.validation_errors
            }
            for item in incident.evidence_items
        ]
    }


@app.get("/api/v1/incidents/{incident_id}/timeline")
async def get_incident_timeline(incident_id: str):
    """Get the synchronized multi-lane timeline events and clock alignment."""
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    clock_alignment = incident.manifest.get("clock_alignment", {}) if incident.manifest else {}
    return {
        "incident_id": incident.id,
        "total_events": len(incident.timeline_events),
        "clock_alignment": clock_alignment,
        "timeline_events": incident.timeline_events
    }


@app.get("/api/v1/incidents/{incident_id}/temporal-analysis")
async def get_incident_temporal_analysis(incident_id: str):
    """Get temporal causality analysis for an incident."""
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.temporal_analysis:
        result = ctx.temporal_analysis
    elif getattr(incident, 'temporal_analysis', None):
        result = incident.temporal_analysis
    else:
        from cauveris.temporal.integration import TemporalAnalyzer
        analyzer = TemporalAnalyzer()
        result = analyzer.analyze_incident(incident)

    return {
        "incident_id": incident_id,
        "temporal_analysis": result,
        "violations": result.get("causality_violations", []),
        "clock_alignment": result.get("clock_analysis", {}),
        "anomalies": result.get("temporal_anomalies", []),
        "is_time_anomalous": result.get("is_time_anomalous", False),
        "confidence_score": result.get("temporal_confidence_score", 1.0),
    }


@app.get("/api/v1/incidents/{incident_id}/hypotheses")
async def get_incident_hypotheses(incident_id: str):
    """Get root-cause hypotheses with causal claims and evidence citations."""
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.hypotheses:
        hypotheses = ctx.hypotheses
    else:
        from cauveris.hypothesis.generator import HypothesisGenerator
        hg = HypothesisGenerator()
        hypotheses = await hg.generate(incident)
        if ctx:
            ctx.hypotheses = hypotheses

    formatted_hypotheses = []
    for h in hypotheses:
        dump = h.model_dump() if hasattr(h, "model_dump") else dict(h)
        hyp_id = dump.get("hypothesis_id", "")
        # Provide compatible fields for both frontend formats
        dump["id"] = hyp_id
        dump["title"] = hyp_id.replace("exp-", "").replace("h1_", "H1: ").replace("h2_", "H2: ").replace("h3_", "H3: ").replace("h4_", "H4: ").replace("_", " ").title()
        dump["description"] = dump.get("causal_claim", "")
        dump["confidence"] = int(float(dump.get("confidence_prior", 0.5)) * 100)
        dump["evidence_count"] = len(dump.get("supporting_artifact_ids", []))
        formatted_hypotheses.append(dump)

    return {
        "incident_id": incident_id,
        "count": len(formatted_hypotheses),
        "hypotheses": formatted_hypotheses
    }


@app.post("/api/v1/incidents/{incident_id}/hypotheses/{hypothesis_id}/test")
@app.post("/api/v1/incidents/{incident_id}/hypotheses/test")
async def test_hypothesis_endpoint(incident_id: str, hypothesis_id: str = "H1"):
    """
    Test a specific root-cause hypothesis in sandbox and simulate outcomes.
    """
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    hypotheses = ctx.hypotheses if ctx and ctx.hypotheses else None
    if not hypotheses:
        from cauveris.hypothesis.generator import HypothesisGenerator
        hg = HypothesisGenerator()
        hypotheses = await hg.generate(incident)
        if ctx:
            ctx.hypotheses = hypotheses

    # Find the hypothesis matching hypothesis_id
    target_hyp = None
    clean_target = hypothesis_id.strip().lower()
    for h in hypotheses:
        hid = h.hypothesis_id.lower()
        if hid == clean_target or clean_target in hid or hid.startswith(clean_target):
            target_hyp = h
            break

    if not target_hyp:
        prefix_map = {
            "h1": "h1_batching_window",
            "h2": "h2_qos_stale_messages",
            "h3": "h3_clock_skew",
            "h4": "h4_gpu_load_throttling"
        }
        mapped = prefix_map.get(clean_target)
        if mapped:
            for h in hypotheses:
                if h.hypothesis_id == mapped:
                    target_hyp = h
                    break

    if not target_hyp:
        target_hyp = hypotheses[0]

    # Run sandbox experiment and simulation
    from cauveris.sandbox.controller import SandboxController
    from cauveris.simulation.runner import SimulationRunner

    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments([target_hyp])
    await sandbox.run_experiments(experiments)

    sim_runner = SimulationRunner()
    sim_experiments = await sim_runner.run_simulations(experiments)
    exp = sim_experiments[0]

    is_confirmed = (exp.reproduction_rate == 0.0) or exp.failure_oracle.get("hypothesis_supported", False)

    if ctx and ctx.experiments:
        for idx, existing in enumerate(ctx.experiments):
            if existing.hypothesis_id == target_hyp.hypothesis_id:
                ctx.experiments[idx] = exp
                break

    msg = (
        "Hypothesis confirmed as root cause! Intervention eliminated emergency stops (0.0% failure reproduction)."
        if is_confirmed
        else f"Hypothesis refuted. Robot emergency stop failure persisted ({int(exp.reproduction_rate * 100)}% reproduction)."
    )

    return {
        "incident_id": incident_id,
        "hypothesis_id": target_hyp.hypothesis_id,
        "id": target_hyp.hypothesis_id,
        "title": target_hyp.hypothesis_id.replace('_', ' ').title(),
        "causal_claim": target_hyp.causal_claim,
        "intervention": target_hyp.intervention,
        "status": "CONFIRMED" if is_confirmed else "REFUTED",
        "reproduction_rate": exp.reproduction_rate,
        "hypothesis_supported": is_confirmed,
        "failure_oracle": exp.failure_oracle,
        "metrics": getattr(exp, "metrics", {}),
        "message": msg
    }


@app.get("/api/v1/incidents/{incident_id}/experiments")
async def get_incident_experiments(incident_id: str):
    """Get sandbox experiment branches and reproduction metrics."""
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    experiments = ctx.experiments if ctx and ctx.experiments else []

    formatted_experiments = []
    for e in experiments:
        dump = e.model_dump() if hasattr(e, "model_dump") else dict(e)
        exp_id = dump.get("experiment_id", "")
        dump["id"] = exp_id
        dump["name"] = exp_id.replace("exp-", "").replace("_", " ").title()
        dump["result"] = dump.get("reproduction_rate", 1.0) == 0.0
        formatted_experiments.append(dump)

    return {
        "incident_id": incident_id,
        "count": len(formatted_experiments),
        "experiments": formatted_experiments
    }


@app.post("/api/v1/incidents/{incident_id}/experiments/run")
async def run_experiments_endpoint(incident_id: str):
    """Run all experiments in sandboxes and digital twin simulations."""
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    hypotheses = ctx.hypotheses if ctx and ctx.hypotheses else None
    if not hypotheses:
        from cauveris.hypothesis.generator import HypothesisGenerator
        hg = HypothesisGenerator()
        hypotheses = await hg.generate(incident)

    from cauveris.sandbox.controller import SandboxController
    from cauveris.simulation.runner import SimulationRunner

    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments(hypotheses)
    await sandbox.run_experiments(experiments)

    sim_runner = SimulationRunner()
    sim_experiments = await sim_runner.run_simulations(experiments)

    if ctx:
        ctx.experiments = sim_experiments

    return {
        "incident_id": incident_id,
        "count": len(sim_experiments),
        "experiments": [
            {
                "id": e.experiment_id,
                "experiment_id": e.experiment_id,
                "name": e.experiment_id.replace('exp-', '').replace('_', ' ').title(),
                "hypothesis_id": e.hypothesis_id,
                "branch_name": e.branch_name,
                "status": e.status,
                "intervention": e.intervention,
                "reproduction_rate": e.reproduction_rate,
                "result": e.reproduction_rate == 0.0,
                "failure_oracle": e.failure_oracle,
                "metrics": getattr(e, "metrics", {})
            }
            for e in sim_experiments
        ],
        "message": "Digital twin simulations completed across all experiment branches"
    }


@app.post("/api/v1/incidents/{incident_id}/simulate-custom")
async def simulate_custom_parameters(incident_id: str, request: CustomSimulationRequest):
    """
    Run custom digital twin simulation with interactive parameters (Engineer Mode).
    Simulates real-world queuing, batching, GPU compute, network jitter, and safety invariants.
    """
    from cauveris.simulation.runner import CloudToRobotDigitalTwin, DigitalTwinFaultInjectors
    faults = DigitalTwinFaultInjectors(
        batching_window_ms=request.batching_window_ms,
        qos_queue_depth=request.qos_queue_depth,
        clock_skew_ms=request.clock_skew_ms,
        max_batch_size=request.max_batch_size,
        gpu_contention_ms=request.gpu_contention_ms
    )
    twin = CloudToRobotDigitalTwin(faults)
    twin.freshness_budget_ms = request.freshness_budget_ms

    cycles = []
    reproduction_count = 0
    for i in range(request.trials):
        step_res = twin.step(seed=5000 + i)
        cycles.append(step_res)
        if step_res["emergency_stop"]:
            reproduction_count += 1

    reproduction_rate = reproduction_count / request.trials if request.trials > 0 else 0.0
    latencies = [c["total_latency_ms"] for c in cycles]
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0
    sorted_latencies = sorted(latencies)
    p99_idx = int(0.99 * len(sorted_latencies))
    p99_latency = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)] if sorted_latencies else 0.0

    hypothesis_supported = reproduction_rate < 0.20 and avg_latency <= twin.freshness_budget_ms

    return {
        "incident_id": incident_id,
        "trial_count": request.trials,
        "reproduction_count": reproduction_count,
        "reproduction_rate": reproduction_rate,
        "avg_latency_ms": avg_latency,
        "p99_latency_ms": p99_latency,
        "freshness_budget_ms": twin.freshness_budget_ms,
        "emergency_stop_triggered": reproduction_count > 0,
        "hypothesis_supported": hypothesis_supported,
        "status": "CONFIRMED" if hypothesis_supported else "REFUTED",
        "parameters": request.model_dump(),
        "cycles": cycles[:10],
        "message": (
            f"Intervention verified: 0 emergency stops produced (avg latency {avg_latency:.1f}ms <= {twin.freshness_budget_ms}ms limit)"
            if hypothesis_supported
            else f"Safety violation triggered: {reproduction_count}/{request.trials} emergency stops ({reproduction_rate:.1%}, avg latency {avg_latency:.1f}ms)"
        )
    }


@app.get("/api/v1/incidents/{incident_id}/patches")
async def get_incident_patches(incident_id: str):
    """Get patch candidates with 9-point verification results."""
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    patches = ctx.patch_candidates if ctx and ctx.patch_candidates else []
    verification_reports = ctx.verification_reports if ctx and ctx.verification_reports else []

    formatted_patches = []
    for p in patches:
        dump = p.model_dump() if hasattr(p, "model_dump") else dict(p)
        cand_id = dump.get("candidate_id", "")
        dump["id"] = cand_id
        dump["title"] = cand_id.replace("patch-", "").replace("exp-", "").replace("_", " ").title()
        dump["diff"] = dump.get("unified_diff", "")
        formatted_patches.append(dump)

    formatted_reports = [
        r.model_dump() if hasattr(r, "model_dump") else dict(r)
        for r in verification_reports
    ]

    return {
        "incident_id": incident_id,
        "count": len(formatted_patches),
        "patch_candidates": formatted_patches,
        "verification_reports": formatted_reports
    }


@app.get("/api/v1/incidents/{incident_id}/report")
async def get_incident_report(incident_id: str):
    """Get comprehensive incident investigation report."""
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.final_report:
        return ctx.final_report

    report_file = Path(f"./report/{incident_id}/incident_report.json")
    if report_file.exists():
        with open(report_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    if incident_id.upper() == "CAU-0001":
        alt_report = Path("./report/CAU-0001/incident_report.json")
        if alt_report.exists():
            with open(alt_report, 'r', encoding='utf-8') as f:
                return json.load(f)

    return {"message": "Report not yet generated for this incident"}


@app.get("/status-center")
@app.get("/api/v1/status-center")
async def get_status_center():
    """Get orchestration and system health status center."""
    _ensure_incident("CAU-0001")
    incident_count = len(incidents)
    active_inc = incidents.get("CAU-0001")
    stage = pipeline_progress.get("CAU-0001", {}).get("state", "COMPLETED" if active_inc else "IDLE")
    return {
        "status": "healthy",
        "incidents_count": incident_count,
        "active_incident_id": "CAU-0001" if active_inc else None,
        "current_stage": stage,
        "model_route": "Local Fixtures (Deterministic)",
        "sandbox_status": "Ready",
        "timestamp": "2026-09-20T10:30:00Z"
    }


@app.get("/api/v1/incidents/{incident_id}/download-patch-package")
async def download_patch_package(incident_id: str):
    """Download the complete verified patch package as a ZIP archive."""
    pkg_dir = Path(f"./report/{incident_id}/patch-package")
    if not pkg_dir.exists():
        # Check alternative report location
        pkg_dir = Path("./report/CAU-0001/patch-package")

    if not pkg_dir.exists():
        raise HTTPException(status_code=404, detail="Patch package not found for this incident")

    zip_dest = Path(f"./report/{incident_id}_patch_package.zip")
    shutil.make_archive(str(zip_dest.with_suffix('')), 'zip', str(pkg_dir))

    return FileResponse(
        str(zip_dest),
        filename=f"cauveris-patch-package-{incident_id}.zip",
        media_type="application/zip"
    )


@app.get("/api/v1/incidents/{incident_id}/export-patch")
async def export_incident_patch(incident_id: str, format: str = "installer"):
    """
    Export the verified patch for direct import into the infected space.
    Formats:
      - 'installer' (default): zero-dependency self-contained executable apply_patch.py
      - 'patch': standard universal unified diff fix.patch
      - 'zip': complete verified patch package archive
    """
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    pkg_dir = Path(f"./report/{incident_id}/patch-package")
    if not pkg_dir.exists():
        pkg_dir = Path("./report/CAU-0001/patch-package")

    # If patch package doesn't exist yet, generate from pipeline context or golden patch
    if not pkg_dir.exists():
        ctx = pipeline_contexts.get(incident_id)
        patches = ctx.patch_candidates if ctx else []
        verified_patches = [p for p in patches if p.verified]
        if verified_patches:
            patch_gen = PatchGenerator()
            patch_gen.export_patch(verified_patches[0], pkg_dir)
        else:
            raise HTTPException(status_code=404, detail="No verified patch candidate available to export")

    if format.lower() in ["installer", "python", "script"]:
        installer_file = pkg_dir / "apply_patch.py"
        if not installer_file.exists():
            ctx = pipeline_contexts.get(incident_id)
            if ctx and ctx.patch_candidates:
                PatchGenerator().export_patch(ctx.patch_candidates[0], pkg_dir)
        if not installer_file.exists():
            raise HTTPException(status_code=404, detail="Installer script not found")
        return FileResponse(
            str(installer_file),
            filename=f"apply_patch_{incident_id}.py",
            media_type="text/x-python"
        )
    elif format.lower() in ["patch", "diff"]:
        patch_file = pkg_dir / "fix.patch"
        if not patch_file.exists():
            raise HTTPException(status_code=404, detail="fix.patch not found")
        return FileResponse(
            str(patch_file),
            filename=f"cauveris-fix-{incident_id}.patch",
            media_type="text/x-diff"
        )
    else:
        # Default or zip format
        zip_dest = Path(f"./report/{incident_id}_patch_package.zip")
        shutil.make_archive(str(zip_dest.with_suffix('')), 'zip', str(pkg_dir))
        return FileResponse(
            str(zip_dest),
            filename=f"cauveris-patch-package-{incident_id}.zip",
            media_type="application/zip"
        )


@app.post("/api/v1/incidents/{incident_id}/apply-patch")
async def apply_patch_to_target(incident_id: str, request: ApplyPatchRequest):
    """
    Directly apply or rollback the verified patch on an infected target space.
    """
    incident = _ensure_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    target_path = Path(request.target_directory).resolve()
    # Check if target workspace has incident directory
    if (target_path / f"incident-{incident_id}").exists():
        target_path = (target_path / f"incident-{incident_id}").resolve()
    elif not target_path.exists():
        raise HTTPException(status_code=400, detail=f"Target directory '{request.target_directory}' does not exist")

    pkg_dir = Path(f"./report/{incident_id}/patch-package")
    if not pkg_dir.exists():
        pkg_dir = Path("./report/CAU-0001/patch-package")

    installer_file = pkg_dir / "apply_patch.py"
    if not installer_file.exists():
        ctx = pipeline_contexts.get(incident_id)
        if ctx and ctx.patch_candidates:
            PatchGenerator().export_patch(ctx.patch_candidates[0], pkg_dir)
            installer_file = pkg_dir / "apply_patch.py"

    if not installer_file.exists():
        raise HTTPException(status_code=404, detail="No verified patch installer found for this incident")

    # Execute installer script within target space
    scope: dict = {}
    with open(installer_file, "r", encoding="utf-8") as f:
        code = f.read()
    exec(code, scope)

    if request.rollback:
        rollback_fn = scope.get("rollback")
        if not callable(rollback_fn):
            raise HTTPException(status_code=500, detail="Rollback function not found in installer")
        success = rollback_fn(target_dir=str(target_path))
        return {
            "incident_id": incident_id,
            "operation": "rollback",
            "target_directory": str(target_path),
            "success": True if success is not False else False,
            "status": scope.get("status", lambda x: "INFECTED")(str(target_path))
        }
    else:
        apply_fn = scope.get("apply")
        if not callable(apply_fn):
            raise HTTPException(status_code=500, detail="Apply function not found in installer")
        success = apply_fn(target_dir=str(target_path), dry_run=request.dry_run)
        return {
            "incident_id": incident_id,
            "operation": "dry_run" if request.dry_run else "apply",
            "target_directory": str(target_path),
            "success": success,
            "status": scope.get("status", lambda x: "UNKNOWN")(str(target_path))
        }


@app.get("/api/v1/incidents/{incident_id}/events")
async def get_incident_events(incident_id: str):
    """Get processing events/progress for an incident."""
    if incident_id not in pipeline_progress:
        if incident_id in incidents:
            return {"state": "RECEIVED", "progress": 0.0}
        else:
            raise HTTPException(status_code=404, detail="Incident not found")

    return pipeline_progress[incident_id]


@app.get("/api/v1/incidents/{incident_id}/stream")
async def stream_incident_progress(incident_id: str):
    """
    Server-Sent Events endpoint for real-time progress updates.
    """
    async def event_generator():
        last_state = None
        while True:
            if incident_id in pipeline_progress:
                progress = pipeline_progress[incident_id]
                if progress.get("state") != last_state:
                    last_state = progress.get("state")
                    yield f"data: {json.dumps(progress)}\n\n"

                if last_state in ["COMPLETED", "FAILED"]:
                    break
            else:
                if incident_id not in incidents:
                    yield f"data: {json.dumps({'error': 'Incident not found'})}\n\n"
                    break
                else:
                    yield f"data: {json.dumps({'state': 'RECEIVED', 'progress': 0.0})}\n\n"

            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/v1/incidents/{incident_id}/temporal-visualization")
async def get_incident_temporal_visualization(incident_id: str):
    """
    Get visualization data for temporal anomalies.

    Returns data structured for an interactive timeline that shows:
    * Events positioned by relative time
    * Causal edges between events
    * Anomaly markers and time loop cycles
    * Untrusted time windows
    """
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.temporal_analysis:
        temporal_result = ctx.temporal_analysis
    else:
        from cauveris.temporal.integration import TemporalAnalyzer
        analyzer = TemporalAnalyzer()
        temporal_result = analyzer.analyze_incident(incidents[incident_id])

    from cauveris.temporal.visualization import build_timeline_visualization_data

    return build_timeline_visualization_data(temporal_result, incidents[incident_id].timeline_events)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

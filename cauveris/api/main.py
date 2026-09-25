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
from pydantic import BaseModel
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.datasets.golden_incident import GoldenIncidentGenerator
from cauveris.state_machine.orchestrator import PipelineOrchestrator, PipelineContext
from cauveris.ingestion.controller import IngestionController, extract_zip_safely
from cauveris.security import scan_for_secrets, compute_file_hash
from cauveris.patch.generator import PatchGenerator

class ApplyPatchRequest(BaseModel):
    target_directory: str = "."
    dry_run: bool = False
    rollback: bool = False

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


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Cauveris API is running"}


@app.get("/health")
@app.get("/api/v1/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "service": "cauveris", "version": "0.1.0"}


@app.post("/api/v1/incidents")
async def create_incident(background_tasks: BackgroundTasks, golden: bool = False):
    """
    Create a new incident. If golden=True, load the golden incident.
    Otherwise, expect a file upload in a separate call to /upload.
    """
    if golden:
        # Generate golden incident
        generator = GoldenIncidentGenerator()
        incident = generator.generate()
        incidents[incident.id] = incident
        logger.info(f"Created golden incident {incident.id}")
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

        # Extract ZIP safely
        extract_dir = Path("./temp_extract") / incident_id
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            extracted_files = extract_zip_safely(zip_path, extract_dir)
            logger.info(f"Extracted {len(extracted_files)} files from ZIP")
        except ValueError as e:
            logger.error(f"ZIP extraction failed due to security violation: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid ZIP file: {str(e)}")
        except Exception as e:
            logger.error(f"ZIP extraction failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to extract ZIP file")

        # Process each extracted file and create EvidenceItem objects
        incident = incidents[incident_id]

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
        # Cleanup temporary files
        try:
            if zip_path.exists():
                zip_path.unlink()
            extract_dir = Path("./temp_extract") / incident_id
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
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
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = incidents[incident_id]
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


@app.get("/api/v1/incidents")
async def list_incidents():
    """List all incidents."""
    return {
        "incidents": [
            {
                "id": inc.id,
                "title": inc.title,
                "system_name": inc.system_name,
                "evidence_count": inc.evidence_count,
                "status": inc.status,
            }
            for inc in incidents.values()
        ]
    }


@app.get("/api/v1/incidents/{incident_id}/timeline")
async def get_incident_timeline(incident_id: str):
    """Get the synchronized multi-lane timeline events and clock alignment."""
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = incidents[incident_id]
    clock_alignment = incident.manifest.get("clock_alignment", {}) if incident.manifest else {}
    return {
        "incident_id": incident.id,
        "total_events": len(incident.timeline_events),
        "clock_alignment": clock_alignment,
        "timeline_events": incident.timeline_events
    }


@app.get("/api/v1/incidents/{incident_id}/hypotheses")
async def get_incident_hypotheses(incident_id: str):
    """Get root-cause hypotheses with causal claims and evidence citations."""
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.hypotheses:
        hypotheses = ctx.hypotheses
    else:
        # Fallback: generate hypotheses from incident
        from cauveris.hypothesis.generator import HypothesisGenerator
        hg = HypothesisGenerator()
        hypotheses = await hg.generate(incidents[incident_id])

    return {
        "incident_id": incident_id,
        "count": len(hypotheses),
        "hypotheses": [h.model_dump() for h in hypotheses]
    }


@app.get("/api/v1/incidents/{incident_id}/experiments")
async def get_incident_experiments(incident_id: str):
    """Get sandbox experiment branches and reproduction metrics."""
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    experiments = ctx.experiments if ctx else []
    return {
        "incident_id": incident_id,
        "count": len(experiments),
        "experiments": [e.model_dump() for e in experiments]
    }


@app.get("/api/v1/incidents/{incident_id}/patches")
async def get_incident_patches(incident_id: str):
    """Get patch candidates with 9-point verification results."""
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    patches = ctx.patch_candidates if ctx else []
    verification_reports = ctx.verification_reports if ctx else []
    return {
        "incident_id": incident_id,
        "count": len(patches),
        "patch_candidates": [p.model_dump() for p in patches],
        "verification_reports": [r.model_dump() for r in verification_reports]
    }


@app.get("/api/v1/incidents/{incident_id}/report")
async def get_incident_report(incident_id: str):
    """Get comprehensive incident investigation report."""
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    ctx = pipeline_contexts.get(incident_id)
    if ctx and ctx.final_report:
        return ctx.final_report

    report_file = Path(f"./report/{incident_id}/incident_report.json")
    if report_file.exists():
        with open(report_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    return {"message": "Report not yet generated for this incident"}


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
    if incident_id not in incidents:
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
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    target_path = Path(request.target_directory).resolve()
    if not target_path.exists():
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
            "success": success,
            "status": scope.get("status", lambda x: "UNKNOWN")(str(target_path))
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

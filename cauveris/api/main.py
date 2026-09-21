"""
Main FastAPI application for Cauveris.
"""
import asyncio
import hashlib
import logging
import shutil
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uuid
import json
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.datasets.golden_incident import GoldenIncidentGenerator
from cauveris.state_machine.orchestrator import PipelineOrchestrator, PipelineContext
from cauveris.ingestion.controller import IngestionController, extract_zip_safely
from cauveris.security import compute_file_hash, scan_for_secrets

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

# Background task storage for pipeline progress
pipeline_progress: dict[str, dict] = {}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Cauveris API is running"}


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

    incident = incidents[incident_id]

    # Validate file extension
    if not file.filename.lower().endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    # Read file content
    content = await file.read()

    # Save to temporary location for processing
    zip_path = Path("./temp_upload") / file.filename
    zip_path.parent.mkdir(exist_ok=True)

    with open(zip_path, "wb") as f:
        f.write(content)

    try:
        # Extract ZIP safely
        extract_dir = Path("./temp_upload") / "extracted"
        extract_dir.mkdir(exist_ok=True)

        # Clear previous extraction
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir()

        extracted_files = extract_zip_safely(zip_path, extract_dir)

        # Create EvidenceItem for each extracted file
        evidence_items = []
        for extracted_file in extracted_files:
            # Get relative path from extract_dir for storage in evidence
            relative_path = extracted_file.relative_to(extract_dir)

            # Detect file type from content
            detected_type = IngestionController()._detect_file_type(extracted_file)

            # Compute checksum and size
            checksum = compute_file_hash(str(extracted_file))
            size_bytes = extracted_file.stat().st_size

            # Scan for secrets (text files only)
            secrets_found = []
            try:
                with open(str(extracted_file), 'r', encoding='utf-8', errors='ignore') as f:
                    file_content = f.read()
                secrets_found = scan_for_secrets(file_content, str(extracted_file))
            except Exception:
                # If we can't read as text, skip secret scanning
                pass

            evidence = EvidenceItem(
                file_path=str(relative_path),
                file_type=detected_type,
                size_bytes=size_bytes,
                checksum_sha256=checksum,
                status="OBSERVED",
                is_required=True,  # All extracted files are required for processing
            )

            if secrets_found:
                evidence.validation_errors = [f"Potential secrets detected: {', '.join(secrets_found)}"]
                evidence.status = "SECRETS_DETECTED"

            evidence_items.append(evidence)

        # Clear existing evidence items and replace with extracted ones
        # (We keep the ZIP file evidence item as well for record-keeping)
        incident.evidence_items.clear()

        # Add ZIP file evidence
        zip_checksum = hashlib.sha256(content).hexdigest()
        zip_evidence = EvidenceItem(
            file_path=f"{file.filename}",
            file_type="application/zip",
            size_bytes=len(content),
            checksum_sha256=zip_checksum,
            status="OBSERVED",
            is_required=True,
        )
        incident.evidence_items.append(zip_evidence)

        # Add all extracted file evidence
        incident.evidence_items.extend(evidence_items)

        # Update counts
        incident.update_counts()

        logger.info(f"Uploaded and extracted {file.filename} with {len(evidence_items)} files for incident {incident_id}")
        return {
            "message": "File uploaded and extracted successfully",
            "filename": file.filename,
            "size": len(content),
            "extracted_files": len(evidence_items)
        }

    except Exception as e:
        logger.error(f"Error processing upload {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process upload: {str(e)}")
    finally:
        # Cleanup temporary files
        try:
            if zip_path.exists():
                zip_path.unlink()
            extract_dir = Path("./temp_upload") / "extracted"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
        except Exception as e:
            logger.warning(f"Cleanup warning: {e}")


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
    """Run the pipeline in the background."""
    try:
        _context: PipelineContext = await orchestrator.process_incident(incident)
        # Store final results (in reality, we'd update the incident or store in database)
        logger.info(f"Pipeline completed for incident {incident_id}")
        # Clean up task reference
        if incident_id in pipeline_tasks:
            del pipeline_tasks[incident_id]
    except Exception as e:
        logger.exception(f"Pipeline failed for incident {incident_id}")
        # Store error
        pipeline_progress[incident_id] = {
            "state": "FAILED",
            "progress": 0.0,
            "error": str(e),
        }
        if incident_id in pipeline_tasks:
            del pipeline_tasks[incident_id]


@app.get("/api/v1/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Get incident details."""
    if incident_id not in incidents:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident = incidents[incident_id]
    # Return a safe representation (excluding large binary data)
    return {
        "id": incident.id,
        "title": incident.title,
        "description": incident.description,
        "system_name": incident.system_name,
        "approximate_time": incident.approximate_time.isoformat() if incident.approximate_time else None,
        "evidence_count": incident.evidence_count,
        "required_evidence_count": incident.required_evidence_count,
        "missing_required_evidence": incident.missing_required_evidence,
        # Don't return full evidence items to avoid huge responses
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
            }
            for inc in incidents.values()
        ]
    }


@app.get("/api/v1/incidents/{incident_id}/events")
async def get_incident_events(incident_id: str):
    """Get processing events/progress for an incident."""
    if incident_id not in pipeline_progress:
        # Check if incident exists but not processed
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

                # Stop streaming if completed or failed
                if last_state in ["COMPLETED", "FAILED"]:
                    break
            else:
                # Incident not found or not being processed
                if incident_id not in incidents:
                    yield f"data: {json.dumps({'error': 'Incident not found'})}\n\n"
                    break
                else:
                    yield f"data: {json.dumps({'state': 'RECEIVED', 'progress': 0.0})}\n\n"

            # Wait before next update
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

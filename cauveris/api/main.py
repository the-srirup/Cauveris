"""
Main FastAPI application for Cauveris.
"""
import asyncio
import logging
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uuid
import json
from cauveris.schemas.incident import Incident, EvidenceItem
from cauveris.datasets.golden_incident import GoldenIncidentGenerator
from cauveris.state_machine.orchestrator import PipelineOrchestrator, PipelineContext
from cauveris.ingestion.controller import IngestionController

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

    # In a real implementation, we would:
    # 1. Validate the file is a ZIP
    # 2. Extract it safely
    # 3. Scan for secrets
    # 4. Validate contents
    # 5. Create EvidenceItem objects for each file
    #
    # For now, we'll simulate by creating a dummy evidence item
    incident = incidents[incident_id]

<<<<<<< HEAD
    # Read file content (in reality, we'd save to temp and extract)
    content = await file.read()

    # Create a placeholder evidence item for the ZIP itself
    import hashlib
    checksum = hashlib.sha256(content).hexdigest()
    evidence = EvidenceItem(
        file_path=f"{file.filename}",
        file_type="application/zip",
        size_bytes=len(content),
        checksum_sha256=checksum,
        status="OBSERVED",
        is_required=True,
    )
    incident.evidence_items.append(evidence)
    incident.update_counts()
=======
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
>>>>>>> 95fa243 (Fixed Issue)

    logger.info(f"Uploaded file {file.filename} for incident {incident_id}")
    return {"message": "File uploaded", "filename": file.filename, "size": len(content)}


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

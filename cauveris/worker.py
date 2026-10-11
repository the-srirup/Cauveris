"""
Cauveris Worker - Background job processor.

Subscribes to the shared job queue via JobQueue.register_handler() /
start_worker() and processes jobs as they are dequeued.

Run as a separate process:

    python -m cauveris.worker

Note: with the default in-memory queue backend, jobs submitted inside the API
process are not visible to this process — a cross-process backend (Redis /
RabbitMQ) is required for a separate worker to observe them.
"""

import asyncio
import logging
import signal
from pathlib import Path

from cauveris.config import get_settings
from cauveris.job_queue import get_job_queue
from cauveris.logging_config import setup_structured_logging, get_logger

logger = get_logger(__name__)

# Canonical job type strings (see job_queue.Job.type docstring).
WORKER_TYPES = ["pipeline", "simulation", "patch_generation"]


async def process_pipeline_job(job):
    """Process a pipeline job for an incident loaded from the evidence store."""
    from cauveris.api.main import _run_pipeline
    from cauveris.state_machine.orchestrator import PipelineOrchestrator, PipelineContext
    from cauveris.ingestion.controller import IngestionController

    incident_id = job.payload.get("incident_id")
    if not incident_id:
        raise ValueError("incident_id required in payload")

    # Load directly (async) rather than via the API's _ensure_incident, which
    # calls asyncio.run() and would fail inside this running event loop.
    # Mirror _ensure_incident's lookup (including its incident-<id> fallback
    # patterns) and GUARD existence: load_incident_from_store silently builds
    # an empty Incident for a missing bundle, which would run a full pipeline
    # cycle on a bogus id and be reported as COMPLETED. Raising here instead
    # fails the job and engages the queue's retry/dead-letter semantics.
    evidence_path = Path(get_settings().evidence_store_path) / incident_id
    if not evidence_path.exists():
        for pattern in (f"./incident-{incident_id}", f"./incident-{incident_id.lower()}"):
            pattern_path = Path(pattern)
            if pattern_path.exists():
                evidence_path = pattern_path
                break
    if not evidence_path.exists():
        raise ValueError(f"Incident {incident_id} not found in evidence store at {evidence_path}")
    if not (evidence_path / "manifest.yaml").exists():
        raise ValueError(f"Incident {incident_id} has no manifest.yaml at {evidence_path}")

    ingestion = IngestionController()
    try:
        incident = await ingestion.load_incident_from_store(incident_id, evidence_path)
    except Exception as e:
        raise ValueError(
            f"Incident {incident_id} could not be loaded from evidence store "
            f"at {evidence_path}: {e}"
        ) from e

    logger.info(f"Processing pipeline job {job.id} for incident {incident_id}")

    orchestrator = PipelineOrchestrator()
    orchestrator.context = PipelineContext(incident=incident)

    await _run_pipeline(incident_id, orchestrator, incident)


async def process_simulation_job(job):
    """Process a simulation job."""
    logger.info(f"Processing simulation job {job.id}: handled by the pipeline")
    # Simulation jobs are handled by the pipeline
    return {"status": "no-op"}


async def process_patch_job(job):
    """Process a patch generation job."""
    logger.info(f"Processing patch job {job.id}: handled by the pipeline")
    # Patch generation is handled by the pipeline
    return {"status": "no-op"}


JOB_HANDLERS = {
    "pipeline": process_pipeline_job,
    "simulation": process_simulation_job,
    "patch_generation": process_patch_job,
}


async def run_worker():
    """Main worker loop — registers handlers and lets JobQueue drive processing."""
    queue = get_job_queue()
    if not queue:
        logger.error("Job queue not initialized")
        return

    for job_type, handler in JOB_HANDLERS.items():
        queue.register_handler(job_type, handler)

    logger.info("Starting Cauveris worker")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        loop.call_soon_threadsafe(stop_event.set)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    await queue.start_worker(WORKER_TYPES)
    try:
        await stop_event.wait()
    finally:
        await queue.stop_worker()
        logger.info("Worker stopped")


def main():
    """Entry point."""
    setup_structured_logging(level=logging.INFO, json_output=True)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()

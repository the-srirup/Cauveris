"""
Cauveris Worker - Background job processor.

Subscribes to the shared job queue via JobQueue.register_handler() /
start_worker() and processes jobs as they are dequeued.

Run as a separate process:

    python -m cauveris.worker

The API process serves the queue itself by default (see
``start_embedded_worker``), so a separate worker is only needed when the
work should happen somewhere else - on a GPU box, on a robot's edge
computer, on another node in the cluster.  That needs a cross-process
backend (Redis / RabbitMQ): with the default in-memory backend, a job
submitted inside the API process is not visible to this process.
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
    """
    Process a simulation job.
    Accepts raw experiments or an incident_id in job.payload, runs the digital
    twin simulation using the calibrated physics model, and returns simulation results.
    """
    from cauveris.simulation.runner import SimulationRunner
    from cauveris.schemas.experiment import Experiment
    from cauveris.ingestion.controller import IngestionController
    from cauveris.hypothesis.generator import HypothesisGenerator
    from cauveris.sandbox.controller import SandboxController

    logger.info(f"Processing simulation job {job.id}")
    raw_experiments = job.payload.get("experiments")

    if raw_experiments:
        experiments = [
            Experiment.model_validate(e) if isinstance(e, dict) else e
            for e in raw_experiments
        ]
        runner = SimulationRunner()
        results = await runner.run_simulations(experiments)
        return {
            "status": "completed",
            "experiments": [e.model_dump() for e in results],
            "count": len(results),
        }

    incident_id = job.payload.get("incident_id")
    if not incident_id:
        raise ValueError("Job payload must contain 'experiments' or 'incident_id'")

    evidence_path = Path(get_settings().evidence_store_path) / incident_id
    if not evidence_path.exists():
        for pattern in (f"./incident-{incident_id}", f"./incident-{incident_id.lower()}"):
            pattern_path = Path(pattern)
            if pattern_path.exists():
                evidence_path = pattern_path
                break
    if not evidence_path.exists():
        raise ValueError(f"Incident {incident_id} not found at {evidence_path}")

    incident = await IngestionController().load_incident_from_store(incident_id, evidence_path)
    hypotheses = await HypothesisGenerator().generate(incident)
    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments(hypotheses)
    await sandbox.run_experiments(experiments)

    runner = SimulationRunner()
    results = await runner.run_simulations(experiments)
    return {
        "status": "completed",
        "incident_id": incident_id,
        "experiments": [e.model_dump() for e in results],
        "count": len(results),
    }


async def process_patch_job(job):
    """
    Process a patch generation and verification job.
    Accepts candidate patches, experiments, or an incident_id in job.payload.
    Runs patch generation and the 9-point invariant verification engine.
    """
    from cauveris.patch.generator import PatchGenerator
    from cauveris.verifier.engine import VerificationEngine
    from cauveris.schemas.experiment import Experiment
    from cauveris.schemas.patch import PatchCandidate
    from cauveris.ingestion.controller import IngestionController
    from cauveris.hypothesis.generator import HypothesisGenerator
    from cauveris.sandbox.controller import SandboxController
    from cauveris.simulation.runner import SimulationRunner

    logger.info(f"Processing patch job {job.id}")
    raw_patches = job.payload.get("patches")
    raw_experiments = job.payload.get("experiments")
    incident_id = job.payload.get("incident_id")

    incident = None
    if incident_id:
        evidence_path = Path(get_settings().evidence_store_path) / incident_id
        if not evidence_path.exists():
            for pattern in (f"./incident-{incident_id}", f"./incident-{incident_id.lower()}"):
                pattern_path = Path(pattern)
                if pattern_path.exists():
                    evidence_path = pattern_path
                    break
        if evidence_path.exists():
            try:
                incident = await IngestionController().load_incident_from_store(
                    incident_id, evidence_path
                )
            except Exception as exc:
                logger.warning(f"Could not load incident {incident_id}: {exc}")

    if raw_patches:
        patches = [
            PatchCandidate.model_validate(p) if isinstance(p, dict) else p
            for p in raw_patches
        ]
        verifier = VerificationEngine(incident=incident)
        reports = await verifier.verify(patches, incident=incident)
        return {
            "status": "completed",
            "patches": [p.model_dump() for p in patches],
            "reports": [r.model_dump() for r in reports],
        }

    if raw_experiments:
        experiments = [
            Experiment.model_validate(e) if isinstance(e, dict) else e
            for e in raw_experiments
        ]
    elif incident:
        hypotheses = await HypothesisGenerator().generate(incident)
        sandbox = SandboxController()
        planned = await sandbox.plan_experiments(hypotheses)
        await sandbox.run_experiments(planned)
        experiments = await SimulationRunner().run_simulations(planned)
    else:
        raise ValueError("Job payload must contain 'patches', 'experiments', or 'incident_id'")

    generator = PatchGenerator()
    patches = await generator.generate(experiments)
    verifier = VerificationEngine(incident=incident)
    reports = await verifier.verify(patches, incident=incident)
    return {
        "status": "completed",
        "patches": [p.model_dump() for p in patches],
        "reports": [r.model_dump() for r in reports],
    }


JOB_HANDLERS = {
    "pipeline": process_pipeline_job,
    "simulation": process_simulation_job,
    "patch_generation": process_patch_job,
}


async def start_embedded_worker(queue=None, types=None) -> bool:
    """
    Serve the job queue from inside this process.

    A queue that nobody serves fills up and never drains: jobs are accepted,
    they sit there, and the caller waits for a result that no one is going
    to produce.  The API process is the natural place to serve it - it
    already holds the evidence store, the incident registry and the report
    writer, and a single-process deployment (which is how Cauveris is
    usually run) has no other worker at all.

    The same handlers serve the queue here and in a standalone worker
    process, so a deployment can move from one to the other without the
    work changing.

    Returns:
        True when the worker loop is running.
    """
    queue = queue or get_job_queue()
    if queue is None:
        logger.error("Job queue not initialized; the embedded worker cannot start")
        return False

    for job_type, handler in JOB_HANDLERS.items():
        queue.register_handler(job_type, handler)

    settings = get_settings()
    concurrency = max(1, int(getattr(settings, "job_queue_worker_concurrency", 2) or 1))
    queue.set_concurrency(concurrency)

    await queue.start_worker(types or WORKER_TYPES)
    logger.info(
        f"Embedded worker {queue.worker_id} serving {types or WORKER_TYPES} "
        f"with concurrency {concurrency}"
    )
    return queue.is_running


async def run_worker():
    """Main worker loop — registers handlers and lets JobQueue drive processing."""
    queue = get_job_queue()
    if not queue:
        logger.error("Job queue not initialized")
        return

    # The same registration the embedded worker does, so a deployment can
    # move the work from this process into the API process without the
    # handlers changing.
    started = await start_embedded_worker(queue)
    if not started:
        logger.error("The worker could not be started")
        return

    logger.info("Starting Cauveris worker")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        loop.call_soon_threadsafe(stop_event.set)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

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

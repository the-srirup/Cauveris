"""
Tests for Phase 18: Require a Shared Production Queue.
Verifies production security validation refusing in-memory queue for external workers,
persistent SQLite queue backend, multi-worker concurrency, and lease-based dead worker recovery.
"""

import asyncio
import pytest

from cauveris.config import Settings
from cauveris.job_queue import (
    Job,
    JobPriority,
    JobStatus,
    SQLiteQueueBackend,
)


def test_production_security_refuses_in_memory_queue_for_external_workers():
    """In production runtime mode, in-memory queue must be refused if running external workers."""
    settings = Settings(
        runtime_mode="production",
        demo_auth=False,
        demo_mode=False,
        runtime_fixtures=False,
        autoload_sample=False,
        allow_explicit_samples=False,
        secret_key="a-genuine-production-secret-key-that-is-long-enough",
        job_queue_embedded_worker=False,
        job_queue_backend="memory",
    )

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate_production_security()

    assert "CAUVERIS_JOB_QUEUE_BACKEND cannot be 'memory'" in str(exc_info.value)
    assert "CAUVERIS_JOB_QUEUE_EMBEDDED_WORKER=false" in str(exc_info.value)


def test_production_security_accepts_persistent_shared_queue():
    """In production mode with external workers, persistent backends (sqlite/redis/rabbitmq) are accepted."""
    for backend in ("sqlite", "redis", "rabbitmq"):
        settings = Settings(
            runtime_mode="production",
            demo_auth=False,
            demo_mode=False,
            runtime_fixtures=False,
            autoload_sample=False,
            allow_explicit_samples=False,
            secret_key="a-genuine-production-secret-key-that-is-long-enough",
            job_queue_embedded_worker=False,
            job_queue_backend=backend,
        )
        # Should not raise for queue configuration
        settings.validate_production_security()


@pytest.mark.asyncio
async def test_sqlite_queue_persistence_and_restart(tmp_path):
    """Verify SQLite queue persists jobs across queue backend re-instantiation (server restart)."""
    db_file = tmp_path / "test_shared_queue.db"

    backend1 = SQLiteQueueBackend(db_path=str(db_file), max_size=100)
    job1 = Job(
        id="job-persistent-01",
        type="pipeline",
        payload={"incident_id": "INC-100"},
        priority=JobPriority.HIGH,
    )
    accepted = await backend1.enqueue(job1)
    assert accepted is True
    await backend1.close()

    # Simulate restart: open new backend instance pointing to same file
    backend2 = SQLiteQueueBackend(db_path=str(db_file), max_size=100)
    claimed = await backend2.dequeue(worker_id="worker-01", types=["pipeline"], max_jobs=1)
    assert len(claimed) == 1
    assert claimed[0].id == "job-persistent-01"
    assert claimed[0].payload["incident_id"] == "INC-100"

    # Mark complete
    res = await backend2.complete("job-persistent-01", {"status": "ok"})
    assert res is True

    # Verify state in DB
    completed_job = await backend2.get_job("job-persistent-01")
    assert completed_job is not None
    assert completed_job.status == JobStatus.COMPLETED
    assert completed_job.result == {"status": "ok"}
    await backend2.close()


@pytest.mark.asyncio
async def test_sqlite_queue_priority_ordering(tmp_path):
    """Verify jobs are dequeued strictly by priority: CRITICAL > HIGH > NORMAL > LOW."""
    db_file = tmp_path / "priority_queue.db"
    backend = SQLiteQueueBackend(db_path=str(db_file))

    j_low = Job(id="j-low", type="task", priority=JobPriority.LOW)
    j_norm = Job(id="j-norm", type="task", priority=JobPriority.NORMAL)
    j_crit = Job(id="j-crit", type="task", priority=JobPriority.CRITICAL)
    j_high = Job(id="j-high", type="task", priority=JobPriority.HIGH)

    # Enqueue in random order
    await backend.enqueue(j_low)
    await backend.enqueue(j_norm)
    await backend.enqueue(j_crit)
    await backend.enqueue(j_high)

    claimed = await backend.dequeue(worker_id="w1", types=["task"], max_jobs=4)
    assert len(claimed) == 4
    order = [j.id for j in claimed]
    assert order == ["j-crit", "j-high", "j-norm", "j-low"]
    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_queue_dead_worker_reclamation(tmp_path):
    """Verify that when a worker crashes or abandons a lease, the job is reclaimed."""
    db_file = tmp_path / "dead_worker_queue.db"
    # Set short claim timeout (0.2 seconds)
    backend = SQLiteQueueBackend(db_path=str(db_file), claim_timeout=0.2)

    job = Job(id="j-abandoned", type="sim", max_retries=2)
    await backend.enqueue(job)

    # Worker 1 claims job
    claimed = await backend.dequeue(worker_id="crashed-worker", types=["sim"], max_jobs=1)
    assert len(claimed) == 1
    assert claimed[0].id == "j-abandoned"

    # Sleep longer than claim timeout without completing
    await asyncio.sleep(0.3)

    # Worker 2 attempts dequeue -> triggers dead worker reclamation
    reclaimed = await backend.dequeue(worker_id="healthy-worker", types=["sim"], max_jobs=1)
    assert len(reclaimed) == 1
    assert reclaimed[0].id == "j-abandoned"
    assert reclaimed[0].retry_count == 1

    # Complete the job
    await backend.complete("j-abandoned", {"cleared": True})
    final_job = await backend.get_job("j-abandoned")
    assert final_job.status == JobStatus.COMPLETED
    await backend.close()


@pytest.mark.asyncio
async def test_sqlite_queue_max_size_backpressure(tmp_path):
    """Verify max_size rejects jobs when queue capacity is reached."""
    db_file = tmp_path / "backpressure_queue.db"
    backend = SQLiteQueueBackend(db_path=str(db_file), max_size=2)

    assert await backend.enqueue(Job(id="j1", type="t")) is True
    assert await backend.enqueue(Job(id="j2", type="t")) is True
    # Capacity reached -> should reject
    assert await backend.enqueue(Job(id="j3", type="t")) is False
    await backend.close()

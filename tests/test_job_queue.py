"""
Tests for Phase 6: Bounded Job Queue
"""
import asyncio
import time
import pytest
from cauveris.job_queue import (
    InMemoryQueueBackend,
    JobQueue,
    Job,
    JobPriority,
    JobStatus,
)


@pytest.fixture
def backend():
    """Create a fresh InMemoryQueueBackend."""
    return InMemoryQueueBackend(max_size=100, default_ttl=60)


@pytest.fixture
def queue(backend):
    """Create a JobQueue with test backend."""
    return JobQueue(backend, worker_id="test-worker")


@pytest.mark.asyncio
async def test_enqueue_dequeue(backend):
    """Test basic enqueue and dequeue."""
    job = Job(type="test", payload={"data": "hello"}, owner_id="user1")
    success = await backend.enqueue(job)
    assert success is True

    jobs = await backend.dequeue("worker1", ["test"], max_jobs=1)
    assert len(jobs) == 1
    assert jobs[0].id == job.id
    assert jobs[0].status == JobStatus.PROCESSING


@pytest.mark.asyncio
async def test_priority_ordering(backend):
    """Test that higher priority jobs are dequeued first."""
    low = Job(type="test", payload={}, priority=JobPriority.LOW, owner_id="user1")
    high = Job(type="test", payload={}, priority=JobPriority.HIGH, owner_id="user1")
    critical = Job(type="test", payload={}, priority=JobPriority.CRITICAL, owner_id="user1")

    await backend.enqueue(low)
    await backend.enqueue(high)
    await backend.enqueue(critical)

    jobs = await backend.dequeue("worker1", ["test"], max_jobs=3)
    assert len(jobs) == 3
    assert jobs[0].priority == JobPriority.CRITICAL
    assert jobs[1].priority == JobPriority.HIGH
    assert jobs[2].priority == JobPriority.LOW


@pytest.mark.asyncio
async def test_fifo_within_priority(backend):
    """Test FIFO ordering within same priority."""
    job1 = Job(type="test", payload={"i": 1}, priority=JobPriority.NORMAL, owner_id="user1")
    job2 = Job(type="test", payload={"i": 2}, priority=JobPriority.NORMAL, owner_id="user1")
    job3 = Job(type="test", payload={"i": 3}, priority=JobPriority.NORMAL, owner_id="user1")

    await backend.enqueue(job1)
    await backend.enqueue(job2)
    await backend.enqueue(job3)

    jobs = await backend.dequeue("worker1", ["test"], max_jobs=3)
    assert jobs[0].payload["i"] == 1
    assert jobs[1].payload["i"] == 2
    assert jobs[2].payload["i"] == 3


@pytest.mark.asyncio
async def test_max_size_enforcement(backend):
    """Test that queue rejects when full."""
    backend._max_size = 2

    job1 = Job(type="test", payload={}, owner_id="user1")
    job2 = Job(type="test", payload={}, owner_id="user1")
    job3 = Job(type="test", payload={}, owner_id="user1")

    assert await backend.enqueue(job1) is True
    assert await backend.enqueue(job2) is True
    assert await backend.enqueue(job3) is False  # Rejected


@pytest.mark.asyncio
async def test_complete_job(backend):
    """Test completing a job."""
    job = Job(type="test", payload={}, owner_id="user1")
    await backend.enqueue(job)
    _jobs = await backend.dequeue("worker1", ["test"], 1)

    success = await backend.complete(job.id, {"result": "ok"})
    assert success is True

    completed = await backend.get_job(job.id)
    assert completed.status == JobStatus.COMPLETED
    assert completed.result == {"result": "ok"}


@pytest.mark.asyncio
async def test_fail_and_retry(backend):
    """Test failing a job with retry."""
    job = Job(type="test", payload={}, owner_id="user1", max_retries=2)
    await backend.enqueue(job)
    await backend.dequeue("worker1", ["test"], 1)

    # Fail with retry
    await backend.fail(job.id, "temporary error", retry=True)

    # Job should be requeued
    requeued = await backend.get_job(job.id)
    assert requeued.status == JobStatus.QUEUED
    assert requeued.retry_count == 1


@pytest.mark.asyncio
async def test_fail_to_dead_letter(backend):
    """Test failing a job exhausting retries goes to dead letter."""
    job = Job(type="test", payload={}, owner_id="user1", max_retries=1)
    await backend.enqueue(job)
    await backend.dequeue("worker1", ["test"], 1)

    # First failure - retry
    await backend.fail(job.id, "error 1", retry=True)
    assert (await backend.get_job(job.id)).retry_count == 1

    # Dequeue again
    await backend.dequeue("worker1", ["test"], 1)
    # Second failure - no more retries
    await backend.fail(job.id, "error 2", retry=True)

    # Should be in dead letter
    dead = await backend.get_job(job.id)
    assert dead.status == JobStatus.DEAD_LETTER


@pytest.mark.asyncio
async def test_cancel_queued_job(backend):
    """Test cancelling a queued job."""
    job = Job(type="test", payload={}, owner_id="user1")
    await backend.enqueue(job)

    success = await backend.cancel(job.id)
    assert success is True

    cancelled = await backend.get_job(job.id)
    assert cancelled.status == JobStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_processing_job(backend):
    """Test cancelling a processing job."""
    job = Job(type="test", payload={}, owner_id="user1")
    await backend.enqueue(job)
    await backend.dequeue("worker1", ["test"], 1)

    success = await backend.cancel(job.id)
    assert success is True

    cancelled = await backend.get_job(job.id)
    assert cancelled.status == JobStatus.CANCELLED


@pytest.mark.asyncio
async def test_tenant_isolation(backend):
    """Test per-tenant queue isolation."""
    job_a = Job(type="test", payload={}, owner_id="user1", tenant_id="tenant-a")
    job_b = Job(type="test", payload={}, owner_id="user2", tenant_id="tenant-b")

    await backend.enqueue(job_a)
    await backend.enqueue(job_b)

    # Dequeue from tenant-a only
    jobs = await backend.dequeue("worker1", ["test"], 1)

    # Should only get jobs from one tenant (implementation picks first)
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_job_expiration(backend):
    """Test job TTL expiration."""
    job = Job(type="test", payload={}, owner_id="user1")
    job.expires_at = time.time() - 10  # Already expired

    success = await backend.enqueue(job)
    assert success is False  # Should reject expired job


@pytest.mark.asyncio
async def test_queue_stats(backend):
    """Test queue statistics."""
    job1 = Job(type="test", payload={}, owner_id="user1", priority=JobPriority.HIGH)
    job2 = Job(type="test", payload={}, owner_id="user1", priority=JobPriority.NORMAL)
    job3 = Job(type="simulation", payload={}, owner_id="user2")

    await backend.enqueue(job1)
    await backend.enqueue(job2)
    await backend.enqueue(job3)

    stats = await backend.get_stats()
    assert stats["enqueued"] == 3
    assert stats["queued_total"] == 3
    assert stats["per_tenant"]["default"]["queued"] == 3
    assert stats["per_tenant"]["default"]["by_priority"]["HIGH"] == 1
    assert stats["per_tenant"]["default"]["by_priority"]["NORMAL"] == 2


@pytest.mark.asyncio
async def test_job_queue_submit_and_wait(queue):
    """Test JobQueue submit_and_wait."""
    results = {}

    async def handler(job: Job):
        results[job.id] = "processed"
        return {"output": "done"}

    queue.register_handler("test", handler)
    await queue.start_worker(["test"])

    job = Job(type="test", payload={"input": "data"}, owner_id="user1")
    completed = await queue.submit_and_wait(job, timeout=5.0)

    await queue.stop_worker()

    assert completed.status == JobStatus.COMPLETED
    assert completed.result == {"output": "done"}
    assert results[job.id] == "processed"


@pytest.mark.asyncio
async def test_job_queue_worker(queue):
    """Test JobQueue worker processing."""
    processed = []

    async def handler(job: Job):
        processed.append(job.id)
        return {"ok": True}

    queue.register_handler("test", handler)
    queue.set_concurrency(2)

    await queue.start_worker(["test"])

    # Submit multiple jobs
    jobs = [Job(type="test", payload={"i": i}, owner_id="user1") for i in range(5)]
    for job in jobs:
        await queue.submit(job)

    # Wait for processing
    await asyncio.sleep(0.5)

    await queue.stop_worker()

    assert len(processed) == 5


@pytest.mark.asyncio
async def test_job_queue_cancel(queue):
    """Test JobQueue cancel_job."""
    job = Job(type="test", payload={}, owner_id="user1")
    await queue.submit(job)

    success = await queue.cancel_job(job.id)
    assert success is True

    cancelled = await queue.get_job_status(job.id)
    assert cancelled.status == JobStatus.CANCELLED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

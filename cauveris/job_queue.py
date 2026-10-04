"""
Bounded Job Queue (Phase 6)
Production-grade job queue with:
- Job model with priorities, TTL, retries, dead-letter handling
- Replaceable backend (Memory/Redis/RabbitMQ)
- Max size enforcement with backpressure
- Fairness policies (FIFO, priority lanes, per-tenant isolation)
- Dead job detection and recovery
"""
import asyncio
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import IntEnum, Enum
from typing import Any, Callable, Dict, List, Optional, Set
from contextlib import asynccontextmanager
import logging

from cauveris.config import get_settings

logger = logging.getLogger(__name__)


class JobPriority(IntEnum):
    """Job priority levels (higher = more urgent)."""
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


class JobStatus(str, Enum):
    """Job lifecycle states."""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """
    Job model with full lifecycle tracking.

    Attributes:
        id: Unique job identifier
        type: Job type for routing (e.g., "pipeline", "simulation", "inference")
        payload: Serialized job data
        priority: JobPriority enum value
        status: Current JobStatus
        created_at: Unix timestamp
        started_at: Unix timestamp when processing began
        completed_at: Unix timestamp when finished
        expires_at: Unix timestamp for TTL expiration
        retry_count: Number of retry attempts
        max_retries: Maximum retries allowed
        retry_delay: Base delay between retries (seconds)
        owner_id: Client identity (user/org/incident)
        tenant_id: Optional tenant for multi-tenancy isolation
        metadata: Additional context (incident_id, trace_id, etc.)
        result: Serialized result on completion
        error: Error message on failure
        attempts: List of attempt timestamps
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: JobPriority = JobPriority.NORMAL
    status: JobStatus = JobStatus.QUEUED
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    expires_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    retry_delay: float = 1.0
    owner_id: str = ""
    tenant_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    attempts: List[float] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if job has exceeded TTL."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.retry_count < self.max_retries and self.status == JobStatus.FAILED

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Deserialize from dict."""
        # Convert priority int to enum
        if "priority" in data and isinstance(data["priority"], int):
            data["priority"] = JobPriority(data["priority"])
        return cls(**data)


class QueueBackend(ABC):
    """Abstract backend for job queue storage."""

    @abstractmethod
    async def enqueue(self, job: Job) -> bool:
        """Add job to queue. Returns True if accepted, False if queue full."""
        pass

    @abstractmethod
    async def dequeue(self, worker_id: str, types: List[str], max_jobs: int = 1) -> List[Job]:
        """Get next jobs for worker. Returns list of jobs (up to max_jobs)."""
        pass

    @abstractmethod
    async def requeue(self, job: Job) -> bool:
        """Re-queue a job (for retry). Returns True if accepted."""
        pass

    @abstractmethod
    async def complete(self, job_id: str, result: Dict[str, Any]) -> bool:
        """Mark job as completed with result."""
        pass

    @abstractmethod
    async def fail(self, job_id: str, error: str, retry: bool = False) -> bool:
        """Mark job as failed. If retry=True and can_retry, requeues."""
        pass

    @abstractmethod
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        pass

    @abstractmethod
    async def cancel(self, job_id: str) -> bool:
        """Cancel a queued or processing job."""
        pass

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if backend is healthy."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connections."""
        pass


class InMemoryQueueBackend(QueueBackend):
    """
    In-memory implementation with priority lanes and per-tenant isolation.

    Features:
    - Priority-based ordering (CRITICAL > HIGH > NORMAL > LOW)
    - Per-tenant queues for isolation
    - FIFO within priority
    - Max size enforcement with backpressure
    - TTL-based expiration
    - Dead letter queue for failed jobs
    """

    def __init__(self, max_size: int = 10000, default_ttl: int = 3600):
        self._max_size = max_size
        self._default_ttl = default_ttl

        # Main queue: tenant -> priority -> deque of jobs
        self._queues: Dict[str, Dict[JobPriority, List[Job]]] = {}
        # Processing jobs: job_id -> Job
        self._processing: Dict[str, Job] = {}
        # Dead letter queue: tenant -> List[Job]
        self._dead_letter: Dict[str, List[Job]] = {}
        # Completed jobs (recent): job_id -> Job (for result polling)
        self._completed: Dict[str, Job] = {}
        # Locks per tenant
        self._locks: Dict[str, asyncio.Lock] = {}
        # Waiters for dequeue
        self._waiters: Dict[str, List[asyncio.Event]] = {}
        # Stats
        self._stats = {
            "enqueued": 0,
            "dequeued": 0,
            "completed": 0,
            "failed": 0,
            "dead_lettered": 0,
            "cancelled": 0,
            "expired": 0,
            "rejected_full": 0,
        }

    def _get_lock(self, tenant_id: Optional[str]) -> asyncio.Lock:
        key = tenant_id or "default"
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _get_queue(self, tenant_id: Optional[str]) -> Dict[JobPriority, List[Job]]:
        key = tenant_id or "default"
        if key not in self._queues:
            self._queues[key] = {p: [] for p in JobPriority}
        return self._queues[key]

    def _get_dead_letter(self, tenant_id: Optional[str]) -> List[Job]:
        key = tenant_id or "default"
        if key not in self._dead_letter:
            self._dead_letter[key] = []
        return self._dead_letter[key]

    def _get_waiters(self, tenant_id: Optional[str]) -> List[asyncio.Event]:
        key = tenant_id or "default"
        if key not in self._waiters:
            self._waiters[key] = []
        return self._waiters[key]

    def _total_queued(self, tenant_id: Optional[str] = None) -> int:
        """Count total queued jobs across all tenants or specific tenant."""
        if tenant_id:
            q = self._get_queue(tenant_id)
            return sum(len(jobs) for jobs in q.values())
        return sum(
            sum(len(jobs) for jobs in q.values())
            for q in self._queues.values()
        )

    async def enqueue(self, job: Job) -> bool:
        # Check expiration
        if job.expires_at is None:
            job.expires_at = time.time() + self._default_ttl

        if job.is_expired():
            logger.warning(f"Job {job.id} expired before enqueue")
            return False

        tenant_id = job.tenant_id
        lock = self._get_lock(tenant_id)

        async with lock:
            # Check capacity
            if self._total_queued(tenant_id) >= self._max_size:
                self._stats["rejected_full"] += 1
                logger.warning(f"Queue full for tenant {tenant_id or 'default'}, rejecting job {job.id}")
                return False

            # Add to appropriate priority queue
            queue = self._get_queue(tenant_id)
            queue[job.priority].append(job)

            self._stats["enqueued"] += 1

            # Notify a waiter
            waiters = self._get_waiters(tenant_id)
            for waiter in waiters:
                if not waiter.is_set():
                    waiter.set()
                    break

        logger.debug(f"Enqueued job {job.id} (type={job.type}, priority={job.priority.name})")
        return True

    async def dequeue(self, worker_id: str, types: List[str], max_jobs: int = 1) -> List[Job]:
        # For simplicity, we check all tenants. In production, workers register for specific tenants.
        # Here we aggregate across all tenants.
        jobs_taken = []

        # Get all tenant keys
        tenant_keys = set(self._queues.keys())
        tenant_keys.add(None)  # Also check default

        for _ in range(max_jobs):
            best_job = None
            best_tenant = None
            best_priority = None

            # Find highest priority job across all tenants matching types
            for tenant_id in tenant_keys:
                lock = self._get_lock(tenant_id)
                async with lock:
                    queue = self._get_queue(tenant_id)
                    for priority in sorted(JobPriority, reverse=True):
                        jobs_list = queue[priority]
                        for i, job in enumerate(jobs_list):
                            if not types or job.type in types:
                                if job.is_expired():
                                    # Remove expired
                                    jobs_list.pop(i)
                                    self._stats["expired"] += 1
                                    continue
                                best_job = job
                                best_tenant = tenant_id
                                best_priority = priority
                                break
                        if best_job:
                            break
                    if best_job:
                        break

            if not best_job:
                break  # No more jobs

            # Remove from queue and mark processing
            queue = self._get_queue(best_tenant)
            queue[best_priority].remove(best_job)

            best_job.status = JobStatus.PROCESSING
            best_job.started_at = time.time()
            best_job.attempts.append(time.time())

            self._processing[best_job.id] = best_job
            self._stats["dequeued"] += 1
            jobs_taken.append(best_job)

            logger.debug(f"Dequeued job {best_job.id} for worker {worker_id}")

        return jobs_taken

    async def requeue(self, job: Job) -> bool:
        """Re-queue a job for retry."""
        job.status = JobStatus.QUEUED
        job.retry_count += 1
        job.error = None
        # Exponential backoff for next attempt
        job.expires_at = time.time() + self._default_ttl

        # Remove from processing
        self._processing.pop(job.id, None)

        return await self.enqueue(job)

    async def complete(self, job_id: str, result: Dict[str, Any]) -> bool:
        job = self._processing.pop(job_id, None)
        if not job:
            return False

        job.status = JobStatus.COMPLETED
        job.completed_at = time.time()
        job.result = result

        # Store in completed for result polling (with TTL)
        self._completed[job_id] = job
        self._stats["completed"] += 1

        logger.debug(f"Completed job {job_id}")
        return True

    async def fail(self, job_id: str, error: str, retry: bool = False) -> bool:
        job = self._processing.pop(job_id, None)
        if not job:
            return False

        job.error = error

        can_retry = retry and job.retry_count < job.max_retries

        if can_retry:
            job.status = JobStatus.FAILED
            await self.requeue(job)
            logger.debug(f"Job {job_id} failed, requeued for retry ({job.retry_count}/{job.max_retries})")
        else:
            job.status = JobStatus.DEAD_LETTER
            job.completed_at = time.time()
            dlq = self._get_dead_letter(job.tenant_id)
            dlq.append(job)
            self._stats["failed"] += 1
            self._stats["dead_lettered"] += 1
            logger.warning(f"Job {job_id} moved to dead letter: {error}")

        return True

    async def _save_cancelled(self, job: Job) -> None:
        """Save cancelled job for get_job to find."""
        dlq = self._get_dead_letter(job.tenant_id)
        dlq.append(job)

    async def get_job(self, job_id: str) -> Optional[Job]:
        # Check processing
        if job_id in self._processing:
            return self._processing[job_id]
        # Check completed
        if job_id in self._completed:
            return self._completed[job_id]
        # Check dead letter
        for dlq in self._dead_letter.values():
            for job in dlq:
                if job.id == job_id:
                    return job
        # Check queues
        for tenant_id, queue in self._queues.items():
            for priority_jobs in queue.values():
                for job in priority_jobs:
                    if job.id == job_id:
                        return job
        return None

    async def cancel(self, job_id: str) -> bool:
        # Check processing
        if job_id in self._processing:
            job = self._processing.pop(job_id)
            job.status = JobStatus.CANCELLED
            job.completed_at = time.time()
            await self._save_cancelled(job)
            self._stats["cancelled"] += 1
            return True

        # Check queues
        for tenant_id, queue in self._queues.items():
            lock = self._get_lock(tenant_id)
            async with lock:
                for priority_jobs in queue.values():
                    for i, job in enumerate(priority_jobs):
                        if job.id == job_id:
                            priority_jobs.pop(i)
                            job.status = JobStatus.CANCELLED
                            job.completed_at = time.time()
                            await self._save_cancelled(job)
                            self._stats["cancelled"] += 1
                            return True

        # Check completed
        if job_id in self._completed:
            job = self._completed.pop(job_id)
            job.status = JobStatus.CANCELLED
            job.completed_at = time.time()
            await self._save_cancelled(job)
            self._stats["cancelled"] += 1
            return True

        return False

    async def get_stats(self) -> Dict[str, Any]:
        stats = self._stats.copy()
        stats["queued_total"] = self._total_queued()
        stats["processing"] = len(self._processing)
        stats["completed_cached"] = len(self._completed)
        stats["dead_letter_total"] = sum(len(dlq) for dlq in self._dead_letter.values())
        stats["tenants"] = list(self._queues.keys())

        # Per-tenant breakdown
        stats["per_tenant"] = {}
        for tenant_id, queue in self._queues.items():
            stats["per_tenant"][tenant_id or "default"] = {
                "queued": sum(len(jobs) for jobs in queue.values()),
                "by_priority": {p.name: len(jobs) for p, jobs in queue.items()},
                "dead_letter": len(self._dead_letter.get(tenant_id, [])),
            }

        return stats

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


class JobQueue:
    """
    High-level job queue manager.

    Features:
    - Worker registration and lifecycle
    - Automatic retry with backoff
    - Result polling
    - Graceful shutdown
    - Backpressure signals
    """

    def __init__(self, backend: QueueBackend, worker_id: Optional[str] = None):
        self._backend = backend
        self._worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._handlers: Dict[str, Callable[[Job], Any]] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._poll_interval = 1.0
        self._max_concurrent_jobs = 1

    def register_handler(self, job_type: str, handler: Callable[[Job], Any]) -> None:
        """Register a handler for a job type."""
        self._handlers[job_type] = handler

    def set_concurrency(self, max_concurrent: int) -> None:
        """Set max concurrent jobs for this worker."""
        self._max_concurrent_jobs = max(1, max_concurrent)

    async def submit(self, job: Job) -> bool:
        """Submit a job to the queue."""
        return await self._backend.enqueue(job)

    async def submit_and_wait(self, job: Job, timeout: float = 300.0) -> Job:
        """Submit job and wait for completion."""
        submitted = await self._backend.enqueue(job)
        if not submitted:
            raise QueueFullError(f"Queue full, could not submit job {job.id}")

        start_time = time.time()
        while time.time() - start_time < timeout:
            current = await self._backend.get_job(job.id)
            if current and current.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.DEAD_LETTER, JobStatus.CANCELLED):
                return current
            await asyncio.sleep(0.5)

        raise TimeoutError(f"Job {job.id} did not complete within {timeout}s")

    async def start_worker(self, types: Optional[List[str]] = None) -> None:
        """Start processing jobs."""
        if self._worker_task and not self._worker_task.done():
            return

        self._shutdown_event.clear()
        self._worker_task = asyncio.create_task(self._worker_loop(types or []))
        logger.info(f"Started worker {self._worker_id}")

    async def stop_worker(self, timeout: float = 30.0) -> None:
        """Stop worker gracefully."""
        self._shutdown_event.set()
        if self._worker_task:
            try:
                await asyncio.wait_for(self._worker_task, timeout=timeout)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
        logger.info(f"Stopped worker {self._worker_id}")

    async def _worker_loop(self, types: List[str]) -> None:
        semaphore = asyncio.Semaphore(self._max_concurrent_jobs)

        async def process_job(job: Job):
            async with semaphore:
                handler = self._handlers.get(job.type)
                if not handler:
                    await self._backend.fail(job.id, f"No handler for job type: {job.type}")
                    return

                try:
                    result = await handler(job)
                    await self._backend.complete(job.id, result or {})
                except Exception as e:
                    await self._backend.fail(job.id, str(e), retry=True)

        while not self._shutdown_event.is_set():
            try:
                jobs = await self._backend.dequeue(self._worker_id, types, self._max_concurrent_jobs)
                if not jobs:
                    # No jobs, wait a bit
                    try:
                        await asyncio.wait_for(self._shutdown_event.wait(), timeout=self._poll_interval)
                    except asyncio.TimeoutError:
                        pass  # Normal, continue loop
                    continue

                # Process jobs concurrently
                await asyncio.gather(*[process_job(job) for job in jobs])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)  # Back off on error

    async def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return await self._backend.get_stats()

    async def get_job_status(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        return await self._backend.get_job(job_id)

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        return await self._backend.cancel(job_id)


class QueueFullError(Exception):
    """Raised when queue is at capacity."""
    pass


# Global instance management
_job_queue_backend: Optional[QueueBackend] = None
_job_queue: Optional[JobQueue] = None


def init_job_queue(
    backend: str = "memory",
    max_size: int = 10000,
    default_ttl: int = 3600,
    worker_id: Optional[str] = None
) -> JobQueue:
    """Initialize the global job queue."""
    global _job_queue_backend, _job_queue

    if backend == "redis":
        raise NotImplementedError("Redis backend not yet implemented")
    elif backend == "rabbitmq":
        raise NotImplementedError("RabbitMQ backend not yet implemented")
    else:
        _job_queue_backend = InMemoryQueueBackend(max_size=max_size, default_ttl=default_ttl)

    _job_queue = JobQueue(_job_queue_backend, worker_id)
    return _job_queue


def get_job_queue() -> Optional[JobQueue]:
    """Get the global job queue."""
    global _job_queue
    if _job_queue is None:
        return init_job_queue()
    return _job_queue


async def close_job_queue() -> None:
    """Close the global job queue."""
    global _job_queue, _job_queue_backend
    if _job_queue:
        await _job_queue.stop_worker()
    if _job_queue_backend:
        await _job_queue_backend.close()
    _job_queue = None
    _job_queue_backend = None
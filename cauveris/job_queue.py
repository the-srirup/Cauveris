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
import inspect
import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import IntEnum, Enum
from typing import Any, Callable, Dict, List, Optional
import logging


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
        """Check if job can be retried.

        Mirrors the condition the queue backend uses when a job fails: there
        must be retry budget left and the job must not have reached a
        terminal state. The previous implementation required the status to be
        ``FAILED``, but the backend never leaves a job in that state - it
        either re-queues it (``QUEUED``) or moves it to the dead letter
        queue (``DEAD_LETTER``) - so ``can_retry()`` was always ``False``.
        """
        if self.retry_count >= self.max_retries:
            return False
        return self.status not in (
            JobStatus.COMPLETED,
            JobStatus.CANCELLED,
            JobStatus.DEAD_LETTER,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        """Deserialize from dict."""
        data = dict(data)
        # Convert priority to enum: it may arrive as an int, as an int-like
        # enum member or as its name.
        if "priority" in data and data["priority"] is not None:
            raw_priority = data["priority"]
            if isinstance(raw_priority, JobPriority):
                pass
            elif isinstance(raw_priority, bool):
                raise ValueError("bool is not a valid job priority")
            elif isinstance(raw_priority, int):
                data["priority"] = JobPriority(raw_priority)
            elif isinstance(raw_priority, str):
                candidate = raw_priority.strip().upper()
                data["priority"] = (
                    JobPriority(int(candidate))
                    if candidate.isdigit()
                    else JobPriority[candidate]
                )
            else:
                raise ValueError(f"unsupported job priority: {raw_priority!r}")
        # Convert status to enum for the same reason.
        if "status" in data and data["status"] is not None:
            raw_status = data["status"]
            if not isinstance(raw_status, JobStatus):
                data["status"] = JobStatus(raw_status)
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
        return sum(sum(len(jobs) for jobs in q.values()) for q in self._queues.values())

    async def enqueue(self, job: Job) -> bool:
        # Check expiration
        if job.expires_at is None:
            job.expires_at = time.time() + self._default_ttl

        if job.is_expired():
            logger.warning(f"Job {job.id} expired before enqueue")
            return False

        # Normalise the priority: an unknown value would raise a KeyError when
        # indexing the priority lane.
        try:
            job.priority = JobPriority(job.priority)
        except (ValueError, TypeError):
            logger.warning(f"Job {job.id} has an invalid priority, defaulting to NORMAL")
            job.priority = JobPriority.NORMAL

        tenant_id = job.tenant_id
        lock = self._get_lock(tenant_id)

        async with lock:
            # Check capacity
            if self._total_queued(tenant_id) >= self._max_size:
                self._stats["rejected_full"] += 1
                logger.warning(
                    f"Queue full for tenant {tenant_id or 'default'}, rejecting job {job.id}"
                )
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
            best_priority = None

            # Find highest priority job across all tenants matching types.
            #
            # The removal from the queue happens *inside* the tenant lock: the
            # previous implementation released the lock between the scan and
            # the removal, so two concurrent workers could pick the same job.
            for tenant_id in tenant_keys:
                lock = self._get_lock(tenant_id)
                async with lock:
                    queue = self._get_queue(tenant_id)
                    for priority in sorted(JobPriority, reverse=True):
                        jobs_list = queue[priority]
                        # Purge expired jobs first. This must happen for every
                        # job in the lane - not just the ones matching
                        # ``types`` - otherwise jobs whose type no worker
                        # handles would occupy queue capacity forever.
                        # The index is *not* advanced after a removal: the
                        # element that shifted into the vacated slot still has
                        # to be inspected (the previous implementation skipped
                        # it, letting expired jobs and even live jobs be
                        # silently ignored).
                        i = 0
                        while i < len(jobs_list):
                            job = jobs_list[i]
                            if job.is_expired():
                                jobs_list.pop(i)
                                self._stats["expired"] += 1
                                continue
                            i += 1

                        for job in jobs_list:
                            if not types or job.type in types:
                                best_job = job
                                best_priority = priority
                                break
                        if best_job:
                            break
                    if best_job:
                        # Claim the job while still holding the tenant lock.
                        queue[best_priority].remove(best_job)
                        break

            if not best_job:
                break  # No more jobs

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
        self._prune_completed()

        logger.debug(f"Completed job {job_id}")
        return True

    def _prune_completed(self) -> None:
        """
        Drop completed jobs that are past their TTL.

        Without this the ``_completed`` cache grows without bound, leaking the
        memory of every job the queue has ever finished.
        """
        if not self._completed:
            return
        now = time.time()
        stale = [
            job_id
            for job_id, job in self._completed.items()
            if job.expires_at is not None and job.expires_at < now
        ]
        for job_id in stale:
            self._completed.pop(job_id, None)

    async def fail(self, job_id: str, error: str, retry: bool = False) -> bool:
        job = self._processing.pop(job_id, None)
        if not job:
            return False

        job.error = error

        can_retry = retry and job.retry_count < job.max_retries

        if can_retry:
            # NOTE: the status is deliberately *not* set to FAILED here. The
            # job is re-queued immediately afterwards (which sets it to
            # QUEUED) and an await happens in between, so a poller could
            # otherwise observe the transient FAILED status and give up on a
            # job that is about to be retried.
            requeued = await self.requeue(job)
            if requeued:
                logger.debug(
                    f"Job {job_id} failed, requeued for retry "
                    f"({job.retry_count}/{job.max_retries})"
                )
            else:
                # The retry could not be queued (queue full, job expired).
                # The job has already been removed from the processing set, so
                # without this fallback it would be lost entirely.
                logger.warning(
                    f"Job {job_id} could not be requeued, moving to dead letter: {error}"
                )
                job.status = JobStatus.DEAD_LETTER
                job.completed_at = time.time()
                dlq = self._get_dead_letter(job.tenant_id)
                dlq.append(job)
                self._stats["failed"] += 1
                self._stats["dead_lettered"] += 1
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


class RedisQueueBackend(QueueBackend):
    """
    Redis-backed job queue for distributed workers.

    Features:
    - Priority-based scheduling via Redis Sorted Sets (ZSET)
    - Per-tenant isolation and FIFO ordering within priority lanes
    - Job metadata and payload persistence with TTL
    - Distributed worker claim and processing tracking
    - Dead letter queue for unrecoverable errors
    - Health checks and queue statistics
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "cauveris:jq:",
        max_size: int = 10000,
        default_ttl: int = 3600,
        redis_client: Optional[Any] = None,
        claim_timeout: Optional[float] = None,
    ):
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._redis = redis_client
        self._healthy = False
        if claim_timeout is None:
            from cauveris.config import get_settings

            claim_timeout = getattr(
                get_settings(), "job_queue_claim_timeout_seconds", 300.0
            )
        self._claim_timeout = float(claim_timeout)
        self._stats = {
            "enqueued": 0,
            "dequeued": 0,
            "completed": 0,
            "failed": 0,
            "dead_lettered": 0,
            "cancelled": 0,
            "expired": 0,
            "rejected_full": 0,
            "reclaimed": 0,
        }

    async def _ensure_connection(self) -> bool:
        if self._redis is not None:
            try:
                await self._redis.ping()
                self._healthy = True
                return True
            except Exception as exc:
                logger.warning(f"Redis ping failed: {exc}")
                self._healthy = False
                return False

        try:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
            await self._redis.ping()
            self._healthy = True
            return True
        except ImportError:
            logger.error("redis package is required for RedisQueueBackend")
            self._healthy = False
            return False
        except Exception as exc:
            logger.warning(f"Could not connect to Redis at {self._redis_url}: {exc}")
            self._healthy = False
            return False

    async def _total_queued(self) -> int:
        if not self._redis:
            return 0
        active_queues_key = f"{self._key_prefix}active_queues"
        active_queues = await self._redis.smembers(active_queues_key)
        total = 0
        for qk in active_queues:
            total += await self._redis.zcard(qk)
        return total

    async def enqueue(self, job: Job) -> bool:
        if not await self._ensure_connection():
            logger.error("RedisQueueBackend: Redis connection unavailable")
            return False

        if job.expires_at is None:
            job.expires_at = time.time() + self._default_ttl

        if job.is_expired():
            logger.warning(f"Job {job.id} expired before enqueue")
            self._stats["expired"] += 1
            return False

        try:
            job.priority = JobPriority(job.priority)
        except (ValueError, TypeError):
            job.priority = JobPriority.NORMAL

        tenant_id = job.tenant_id or "default"
        job_type = job.type or "generic"

        total_queued = await self._total_queued()
        if total_queued >= self._max_size:
            self._stats["rejected_full"] += 1
            logger.warning(
                f"Redis queue full ({total_queued} >= {self._max_size}), rejecting job {job.id}"
            )
            return False

        job_key = f"{self._key_prefix}job:{job.id}"
        ttl_seconds = max(1, int(job.expires_at - time.time()))
        await self._redis.set(job_key, json.dumps(job.to_dict()), ex=ttl_seconds)

        score = (int(job.priority.value) * 1_000_000_000_000) - int(job.created_at * 1000)
        queue_key = f"{self._key_prefix}queue:{tenant_id}:{job_type}"
        active_queues_key = f"{self._key_prefix}active_queues"

        await self._redis.zadd(queue_key, {job.id: score})
        await self._redis.sadd(active_queues_key, queue_key)
        self._stats["enqueued"] += 1
        return True

    async def dequeue(self, worker_id: str, types: List[str], max_jobs: int = 1) -> List[Job]:
        if not await self._ensure_connection():
            return []

        # Before handing out new work, take back the work that a worker took
        # and never finished.  A dead worker must not take the job with it.
        await self._reclaim_stalled_jobs()

        jobs_taken: List[Job] = []
        active_queues_key = f"{self._key_prefix}active_queues"
        active_queues = await self._redis.smembers(active_queues_key)

        for _ in range(max_jobs):
            best_job: Optional[Job] = None
            best_queue_key: Optional[str] = None
            highest_score = -float("inf")

            target_queues = []
            for qk in active_queues:
                parts = qk.split(":")
                q_type = parts[-1] if len(parts) >= 4 else ""
                if not types or q_type in types or not q_type:
                    target_queues.append(qk)

            for qk in target_queues:
                top_items = await self._redis.zrevrange(qk, 0, 0, withscores=True)
                if top_items:
                    cand_id, cand_score = top_items[0]
                    if cand_score > highest_score:
                        cand_job = await self.get_job(cand_id)
                        if cand_job is None or cand_job.is_expired():
                            await self._redis.zrem(qk, cand_id)
                            if cand_job and cand_job.is_expired():
                                self._stats["expired"] += 1
                            continue
                        highest_score = cand_score
                        best_job = cand_job
                        best_queue_key = qk

            if not best_job or not best_queue_key:
                break

            removed = await self._redis.zrem(best_queue_key, best_job.id)
            if not removed:
                continue

            best_job.status = JobStatus.PROCESSING
            best_job.started_at = time.time()
            best_job.attempts.append(time.time())

            job_key = f"{self._key_prefix}job:{best_job.id}"
            # The record has to outlive the work itself: a job that is being
            # processed may run for longer than the queue's own TTL, and a
            # record that expires mid-flight would lose the result.
            ttl_seconds = max(
                1,
                int(
                    max(
                        (best_job.expires_at or (time.time() + self._default_ttl))
                        - time.time(),
                        self._claim_timeout * 2,
                    )
                ),
            )
            await self._redis.set(job_key, json.dumps(best_job.to_dict()), ex=ttl_seconds)

            processing_key = f"{self._key_prefix}processing"
            await self._redis.hset(processing_key, best_job.id, worker_id)
            # The claim carries the time it was taken, so that a worker that
            # dies mid-job can be detected and its job handed back.
            await self._redis.hset(
                self._claimed_key(), best_job.id, str(time.time())
            )

            self._stats["dequeued"] += 1
            jobs_taken.append(best_job)

        return jobs_taken

    def _claimed_key(self) -> str:
        """The hash holding the time each in-flight job was claimed."""
        return f"{self._key_prefix}processing_claimed"

    async def _reclaim_stalled_jobs(self) -> int:
        """
        Hand back the jobs whose worker stopped making progress.

        A job is removed from the queue when it is claimed and is only
        deleted from the processing set when it completes, fails or is
        cancelled.  A worker that is killed - a deploy, an OOM kill, a yanked
        power lead - leaves the claim behind and the job with it: nobody is
        left to finish work that has no worker attached.

        So the claim carries the time it was taken.  A claim older than the
        claim timeout belongs to a worker that is not coming back, and the
        job goes back on the queue with its retry counter advanced.  A job
        that has used up its retries goes to the dead letter queue instead,
        because a job that fails this badly is a bug report, not work.

        Returns the number of jobs handed back to the queue.
        """
        if not self._redis:
            return 0
        try:
            claims = await self._redis.hgetall(self._claimed_key())
        except Exception as exc:
            logger.warning(f"Could not read the claim ledger: {exc}")
            return 0
        if not claims:
            return 0

        now = time.time()
        reclaimed = 0
        for job_id, stamp in claims.items():
            try:
                age = now - float(stamp)
            except (TypeError, ValueError):
                age = 0.0
            if age < self._claim_timeout:
                continue

            processing_key = f"{self._key_prefix}processing"
            await self._redis.hdel(processing_key, job_id)
            await self._redis.hdel(self._claimed_key(), job_id)

            job = await self.get_job(job_id)
            if job is None:
                # The job record expired; there is nothing left to recover.
                self._stats["expired"] += 1
                continue
            if job.status in (
                JobStatus.COMPLETED,
                JobStatus.CANCELLED,
                JobStatus.DEAD_LETTER,
            ):
                continue
            if job.is_expired():
                self._stats["expired"] += 1
                continue

            job.error = "the worker holding this job stopped responding"
            job.started_at = None
            if job.retry_count >= job.max_retries:
                job.status = JobStatus.DEAD_LETTER
                job.completed_at = now
                job_key = f"{self._key_prefix}job:{job.id}"
                await self._redis.set(
                    job_key, json.dumps(job.to_dict()), ex=self._default_ttl * 2
                )
                dlq_key = f"{self._key_prefix}dead_letter:{job.tenant_id or 'default'}"
                await self._redis.rpush(dlq_key, job.id)
                self._stats["failed"] += 1
                self._stats["dead_lettered"] += 1
                logger.warning(
                    f"Job {job.id} was abandoned by its worker too often; "
                    f"moving to dead letter"
                )
                continue

            job.retry_count += 1
            job.status = JobStatus.QUEUED
            job.expires_at = time.time() + self._default_ttl
            if await self.enqueue(job):
                reclaimed += 1
                self._stats["reclaimed"] += 1
                logger.warning(
                    f"Reclaimed abandoned job {job.id} "
                    f"(attempt {job.retry_count}/{job.max_retries})"
                )
        return reclaimed

    async def requeue(self, job: Job) -> bool:
        if not await self._ensure_connection():
            return False
        job.status = JobStatus.QUEUED
        job.retry_count += 1
        job.error = None
        job.expires_at = time.time() + self._default_ttl

        processing_key = f"{self._key_prefix}processing"
        await self._redis.hdel(processing_key, job.id)
        await self._redis.hdel(self._claimed_key(), job.id)
        return await self.enqueue(job)

    async def complete(self, job_id: str, result: Dict[str, Any]) -> bool:
        if not await self._ensure_connection():
            return False

        processing_key = f"{self._key_prefix}processing"
        await self._redis.hdel(processing_key, job_id)
        await self._redis.hdel(self._claimed_key(), job_id)

        job = await self.get_job(job_id)
        if not job:
            return False

        job.status = JobStatus.COMPLETED
        job.completed_at = time.time()
        job.result = result

        job_key = f"{self._key_prefix}job:{job_id}"
        await self._redis.set(job_key, json.dumps(job.to_dict()), ex=self._default_ttl)

        completed_key = f"{self._key_prefix}completed"
        await self._redis.sadd(completed_key, job_id)

        self._stats["completed"] += 1
        return True

    async def fail(self, job_id: str, error: str, retry: bool = False) -> bool:
        if not await self._ensure_connection():
            return False

        processing_key = f"{self._key_prefix}processing"
        await self._redis.hdel(processing_key, job_id)
        await self._redis.hdel(self._claimed_key(), job_id)

        job = await self.get_job(job_id)
        if not job:
            return False

        job.error = error
        can_retry = retry and job.retry_count < job.max_retries

        if can_retry:
            requeued = await self.requeue(job)
            if requeued:
                return True

        job.status = JobStatus.DEAD_LETTER
        job.completed_at = time.time()

        job_key = f"{self._key_prefix}job:{job_id}"
        await self._redis.set(job_key, json.dumps(job.to_dict()), ex=self._default_ttl * 2)

        dlq_key = f"{self._key_prefix}dead_letter:{job.tenant_id or 'default'}"
        await self._redis.rpush(dlq_key, job.id)

        self._stats["failed"] += 1
        self._stats["dead_lettered"] += 1
        return True

    async def get_job(self, job_id: str) -> Optional[Job]:
        if not await self._ensure_connection():
            return None
        job_key = f"{self._key_prefix}job:{job_id}"
        data = await self._redis.get(job_key)
        if not data:
            return None
        try:
            return Job.from_dict(json.loads(data))
        except Exception as exc:
            logger.error(f"Error parsing job {job_id} from Redis: {exc}")
            return None

    async def cancel(self, job_id: str) -> bool:
        if not await self._ensure_connection():
            return False

        job = await self.get_job(job_id)
        if not job:
            return False

        processing_key = f"{self._key_prefix}processing"
        await self._redis.hdel(processing_key, job_id)
        await self._redis.hdel(self._claimed_key(), job_id)

        active_queues_key = f"{self._key_prefix}active_queues"
        active_queues = await self._redis.smembers(active_queues_key)
        for qk in active_queues:
            await self._redis.zrem(qk, job_id)

        job.status = JobStatus.CANCELLED
        job.completed_at = time.time()
        job_key = f"{self._key_prefix}job:{job_id}"
        await self._redis.set(job_key, json.dumps(job.to_dict()), ex=self._default_ttl)

        dlq_key = f"{self._key_prefix}dead_letter:{job.tenant_id or 'default'}"
        await self._redis.rpush(dlq_key, job.id)

        self._stats["cancelled"] += 1
        return True

    async def get_stats(self) -> Dict[str, Any]:
        stats = self._stats.copy()
        if not await self._ensure_connection():
            return stats

        stats["queued_total"] = await self._total_queued()
        processing_key = f"{self._key_prefix}processing"
        stats["processing"] = await self._redis.hlen(processing_key)

        completed_key = f"{self._key_prefix}completed"
        stats["completed_cached"] = await self._redis.scard(completed_key)

        active_queues_key = f"{self._key_prefix}active_queues"
        active_queues = await self._redis.smembers(active_queues_key)
        tenants = set()
        per_tenant = {}

        for qk in active_queues:
            parts = qk.split(":")
            tenant = parts[-2] if len(parts) >= 4 else "default"
            tenants.add(tenant)
            count = await self._redis.zcard(qk)
            if tenant not in per_tenant:
                dlq_key = f"{self._key_prefix}dead_letter:{tenant}"
                dlq_len = await self._redis.llen(dlq_key)
                per_tenant[tenant] = {"queued": 0, "dead_letter": dlq_len}
            per_tenant[tenant]["queued"] += count

        stats["tenants"] = list(tenants)
        stats["per_tenant"] = per_tenant
        stats["dead_letter_total"] = sum(t["dead_letter"] for t in per_tenant.values())
        return stats

    async def health_check(self) -> bool:
        return await self._ensure_connection()

    async def close(self) -> None:
        if self._redis:
            try:
                # redis-py 5+ prefers aclose(); close() is deprecated there.
                closer = getattr(self._redis, "aclose", None) or self._redis.close
                result = closer()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                pass
        self._healthy = False


class RabbitMQQueueBackend(QueueBackend):
    """
    Production RabbitMQ-backed job queue via aio-pika (AMQP 0-9-1).

    Features:
    - Topic exchange routing with persistent messages
    - Priority queue support via x-max-priority
    - Dead letter exchange (DLX) for unhandled / failed jobs
    - In-flight message tracking, manual ack / reject semantics
    - Metadata and job lifecycle caching
    """

    def __init__(
        self,
        amqp_url: str = "amqp://guest:guest@localhost:5672/",
        exchange_name: str = "cauveris.jobs",
        max_size: int = 10000,
        default_ttl: int = 3600,
        channel: Optional[Any] = None,
        connection: Optional[Any] = None,
    ):
        self._amqp_url = amqp_url
        self._exchange_name = exchange_name
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._connection = connection
        self._channel = channel
        self._exchange = None
        self._dlx = None
        self._healthy = False
        self._jobs: Dict[str, Job] = {}
        self._pending_messages: Dict[str, Any] = {}
        self._processing: Dict[str, Job] = {}
        self._dead_letter: Dict[str, List[Job]] = {}
        self._completed: Dict[str, Job] = {}
        self._declared_queues: Dict[str, Any] = {}
        self._declared_dlqs: Dict[str, Any] = {}
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

    async def _ensure_connection(self) -> bool:
        if self._connection is not None and not getattr(self._connection, "is_closed", False):
            self._healthy = True
            return True

        try:
            import aio_pika

            self._connection = await aio_pika.connect_robust(
                self._amqp_url,
                timeout=5.0,
            )
            self._channel = await self._connection.channel()
            self._exchange = await self._channel.declare_exchange(
                self._exchange_name,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            self._dlx = await self._channel.declare_exchange(
                f"{self._exchange_name}.dlx",
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            self._healthy = True
            return True
        except ImportError:
            logger.error("aio-pika package is required for RabbitMQQueueBackend")
            self._healthy = False
            return False
        except Exception as exc:
            logger.warning(f"Could not connect to RabbitMQ at {self._amqp_url}: {exc}")
            self._healthy = False
            return False

    async def _get_queue_for_type(self, job_type: str):
        if job_type in self._declared_queues:
            return self._declared_queues[job_type]
        q_name = f"cauveris.queue.{job_type}"
        queue = await self._channel.declare_queue(
            q_name,
            durable=True,
            arguments={
                "x-max-priority": 200,
                "x-dead-letter-exchange": f"{self._exchange_name}.dlx",
                "x-dead-letter-routing-key": f"dlx.{job_type}",
            },
        )
        await queue.bind(self._exchange, routing_key=f"job.*.{job_type}")

        # The dead letter exchange needs a queue of its own, otherwise the
        # broker has nowhere to put a message it rejects: the message is
        # dropped and the failure is invisible.  A rejected job has to be
        # recoverable after the fact, so it is parked where it can be read.
        dlq_name = f"cauveris.dlq.{job_type}"
        dlq = await self._channel.declare_queue(dlq_name, durable=True)
        await dlq.bind(self._dlx, routing_key=f"dlx.{job_type}")
        self._declared_dlqs[job_type] = dlq

        self._declared_queues[job_type] = queue
        return queue

    async def enqueue(self, job: Job) -> bool:
        if not await self._ensure_connection():
            logger.error("RabbitMQQueueBackend: RabbitMQ is unavailable")
            return False

        if job.expires_at is None:
            job.expires_at = time.time() + self._default_ttl

        if job.is_expired():
            self._stats["expired"] += 1
            return False

        try:
            job.priority = JobPriority(job.priority)
        except (ValueError, TypeError):
            job.priority = JobPriority.NORMAL

        tenant_id = job.tenant_id or "default"
        job_type = job.type or "generic"

        if len(self._jobs) >= self._max_size:
            self._stats["rejected_full"] += 1
            logger.warning(f"RabbitMQ queue full, rejecting job {job.id}")
            return False

        await self._get_queue_for_type(job_type)

        routing_key = f"job.{tenant_id}.{job_type}"

        message = self._message_for(job)

        await self._exchange.publish(message, routing_key=routing_key)
        self._jobs[job.id] = job
        self._prune_jobs()
        self._stats["enqueued"] += 1
        return True

    @staticmethod
    def _message_for(job: Job):
        """
        Build the AMQP message that carries a job.

        The expiry needs care: AMQP expresses it as a string of milliseconds,
        and ``aio_pika`` takes it either as a number of *seconds* (which it
        converts) or as a datetime/timedelta.  A string is not one of those,
        and the encoder rejects it - which would turn every publish into a
        failure at the moment the message is built, on a broker that is
        perfectly healthy.
        """
        import aio_pika

        body = json.dumps(job.to_dict()).encode("utf-8")
        priority_val = min(200, max(0, int(job.priority.value)))
        expiration_seconds = (
            max(1, int(job.expires_at - time.time())) if job.expires_at else None
        )

        return aio_pika.Message(
            body=body,
            message_id=job.id,
            priority=priority_val,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            expiration=expiration_seconds,
        )

    def _prune_jobs(self) -> None:
        """
        Drop the bookkeeping for jobs nobody will ask about again.

        The broker holds the queue itself; this dictionary exists so that
        ``get_job`` can answer for a job that passed through this process.
        Without pruning it grows for as long as the process runs, keeping
        every job ever enqueued - and every payload - alive.
        """
        if not self._jobs:
            return
        cutoff = time.time() - self._default_ttl
        stale = [
            job_id
            for job_id, job in self._jobs.items()
            if job.completed_at is not None and job.completed_at < cutoff
        ]
        for job_id in stale:
            self._jobs.pop(job_id, None)
            self._completed.pop(job_id, None)
        for tenant, jobs in list(self._dead_letter.items()):
            kept = [j for j in jobs if j.completed_at is None or j.completed_at >= cutoff]
            if kept:
                self._dead_letter[tenant] = kept
            else:
                self._dead_letter.pop(tenant, None)

    async def dequeue(self, worker_id: str, types: List[str], max_jobs: int = 1) -> List[Job]:
        if not await self._ensure_connection():
            return []

        jobs_taken: List[Job] = []
        effective_types = types or ["generic", "pipeline", "simulation", "patch_generation"]

        for _ in range(max_jobs):
            found_job = None
            for j_type in effective_types:
                queue = await self._get_queue_for_type(j_type)
                incoming_msg = await queue.get(no_ack=False, fail=False)
                if incoming_msg is not None:
                    job_data = json.loads(incoming_msg.body.decode("utf-8"))
                    job = Job.from_dict(job_data)
                    if job.is_expired():
                        await incoming_msg.reject(requeue=False)
                        self._stats["expired"] += 1
                        continue

                    job.status = JobStatus.PROCESSING
                    job.started_at = time.time()
                    job.attempts.append(time.time())

                    self._pending_messages[job.id] = incoming_msg
                    self._processing[job.id] = job
                    self._jobs[job.id] = job
                    self._stats["dequeued"] += 1
                    found_job = job
                    break

            if found_job:
                jobs_taken.append(found_job)
            else:
                break

        return jobs_taken

    async def requeue(self, job: Job) -> bool:
        job.status = JobStatus.QUEUED
        job.retry_count += 1
        job.error = None
        job.expires_at = time.time() + self._default_ttl
        self._processing.pop(job.id, None)
        pending = self._pending_messages.pop(job.id, None)
        if pending:
            try:
                await pending.ack()
            except Exception:
                pass
        return await self.enqueue(job)

    async def complete(self, job_id: str, result: Dict[str, Any]) -> bool:
        job = self._processing.pop(job_id, None) or self._jobs.get(job_id)
        pending = self._pending_messages.pop(job_id, None)
        if pending:
            try:
                await pending.ack()
            except Exception as exc:
                logger.warning(f"Error acking message {job_id}: {exc}")

        if not job:
            return False

        job.status = JobStatus.COMPLETED
        job.completed_at = time.time()
        job.result = result
        self._completed[job_id] = job
        self._jobs[job_id] = job
        self._stats["completed"] += 1
        return True

    async def fail(self, job_id: str, error: str, retry: bool = False) -> bool:
        job = self._processing.pop(job_id, None) or self._jobs.get(job_id)
        pending = self._pending_messages.pop(job_id, None)

        if not job:
            if pending:
                await pending.reject(requeue=False)
            return False

        job.error = error
        can_retry = retry and job.retry_count < job.max_retries

        if can_retry:
            if pending:
                await pending.ack()
            requeued = await self.requeue(job)
            if requeued:
                return True

        if pending:
            try:
                await pending.reject(requeue=False)
            except Exception:
                pass

        job.status = JobStatus.DEAD_LETTER
        job.completed_at = time.time()
        tenant = job.tenant_id or "default"
        if tenant not in self._dead_letter:
            self._dead_letter[tenant] = []
        self._dead_letter[tenant].append(job)
        self._jobs[job_id] = job

        self._stats["failed"] += 1
        self._stats["dead_lettered"] += 1
        return True

    async def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def cancel(self, job_id: str) -> bool:
        job = self._processing.pop(job_id, None) or self._jobs.get(job_id)
        pending = self._pending_messages.pop(job_id, None)
        if pending:
            try:
                await pending.reject(requeue=False)
            except Exception:
                pass
        if not job:
            return False
        job.status = JobStatus.CANCELLED
        job.completed_at = time.time()
        self._jobs[job_id] = job
        self._stats["cancelled"] += 1
        return True

    async def get_stats(self) -> Dict[str, Any]:
        stats = self._stats.copy()
        stats["queued_total"] = max(
            0, len(self._jobs) - len(self._processing) - len(self._completed)
        )
        stats["processing"] = len(self._processing)
        stats["completed_cached"] = len(self._completed)
        stats["dead_letter_total"] = sum(len(v) for v in self._dead_letter.values())
        return stats

    async def health_check(self) -> bool:
        return await self._ensure_connection()

    async def close(self) -> None:
        if self._channel and not getattr(self._channel, "is_closed", False):
            await self._channel.close()
        if self._connection and not getattr(self._connection, "is_closed", False):
            await self._connection.close()
        self._healthy = False


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

    @property
    def worker_id(self) -> str:
        """The identity this worker claims jobs under."""
        return self._worker_id

    @property
    def is_running(self) -> bool:
        """Whether the worker loop is currently alive."""
        return self._worker_task is not None and not self._worker_task.done()

    @property
    def handled_types(self) -> List[str]:
        """The job types this worker can run."""
        return sorted(self._handlers.keys())

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
            if current and current.status in (
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.DEAD_LETTER,
                JobStatus.CANCELLED,
            ):
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
                jobs = await self._backend.dequeue(
                    self._worker_id, types, self._max_concurrent_jobs
                )
                if not jobs:
                    # No jobs, wait a bit
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(), timeout=self._poll_interval
                        )
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
        stats = await self._backend.get_stats()
        # The worker answers the question the queue statistics cannot: is
        # anybody actually serving this queue?
        stats["worker_id"] = self._worker_id
        stats["worker_running"] = self.is_running
        stats["worker_handled_types"] = self.handled_types
        stats["worker_concurrency"] = self._max_concurrent_jobs
        return stats

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
    backend: Optional[str] = None,
    max_size: Optional[int] = None,
    default_ttl: Optional[int] = None,
    worker_id: Optional[str] = None,
    redis_url: Optional[str] = None,
    rabbitmq_url: Optional[str] = None,
) -> JobQueue:
    """Initialize the global job queue."""
    global _job_queue_backend, _job_queue

    from cauveris.config import get_settings

    settings = get_settings()
    chosen_backend = (backend or getattr(settings, "job_queue_backend", "memory")).lower()
    effective_max_size = (
        max_size if max_size is not None else getattr(settings, "job_queue_max_size", 10000)
    )
    effective_default_ttl = (
        default_ttl
        if default_ttl is not None
        else getattr(settings, "job_queue_default_ttl", 3600)
    )

    if chosen_backend == "redis":
        url = redis_url or getattr(settings, "job_queue_redis_url", "redis://localhost:6379")
        _job_queue_backend = RedisQueueBackend(
            redis_url=url,
            max_size=effective_max_size,
            default_ttl=effective_default_ttl,
        )
    elif chosen_backend in ("rabbitmq", "amqp"):
        url = rabbitmq_url or getattr(
            settings, "job_queue_rabbitmq_url", "amqp://guest:guest@localhost:5672/"
        )
        _job_queue_backend = RabbitMQQueueBackend(
            amqp_url=url,
            max_size=effective_max_size,
            default_ttl=effective_default_ttl,
        )
    else:
        _job_queue_backend = InMemoryQueueBackend(
            max_size=effective_max_size,
            default_ttl=effective_default_ttl,
        )

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

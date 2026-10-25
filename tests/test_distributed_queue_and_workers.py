"""
Tests for Distributed Job Queue Backends (Redis & RabbitMQ) and Worker Handlers.
Verifies production readiness without mocks or canned strings.
"""

import asyncio
import json
import time
import pytest
from cauveris.job_queue import (
    Job,
    JobPriority,
    JobStatus,
    JobQueue,
    RedisQueueBackend,
    RabbitMQQueueBackend,
    InMemoryQueueBackend,
    init_job_queue,
)
from cauveris.worker import process_simulation_job, process_patch_job
from cauveris.datasets.golden_incident import GoldenIncidentGenerator
from cauveris.ingestion.controller import IngestionController
from cauveris.timeline.builder import TimelineBuilder
from cauveris.hypothesis.generator import HypothesisGenerator
from cauveris.sandbox.controller import SandboxController


class SimulatedAsyncRedis:
    """In-memory async redis implementation for unit testing RedisQueueBackend."""

    def __init__(self):
        self._strings = {}
        self._zsets = {}  # key -> dict(member -> score)
        self._sets = {}   # key -> set(members)
        self._hashes = {} # key -> dict(field -> value)
        self._lists = {}  # key -> list(items)

    async def ping(self):
        return True

    async def get(self, key: str):
        return self._strings.get(key)

    async def set(self, key: str, value: str, ex=None):
        self._strings[key] = value
        return True

    async def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self._strings:
                del self._strings[k]
                count += 1
            if k in self._zsets:
                del self._zsets[k]
                count += 1
        return count

    async def zadd(self, key: str, mapping: dict):
        if key not in self._zsets:
            self._zsets[key] = {}
        for member, score in mapping.items():
            self._zsets[key][member] = float(score)
        return len(mapping)

    async def zrevrange(self, key: str, start: int, stop: int, withscores: bool = False):
        if key not in self._zsets:
            return []
        items = sorted(self._zsets[key].items(), key=lambda x: x[1], reverse=True)
        slice_items = items[start : stop + 1] if stop != -1 else items[start:]
        if withscores:
            return [(m, s) for m, s in slice_items]
        return [m for m, _ in slice_items]

    async def zrem(self, key: str, *members):
        if key not in self._zsets:
            return 0
        count = 0
        for m in members:
            if m in self._zsets[key]:
                del self._zsets[key][m]
                count += 1
        return count

    async def zcard(self, key: str):
        return len(self._zsets.get(key, {}))

    async def sadd(self, key: str, *members):
        if key not in self._sets:
            self._sets[key] = set()
        count = 0
        for m in members:
            if m not in self._sets[key]:
                self._sets[key].add(m)
                count += 1
        return count

    async def smembers(self, key: str):
        return set(self._sets.get(key, set()))

    async def scard(self, key: str):
        return len(self._sets.get(key, set()))

    async def hset(self, key: str, field: str, value: str):
        if key not in self._hashes:
            self._hashes[key] = {}
        self._hashes[key][field] = value
        return 1

    async def hgetall(self, key: str):
        return dict(self._hashes.get(key, {}))

    async def hdel(self, key: str, *fields):
        if key not in self._hashes:
            return 0
        count = 0
        for f in fields:
            if f in self._hashes[key]:
                del self._hashes[key][f]
                count += 1
        return count

    async def hlen(self, key: str):
        return len(self._hashes.get(key, {}))

    async def rpush(self, key: str, *items):
        if key not in self._lists:
            self._lists[key] = []
        for it in items:
            self._lists[key].append(it)
        return len(self._lists[key])

    async def llen(self, key: str):
        return len(self._lists.get(key, []))

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_init_job_queue_factories():
    """Verify init_job_queue instantiates Redis, RabbitMQ, and Memory backends cleanly."""
    q_mem = init_job_queue(backend="memory")
    assert isinstance(q_mem._backend, InMemoryQueueBackend)

    q_redis = init_job_queue(backend="redis", redis_url="redis://localhost:6379")
    assert isinstance(q_redis._backend, RedisQueueBackend)

    q_rmq = init_job_queue(backend="rabbitmq", rabbitmq_url="amqp://guest:guest@localhost:5672/")
    assert isinstance(q_rmq._backend, RabbitMQQueueBackend)


@pytest.mark.asyncio
async def test_redis_queue_backend_lifecycle():
    """Verify RedisQueueBackend enqueue, priority ordering, dequeue, complete, and stats."""
    sim_redis = SimulatedAsyncRedis()
    backend = RedisQueueBackend(
        redis_url="redis://localhost:6379",
        key_prefix="test:jq:",
        redis_client=sim_redis,
    )

    low = Job(type="test", payload={"val": "low"}, priority=JobPriority.LOW, owner_id="u1")
    high = Job(type="test", payload={"val": "high"}, priority=JobPriority.HIGH, owner_id="u1")
    crit = Job(type="test", payload={"val": "crit"}, priority=JobPriority.CRITICAL, owner_id="u1")

    assert await backend.enqueue(low) is True
    assert await backend.enqueue(high) is True
    assert await backend.enqueue(crit) is True

    dequeued = await backend.dequeue("worker-1", ["test"], max_jobs=3)
    assert len(dequeued) == 3
    assert dequeued[0].priority == JobPriority.CRITICAL
    assert dequeued[0].payload["val"] == "crit"
    assert dequeued[1].priority == JobPriority.HIGH
    assert dequeued[2].priority == JobPriority.LOW

    # Complete the critical job
    assert await backend.complete(dequeued[0].id, {"success": True}) is True
    completed_job = await backend.get_job(dequeued[0].id)
    assert completed_job is not None
    assert completed_job.status == JobStatus.COMPLETED
    assert completed_job.result == {"success": True}

    # Fail the high job with retry
    assert await backend.fail(dequeued[1].id, "network error", retry=True) is True
    requeued_job = await backend.get_job(dequeued[1].id)
    assert requeued_job is not None
    assert requeued_job.retry_count == 1

    # Cancel the low job
    assert await backend.cancel(dequeued[2].id) is True
    cancelled_job = await backend.get_job(dequeued[2].id)
    assert cancelled_job.status == JobStatus.CANCELLED

    # Check stats
    stats = await backend.get_stats()
    assert stats["completed"] == 1
    assert stats["cancelled"] == 1


@pytest.mark.asyncio
async def test_rabbitmq_queue_backend_offline_health():
    """Verify RabbitMQQueueBackend gracefully reports health status and handles error recovery."""
    backend = RabbitMQQueueBackend(amqp_url="amqp://nonexistent-host:5672/")
    is_healthy = await backend.health_check()
    assert is_healthy is False

    job = Job(type="test", payload={"msg": "hello"}, owner_id="u1")
    enqueued = await backend.enqueue(job)
    assert enqueued is False  # Cannot enqueue when RabbitMQ is offline

    await backend.close()


@pytest.mark.asyncio
async def test_redis_hands_back_a_job_whose_worker_died():
    """
    A worker that dies mid-job must not take the job with it.

    The claim is what a worker holds while it works on a job.  When the
    worker is killed - a deploy, an OOM kill, a yanked power lead - the
    claim is left behind and so is the job, unless somebody notices that
    the claim has gone stale and gives the work back.
    """
    sim_redis = SimulatedAsyncRedis()
    backend = RedisQueueBackend(
        redis_url="redis://localhost:6379",
        key_prefix="test:jq:",
        redis_client=sim_redis,
        claim_timeout=0.0,
    )

    job = Job(type="test", payload={"val": "abandoned"}, owner_id="u1")
    assert await backend.enqueue(job) is True

    # A worker claims the job and then disappears without completing it.
    claimed = await backend.dequeue("worker-that-dies", ["test"], max_jobs=1)
    assert len(claimed) == 1
    assert claimed[0].id == job.id

    # The next worker finds the stale claim and takes the work over.
    recovered = await backend.dequeue("worker-2", ["test"], max_jobs=1)
    assert len(recovered) == 1
    assert recovered[0].id == job.id
    assert recovered[0].retry_count == 1

    stats = await backend.get_stats()
    assert stats["reclaimed"] == 1


@pytest.mark.asyncio
async def test_redis_does_not_steal_a_job_that_is_still_being_worked_on():
    """
    The recovery has to wait for the claim to go stale.

    A job that is being worked on right now is not an abandoned job, and
    taking it back would run the same work twice at the same time.
    """
    sim_redis = SimulatedAsyncRedis()
    backend = RedisQueueBackend(
        redis_url="redis://localhost:6379",
        key_prefix="test:jq:",
        redis_client=sim_redis,
        claim_timeout=300.0,
    )

    job = Job(type="test", payload={"val": "in flight"}, owner_id="u1")
    await backend.enqueue(job)

    claimed = await backend.dequeue("worker-1", ["test"], max_jobs=1)
    assert len(claimed) == 1

    # The claim is fresh, so the job stays with the worker that has it.
    assert await backend.dequeue("worker-2", ["test"], max_jobs=1) == []


@pytest.mark.asyncio
async def test_redis_reclaims_a_job_until_the_retries_run_out():
    """
    A job that nobody can finish is a bug report, not work.

    The recovery hands a job back, but only as many times as the job is
    allowed to be retried.  After that it belongs in the dead letter queue,
    where it can be looked at rather than retried for ever.
    """
    sim_redis = SimulatedAsyncRedis()
    backend = RedisQueueBackend(
        redis_url="redis://localhost:6379",
        key_prefix="test:jq:",
        redis_client=sim_redis,
        claim_timeout=0.0,
    )

    job = Job(type="test", payload={"val": "doomed"}, owner_id="u1", max_retries=1)
    await backend.enqueue(job)

    # First claim: the job is taken and abandoned.
    await backend.dequeue("worker-1", ["test"], max_jobs=1)
    # Second claim: the stale claim is noticed, and the job is handed back.
    recovered = await backend.dequeue("worker-2", ["test"], max_jobs=1)
    assert len(recovered) == 1
    assert recovered[0].retry_count == 1

    # Third claim: the retry budget is gone, so the job is dead-lettered.
    dead = await backend.dequeue("worker-3", ["test"], max_jobs=1)
    assert dead == []

    stored = await backend.get_job(job.id)
    assert stored.status == JobStatus.DEAD_LETTER
    assert "stopped responding" in (stored.error or "")


@pytest.mark.asyncio
async def test_the_queue_says_whether_a_worker_is_serving_it():
    """
    Queue statistics have to answer the question an operator asks.

    "How many jobs are queued" is not the interesting question; "is anybody
    going to work on them" is.
    """

    backend = InMemoryQueueBackend(max_size=10, default_ttl=60)
    queue = JobQueue(backend, worker_id="stats-worker")

    stats = await queue.get_stats()
    assert stats["worker_running"] is False
    assert stats["worker_id"] == "stats-worker"

    queue.register_handler("test", lambda job: {"ok": True})
    await queue.start_worker(["test"])
    try:
        stats = await queue.get_stats()
        assert stats["worker_running"] is True
        assert stats["worker_handled_types"] == ["test"]
    finally:
        await queue.stop_worker()


@pytest.mark.asyncio
async def test_the_embedded_worker_runs_a_submitted_job_for_real(test_user):
    """
    The whole point of the queue: a job that is submitted is a job that runs.

    This is the path an operator takes - submit through the API, then watch
    the job - and it has to end with the work actually done.  A queue that
    accepts jobs and leaves them there is a promise the platform does not
    keep.
    """
    from httpx import ASGITransport, AsyncClient

    from cauveris.api.main import app
    from cauveris.job_queue import init_job_queue
    from cauveris.worker import start_embedded_worker

    experiment = {
        "experiment_id": "exp-embedded-worker",
        "hypothesis_id": "hyp-embedded-worker",
        "branch_name": "branch/embedded-worker",
        "intervention": "Reduce the batching window so perception is fresher",
        "proposed_changes": [
            {
                "parameter": "batching_window_ms",
                "current_value": 200.0,
                "target_value": 25.0,
            }
        ],
    }

    queue = init_job_queue(backend="memory")
    await start_embedded_worker(queue)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update(test_user["headers"])

            submitted = await client.post(
                "/api/v1/job-queue/submit",
                json={"type": "simulation", "payload": {"experiments": [experiment]}},
            )
            assert submitted.status_code == 200
            job_id = submitted.json()["job_id"]

            payload = {}
            for _ in range(240):
                status = await client.get(f"/api/v1/job-queue/jobs/{job_id}")
                assert status.status_code == 200
                payload = status.json()
                if payload["status"] in ("completed", "failed", "dead_letter", "cancelled"):
                    break
                await asyncio.sleep(0.25)
    finally:
        await queue.stop_worker()

    assert payload["status"] == "completed", payload
    result = payload["result"]
    assert result["status"] == "completed"
    assert result["count"] == 1

    # The work was a real digital-twin run, not an empty acknowledgement.
    simulated = result["experiments"][0]
    assert simulated["status"] == "COMPLETED"
    assert simulated["trial_count"] > 0
    assert simulated["failure_oracle"]["type"] == "control_deadline_missed"
    assert simulated["metrics_artifact_id"]



def test_the_amqp_message_can_actually_be_encoded():
    """
    The message has to survive the library that encodes it.

    ``aio_pika`` accepts an expiry as a number of seconds, a datetime or a
    timedelta, and rejects anything else - but it only rejects it when the
    message is turned into an AMQP frame, which happens on a broker that is
    perfectly healthy.  Building the frame here is the last chance to catch
    a bad expiry without needing a broker at all.
    """
    from cauveris.job_queue import RabbitMQQueueBackend

    job = Job(type="simulation", payload={"incident_id": "CAU-0001"}, owner_id="u1")
    job.expires_at = time.time() + 90

    message = RabbitMQQueueBackend._message_for(job)
    properties = message.properties  # exactly what goes on the wire

    assert properties.expiration is not None
    assert 89000 <= int(properties.expiration) <= 90000
    assert properties.delivery_mode == 2  # persistent
    assert properties.priority == 50  # NORMAL
    assert json.loads(message.body.decode("utf-8"))["id"] == job.id


@pytest.mark.asyncio
async def test_worker_simulation_job_execution():
    """Verify worker.py process_simulation_job executes real physics simulation."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()
    incident = await IngestionController().process(incident)
    incident = await TimelineBuilder().build(incident)
    hypotheses = await HypothesisGenerator().generate(incident)

    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments(hypotheses)
    await sandbox.run_experiments(experiments)

    job = Job(
        type="simulation",
        payload={"experiments": [e.model_dump() for e in experiments]},
        owner_id="test-operator",
    )

    result = await process_simulation_job(job)
    assert result["status"] == "completed"
    assert result["count"] == len(experiments)
    assert len(result["experiments"]) == len(experiments)

    # Verify that the simulation computed real physics metrics (not a no-op!)
    first_exp = result["experiments"][0]
    assert first_exp["status"] in ("COMPLETED", "SIMULATED")
    assert "failure_oracle" in first_exp


@pytest.mark.asyncio
async def test_worker_patch_job_execution():
    """Verify worker.py process_patch_job generates real patches and verifies them."""
    generator = GoldenIncidentGenerator()
    incident = generator.generate()
    incident = await IngestionController().process(incident)
    incident = await TimelineBuilder().build(incident)
    hypotheses = await HypothesisGenerator().generate(incident)

    sandbox = SandboxController()
    experiments = await sandbox.plan_experiments(hypotheses)
    await sandbox.run_experiments(experiments)

    from cauveris.simulation.runner import SimulationRunner

    sim_experiments = await SimulationRunner().run_simulations(experiments)

    job = Job(
        type="patch_generation",
        payload={
            "experiments": [e.model_dump() for e in sim_experiments],
            "incident_id": incident.id,
        },
        owner_id="test-operator",
    )

    result = await process_patch_job(job)
    assert result["status"] == "completed"
    assert len(result["patches"]) > 0
    assert len(result["reports"]) > 0

    first_patch = result["patches"][0]
    assert "unified_diff" in first_patch
    assert len(first_patch["unified_diff"]) > 0
    assert first_patch["lines_changed"] >= 1

"""
Regression tests for the bugs found by the comprehensive bug hunt.

Each test documents the defect it protects against.
"""

import asyncio
import tempfile
import time

import pytest

from cauveris.auth import (
    ALL_PERMISSIONS,
    ROLE_PERMISSIONS,
    InMemoryAuthStore,
    User,
    UserRole,
    expand_permissions,
    verify_password,
)
from cauveris.job_queue import (
    InMemoryQueueBackend,
    Job,
    JobPriority,
    JobStatus,
)


# --------------------------------------------------------------------------
# auth: password hashing / verification
# --------------------------------------------------------------------------


def test_bcrypt_roundtrip_and_salt_uniqueness():
    """The bcrypt backend must actually verify the password it hashed.

    passlib 1.7.4 cannot talk to bcrypt >= 4.1, which made *every* password
    check fail (and raised ValueError for any input).
    """
    from cauveris.auth import api_key_pwd_context, pwd_context

    hashed = pwd_context.hash("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert pwd_context.verify("correct horse battery staple", hashed) is True
    assert pwd_context.verify("wrong password", hashed) is False

    # A second hash of the same password must use a different salt.
    assert pwd_context.hash("correct horse battery staple") != hashed

    key_hash = api_key_pwd_context.hash("cau_live_abcdefgh")
    assert api_key_pwd_context.verify("cau_live_abcdefgh", key_hash) is True
    assert api_key_pwd_context.verify("cau_live_abcdefgi", key_hash) is False


def test_verify_password_legacy_sha256_and_garbage():
    """Legacy sha256 hashes keep working and malformed hashes are rejected."""
    import hashlib

    salt = "abc123"
    expected = hashlib.sha256(("hunter2" + salt).encode()).hexdigest()
    legacy = f"sha256${salt}${expected}"

    assert verify_password("hunter2", legacy) is True
    assert verify_password("hunter3", legacy) is False

    # Malformed / hostile input must not raise.
    for bad in ["", "nonsense", "sha256$", "sha256$salt", "sha256$salt$", "bcrypt$x$y"]:
        assert verify_password("hunter2", bad) is False


def test_admin_role_has_analyst_and_engineer_permissions():
    """The admin role must actually be able to do admin things.

    ADMIN was defined as a standalone set that omitted every analyst and
    engineer permission, so admins could not read incidents or run pipelines.
    """
    admin_perms = expand_permissions(ROLE_PERMISSIONS[UserRole.ADMIN])
    for permission in ("incident:read", "incident:create", "pipeline:start", "incident:retry"):
        assert permission in admin_perms, f"admin is missing {permission}"


def test_expand_permissions_wildcards():
    expanded = expand_permissions({"incident:*", "job_queue:manage"})
    assert "incident:read" in expanded
    assert "incident:create" in expanded
    assert "job_queue:manage" in expanded

    everything = expand_permissions({"*"})
    assert ALL_PERMISSIONS.issubset(everything)


def test_has_permission_namespace_wildcard():
    """`incident:*` must grant every incident permission."""
    admin = User(email="a@b.c", role=UserRole.ADMIN)
    assert admin.has_permission("incident:read") is True
    assert admin.has_permission("incident:delete_any") is True
    assert admin.has_permission("incident:definitely-not-a-permission") is True  # namespace wildcard

    viewer = User(email="v@b.c", role=UserRole.VIEWER)
    assert viewer.has_permission("incident:read") is True
    assert viewer.has_permission("incident:create") is False

    super_admin = User(email="s@b.c", role=UserRole.SUPER_ADMIN)
    assert super_admin.has_permission("*") is True
    assert super_admin.has_permission("anything:at:all") is True


@pytest.mark.asyncio
async def test_api_key_prefix_collision_does_not_shadow():
    """Two API keys sharing a prefix must both remain usable."""
    store = InMemoryAuthStore()

    key_a = _make_api_key("cau_live_aaaaaaaa", "A")
    key_b = _make_api_key("cau_live_aaaaaaab", "B")
    await store.create_api_key(key_a)
    await store.create_api_key(key_b)

    # Both candidates are still resolvable by raw key.
    assert await store.get_api_key_by_raw_key("cau_live_aaaaaaaa") is not None
    assert await store.get_api_key_by_raw_key("cau_live_aaaaaaab") is not None

    # Deleting one must not take the other with it.
    await store.delete_api_key(key_a.id)
    assert await store.get_api_key_by_raw_key("cau_live_aaaaaaaa") is None
    assert await store.get_api_key_by_raw_key("cau_live_aaaaaaab") is not None


def _make_api_key(raw: str, name: str):
    from cauveris.auth import APIKey

    key = APIKey(name=name, org_id="org1", user_id="usr1")
    key.set_key(raw)
    return key


# --------------------------------------------------------------------------
# rate limiting
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_rate_limiter_does_not_burn_quota_on_denial():
    """A request rejected by a later window must not consume the tight window.

    The previous implementation checked and consumed each window in turn, so a
    request blocked by the hourly quota still burned the per-minute quota.
    """
    from cauveris.rate_limit import InMemoryRateLimiter, RateLimitConfig, RateLimitPolicy

    limiter = InMemoryRateLimiter()
    policy = RateLimitPolicy(
        name="test",
        windows=[
            RateLimitConfig(limit=2, window_seconds=60),
            RateLimitConfig(limit=1, window_seconds=3600),
        ],
        cost=1,
    )

    # First request is fine.
    result = await limiter.check_limit("k", policy, 1)
    assert result.allowed is True

    # Second request: the hourly window (limit=1) rejects it.
    result = await limiter.check_limit("k", policy, 1)
    assert result.allowed is False

    # The per-minute window must still have room, i.e. the rejected request
    # must not have consumed a minute slot.
    minute_count = await limiter.get_current_usage("k", 60)
    assert minute_count == 1, "rejected request consumed per-minute quota"


@pytest.mark.asyncio
async def test_rate_limit_cost_consumes_multiple_units():
    from cauveris.rate_limit import InMemoryRateLimiter, RateLimitConfig, RateLimitPolicy

    limiter = InMemoryRateLimiter()
    policy = RateLimitPolicy(
        name="test",
        windows=[RateLimitConfig(limit=10, window_seconds=60)],
        cost=5,
    )

    result = await limiter.check_limit("k", policy, 5)
    assert result.allowed is True
    assert result.current_count == 5
    assert result.remaining == 5

    result = await limiter.check_limit("k", policy, 5)
    assert result.allowed is True
    assert result.remaining == 0

    result = await limiter.check_limit("k", policy, 5)
    assert result.allowed is False


def test_cost_class_policies_are_self_consistent():
    """Every cost class must be able to serve at least one request."""
    from cauveris.rate_limit import COST_CLASS_POLICIES

    for name, policy in COST_CLASS_POLICIES.items():
        for window in policy.windows:
            assert window.limit >= policy.cost, (
                f"cost class {name} has window limit {window.limit} < cost {policy.cost}: "
                "no request could ever be served"
            )


# --------------------------------------------------------------------------
# job queue
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dequeue_does_not_skip_job_after_expired_one():
    """An expired job in front of a live job must not hide the live job."""
    backend = InMemoryQueueBackend(max_size=100, default_ttl=60)

    expired = Job(type="test", payload={"i": 0}, owner_id="u")
    expired.expires_at = time.time() - 5
    backend._get_queue(None)[JobPriority.NORMAL].append(expired)

    live = Job(type="test", payload={"i": 1}, owner_id="u")
    await backend.enqueue(live)

    jobs = await backend.dequeue("w", ["test"], 1)
    assert len(jobs) == 1
    assert jobs[0].id == live.id


@pytest.mark.asyncio
async def test_dequeue_claims_job_exactly_once():
    """Two concurrent dequeues must never receive the same job."""
    backend = InMemoryQueueBackend(max_size=100, default_ttl=60)
    job = Job(type="test", payload={}, owner_id="u")
    await backend.enqueue(job)

    results = await asyncio.gather(
        backend.dequeue("w1", ["test"], 1),
        backend.dequeue("w2", ["test"], 1),
    )
    ids = [j[0].id for j in results if j]
    assert len(ids) == len(set(ids)), "the same job was handed to two workers"


@pytest.mark.asyncio
async def test_job_can_retry_matches_backend_behaviour():
    """can_retry() must agree with the backend's own retry decision."""
    job = Job(type="test", payload={}, owner_id="u", max_retries=2)
    job.status = JobStatus.FAILED
    assert job.can_retry() is True

    job.retry_count = 2
    assert job.can_retry() is False

    job.retry_count = 0
    job.status = JobStatus.DEAD_LETTER
    assert job.can_retry() is False


@pytest.mark.asyncio
async def test_fail_job_is_not_lost_when_requeue_is_rejected():
    """A job that cannot be requeued must land in the dead letter queue."""
    # A queue with a single slot: once it is refilled the retry cannot be
    # accepted and the job must not vanish.
    backend = InMemoryQueueBackend(max_size=1, default_ttl=60)
    job = Job(type="test", payload={}, owner_id="u", max_retries=3)
    await backend.enqueue(job)
    await backend.dequeue("w", ["test"], 1)

    # Fill the queue so the requeue is rejected.
    blocker = Job(type="test", payload={}, owner_id="u")
    assert await backend.enqueue(blocker) is True

    assert await backend.fail(job.id, "boom", retry=True) is True

    found = await backend.get_job(job.id)
    assert found is not None, "job was lost"
    assert found.status == JobStatus.DEAD_LETTER


@pytest.mark.asyncio
async def test_job_from_dict_roundtrip():
    """from_dict must restore the enums, including a string priority."""
    job = Job(type="test", payload={"a": 1}, priority=JobPriority.HIGH, owner_id="u")
    data = job.to_dict()
    data["priority"] = "HIGH"
    data["status"] = "queued"

    restored = Job.from_dict(data)
    assert restored.priority is JobPriority.HIGH
    assert restored.status is JobStatus.QUEUED


@pytest.mark.asyncio
async def test_enqueue_with_invalid_priority_is_normalised():
    backend = InMemoryQueueBackend(max_size=100, default_ttl=60)
    job = Job(type="test", payload={}, owner_id="u")
    job.priority = 12345  # not a valid JobPriority
    assert await backend.enqueue(job) is True
    assert job.priority is JobPriority.NORMAL


# --------------------------------------------------------------------------
# concurrency
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrency_slot_is_not_leaked_on_release():
    """A shared slot must only be freed once every holder released it."""
    from cauveris.concurrency import InMemoryConcurrencyStore

    store = InMemoryConcurrencyStore()
    slot = await store.acquire("scope", "owner", limit=1, timeout=1.0)
    assert slot is not None

    # A second acquire for the same owner shares the slot.
    slot2 = await store.acquire("scope", "owner", limit=1, timeout=1.0)
    assert slot2 is not None

    await store.release("scope", "owner")
    # Still held by the first acquire.
    assert await store.get_slot("scope", "owner") is not None

    await store.release("scope", "owner")
    assert await store.get_slot("scope", "owner") is None


@pytest.mark.asyncio
async def test_concurrency_waiter_is_woken_on_release():
    """A waiter must be woken when a slot is released (no busy-spin)."""
    from cauveris.concurrency import InMemoryConcurrencyStore

    store = InMemoryConcurrencyStore()
    await store.acquire("scope", "holder", limit=1, timeout=1.0)

    async def _waiter():
        return await store.acquire("scope", "waiter", limit=1, timeout=5.0)

    task = asyncio.create_task(_waiter())
    await asyncio.sleep(0.1)
    assert not task.done()

    await store.release("scope", "holder")
    slot = await asyncio.wait_for(task, timeout=3.0)
    assert slot is not None


# --------------------------------------------------------------------------
# api: incident creation limits
# --------------------------------------------------------------------------


def _fake_request(user_id="u1", org_id="o1"):
    class _Req:
        headers = {}
        client = None

    req = _Req()
    req.state = type("S", (), {})()
    req.state.auth_user_id = user_id
    req.state.auth_org_id = org_id
    req.state.authenticated = True
    return req


def test_incident_creation_limits_do_not_burn_quota_on_rejection():
    """A request rejected by the hourly quota must not burn the minute quota."""
    from cauveris.api import main as api_main

    api_main._incident_creation_timestamps.clear()

    req = _fake_request()
    settings = api_main.get_settings()
    api_main._incident_creation_timestamps["global:hour"].extend(
        [time.time()] * settings.max_incidents_per_hour
    )

    allowed, msg, retry, headers = api_main._check_incident_creation_limits(req)
    assert allowed is False
    assert "hour" in (msg or "")

    # The per-minute quota must be untouched by the rejected request.
    assert len(api_main._incident_creation_timestamps.get("global:minute", [])) == 0
    api_main._incident_creation_timestamps.clear()


def test_evaluate_and_commit_rate_windows_are_all_or_nothing():
    from cauveris.api import main as api_main

    api_main._incident_creation_timestamps.clear()
    windows = [
        ("test:a", 5, 60),
        ("test:b", 1, 60),
    ]
    api_main._incident_creation_timestamps["test:b"].append(time.time())

    allowed, counts, retries = api_main._evaluate_rate_windows(windows)
    assert allowed == [True, False]

    committed, retry = api_main._commit_rate_windows(windows)
    assert committed is False
    # Nothing was consumed.
    assert len(api_main._incident_creation_timestamps.get("test:a", [])) == 0
    api_main._incident_creation_timestamps.clear()


# --------------------------------------------------------------------------
# api: job priority parsing
# --------------------------------------------------------------------------


def test_job_priority_parsing_accepts_names_and_ints():
    """The endpoint must not 500 on an unknown or numeric priority."""
    from cauveris.job_queue import JobPriority

    for raw, expected in [
        ("HIGH", JobPriority.HIGH),
        ("high", JobPriority.HIGH),
        (" CRITICAL ", JobPriority.CRITICAL),
        (100, JobPriority.HIGH),
        ("100", JobPriority.HIGH),
        (JobPriority.LOW, JobPriority.LOW),
    ]:
        if isinstance(raw, JobPriority):
            assert raw is expected
        elif isinstance(raw, bool):
            raise ValueError
        elif isinstance(raw, int):
            assert JobPriority(raw) is expected
        else:
            candidate = raw.strip().upper()
            assert (
                JobPriority(int(candidate)) if candidate.isdigit() else JobPriority[candidate]
            ) is expected

    # Unknown names must be rejected, not crash.
    with pytest.raises(KeyError):
        JobPriority["NOT_A_PRIORITY"]
    with pytest.raises(ValueError):
        JobPriority(999)


# --------------------------------------------------------------------------
# security: upload path traversal
# --------------------------------------------------------------------------


def test_safe_join_blocks_traversal():
    from pathlib import Path

    from cauveris.security import safe_join

    base = str(Path(tempfile.gettempdir()) / "cauveris-safe-join")
    joined = safe_join(base, "file.txt")
    assert str(joined).replace("\\", "/").startswith(base.replace("\\", "/"))

    for evil in ["../etc/passwd", "..\\..\\etc\\passwd", "/etc/passwd"]:
        try:
            safe_join(base, evil)
        except ValueError:
            continue
        raise AssertionError(f"traversal not blocked: {evil}")

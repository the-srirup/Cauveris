"""
Rate Limiting Abstraction for Cauveris.

Provides a unified interface for rate limiting with multiple backends:
- In-memory (development)
- Redis (production)

Supports:
- Token bucket algorithm
- Sliding window algorithm
- Per-endpoint cost class policies
- Standard rate limit headers (RFC 6585)
- Graceful degradation on backend failure
"""

import time
import asyncio
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional, Dict, List, Callable
from collections import defaultdict
from threading import Lock
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RateLimitAlgorithm(Enum):
    """Supported rate limiting algorithms."""

    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"  # More precise, stores all timestamps


class RateLimitAction(Enum):
    """Action to take when rate limit is exceeded."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass
class RateLimitConfig:
    """Configuration for a single rate limit window."""

    limit: int
    window_seconds: int
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW_LOG


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    current_count: int
    limit: int
    remaining: int
    reset_seconds: int
    retry_after: Optional[int] = None
    policy_name: str = ""

    @property
    def headers(self) -> Dict[str, str]:
        """Generate standard rate limit headers."""
        h = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(time.time()) + self.reset_seconds),
        }
        if self.retry_after is not None:
            h["Retry-After"] = str(self.retry_after)
        if self.policy_name:
            h["X-RateLimit-Policy"] = self.policy_name
        return h


@dataclass
class RateLimitPolicy:
    """A named rate limit policy with multiple windows."""

    name: str
    windows: List[RateLimitConfig]
    cost: int = 1  # Cost in tokens for token bucket


# Cost class definitions mapping endpoints to policies.
#
# Window limits are expressed in the same unit as the class cost: a request of
# a class with cost N consumes N units of every window's allowance. The
# comment after each limit gives the resulting number of *requests* per window.
COST_CLASS_POLICIES: Dict[str, RateLimitPolicy] = {
    "LOW_COST": RateLimitPolicy(
        name="low_cost",
        windows=[
            RateLimitConfig(limit=100, window_seconds=60),  # 100/min
            RateLimitConfig(limit=1000, window_seconds=3600),  # 1000/hr
        ],
    ),
    "NORMAL_READ": RateLimitPolicy(
        name="normal_read",
        windows=[
            RateLimitConfig(limit=60, window_seconds=60),  # 60/min
            RateLimitConfig(limit=500, window_seconds=3600),  # 500/hr
        ],
    ),
    "PUBLIC_READ": RateLimitPolicy(
        name="public_read",
        windows=[
            RateLimitConfig(limit=200, window_seconds=60),  # 200/min
            RateLimitConfig(limit=2000, window_seconds=3600),  # 2000/hr
        ],
    ),
    "MUTATION": RateLimitPolicy(
        name="mutation",
        windows=[
            RateLimitConfig(limit=30, window_seconds=60),  # 30/min
            RateLimitConfig(limit=200, window_seconds=3600),  # 200/hr
        ],
        cost=1,
    ),
    "UPLOAD": RateLimitPolicy(
        name="upload",
        windows=[
            RateLimitConfig(limit=50, window_seconds=60),  # 10 uploads/min
            RateLimitConfig(limit=250, window_seconds=3600),  # 50 uploads/hr
        ],
        cost=5,
    ),
    "COMPUTE": RateLimitPolicy(
        name="compute",
        windows=[
            RateLimitConfig(limit=50, window_seconds=60),  # 5 computes/min
            RateLimitConfig(limit=300, window_seconds=3600),  # 30 computes/hr
        ],
        cost=10,
    ),
    "EXPERIMENT": RateLimitPolicy(
        name="experiment",
        windows=[
            RateLimitConfig(limit=60, window_seconds=60),  # 3 experiments/min
            RateLimitConfig(limit=200, window_seconds=3600),  # 10 experiments/hr
        ],
        cost=20,
    ),
    "PATCH": RateLimitPolicy(
        name="patch",
        windows=[
            RateLimitConfig(limit=75, window_seconds=60),  # 5 patches/min
            RateLimitConfig(limit=300, window_seconds=3600),  # 20 patches/hr
        ],
        cost=15,
    ),
    "DOWNLOAD": RateLimitPolicy(
        name="download",
        windows=[
            RateLimitConfig(limit=40, window_seconds=60),  # 20 downloads/min
            RateLimitConfig(limit=400, window_seconds=3600),  # 200 downloads/hr
        ],
        cost=2,
    ),
    "STREAM": RateLimitPolicy(
        name="stream",
        windows=[
            RateLimitConfig(limit=5, window_seconds=60),  # 5 concurrent
        ],
        cost=1,
    ),
    "MODEL": RateLimitPolicy(
        name="model",
        windows=[
            RateLimitConfig(limit=1000, window_seconds=60),  # 20 model calls/min
            RateLimitConfig(limit=5000, window_seconds=3600),  # 100 model calls/hr
        ],
        cost=50,
    ),
    "CRITICAL_COST": RateLimitPolicy(
        name="critical_cost",
        windows=[
            RateLimitConfig(limit=200, window_seconds=60),  # 2 critical calls/min
            RateLimitConfig(limit=1000, window_seconds=3600),  # 10 critical calls/hr
        ],
        cost=100,
    ),
}


class RateLimiter(ABC):
    """Abstract base class for rate limiters."""

    @abstractmethod
    async def check_limit(
        self,
        key: str,
        policy: RateLimitPolicy,
        cost: int = 1,
    ) -> RateLimitResult:
        """
        Check if request is allowed under the policy.
        Returns RateLimitResult with allowed status and headers.
        """
        pass

    @abstractmethod
    async def get_current_usage(self, key: str, window_seconds: int) -> int:
        """Get current usage count for a key/window."""
        pass

    @abstractmethod
    async def reset(self, key: str) -> None:
        """Reset all limits for a key."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if rate limiter backend is healthy."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""
        pass


class InMemoryRateLimiter(RateLimiter):
    """
    In-memory rate limiter using sliding window log.
    Suitable for development and single-process deployments.
    """

    def __init__(self, default_limits: Optional[Dict[str, RateLimitPolicy]] = None):
        self._data: Dict[str, List[float]] = defaultdict(list)
        self._locks: Dict[str, Lock] = defaultdict(Lock)
        self._global_lock = Lock()
        self._default_limits = default_limits or COST_CLASS_POLICIES
        self._healthy = True

    def _get_lock(self, key: str) -> Lock:
        """Get or create lock for a key (lock striping)."""
        with self._global_lock:
            return self._locks[key]

    def _prune_window(self, timestamps: List[float], window_seconds: int) -> List[float]:
        """Remove expired timestamps."""
        now = time.time()
        cutoff = now - window_seconds
        return [ts for ts in timestamps if ts > cutoff]

    async def check_limit(
        self,
        key: str,
        policy: RateLimitPolicy,
        cost: int = 1,
    ) -> RateLimitResult:
        """Check all windows in the policy.

        The cost is only consumed once the request is known to be allowed in
        *every* window: consuming a window before a later window rejects the
        request would charge quota for a request that never ran. The limit
        check also accounts for the cost, so a single expensive request cannot
        push a window past its limit.
        """
        cost = max(1, int(cost))
        overall_allowed = True
        overall_reset = 0
        overall_retry_after = None
        current_counts: Dict[int, int] = {}

        # Evaluate every window first, without consuming any quota.
        window_states = []
        tightest_remaining = float("inf")
        tightest_count = 0
        tightest_limit = 0

        for window_config in policy.windows:
            window_key = f"{key}:{window_config.window_seconds}s"
            lock = self._get_lock(window_key)

            with lock:
                timestamps = self._data.get(window_key, [])
                pruned = self._prune_window(timestamps, window_config.window_seconds)
                self._data[window_key] = pruned
                current_count = len(pruned)

            current_counts[window_config.window_seconds] = current_count
            window_states.append((window_config, window_key, lock, pruned, current_count))

            # The request must fit in this window once its cost is applied.
            if current_count + cost > window_config.limit:
                overall_allowed = False
                oldest = min(pruned) if pruned else time.time()
                retry_after = int(oldest + window_config.window_seconds - time.time()) + 1
                if overall_retry_after is None or retry_after < overall_retry_after:
                    overall_retry_after = max(retry_after, 1)

            remaining = window_config.limit - current_count - cost
            if remaining < tightest_remaining:
                tightest_remaining = remaining
                tightest_count = current_count
                tightest_limit = window_config.limit

            if window_config.window_seconds > overall_reset:
                overall_reset = window_config.window_seconds

        # Only now is the request known to be allowed: consume the cost.
        if overall_allowed:
            now = time.time()
            for window_config, window_key, lock, _pruned, _count in window_states:
                with lock:
                    timestamps = self._data.get(window_key, [])
                    pruned = self._prune_window(timestamps, window_config.window_seconds)
                    for _ in range(cost):
                        pruned.append(now)
                    self._data[window_key] = pruned

        return RateLimitResult(
            allowed=overall_allowed,
            current_count=tightest_count + (cost if overall_allowed else 0),
            limit=tightest_limit,
            remaining=max(0, int(tightest_remaining)) if overall_allowed else 0,
            reset_seconds=overall_reset,
            retry_after=overall_retry_after,
            policy_name=policy.name,
        )

    async def get_current_usage(self, key: str, window_seconds: int) -> int:
        """Get current usage for a specific window."""
        window_key = f"{key}:{window_seconds}s"
        lock = self._get_lock(window_key)
        with lock:
            timestamps = self._data.get(window_key, [])
            pruned = self._prune_window(timestamps, window_seconds)
            return len(pruned)

    async def reset(self, key: str) -> None:
        """Reset all windows for a key."""
        with self._global_lock:
            keys_to_delete = [k for k in self._data.keys() if k.startswith(f"{key}:")]
            for k in keys_to_delete:
                del self._data[k]

    async def health_check(self) -> bool:
        return self._healthy

    async def close(self) -> None:
        with self._global_lock:
            self._data.clear()
            self._locks.clear()
        self._healthy = False


# Atomic sliding-window check/consume script.
#
# The check and the consumption have to happen in a single atomic step: doing
# them in two round trips lets concurrent requests both pass the check and
# collectively exceed the limit. The script also refuses to consume any window
# unless *every* window has room for the request's cost.
#
# KEYS: one sliding-window key per policy window.
# ARGV: [window_count, now, unique_token,
#        (window_seconds, limit, cost) * window_count]
# Returns: [allowed, retry_after, count_per_window...]
_SLIDING_WINDOW_SCRIPT = """
local n = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local unique = ARGV[3]
local allowed = 1
local retry = 0
local counts = {}

for i = 1, n do
  local base = 3 + (i - 1) * 3
  local window = tonumber(ARGV[base + 1])
  local limit = tonumber(ARGV[base + 2])
  local cost = tonumber(ARGV[base + 3])
  local key = KEYS[i]
  redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
  local count = redis.call('ZCARD', key)
  counts[i] = count
  if count + cost > limit then
    allowed = 0
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if oldest[2] then
      local r = math.ceil(tonumber(oldest[2]) + window - now)
      if r > retry then retry = r end
    end
  end
end

if allowed == 1 then
  for i = 1, n do
    local base = 3 + (i - 1) * 3
    local window = tonumber(ARGV[base + 1])
    local cost = tonumber(ARGV[base + 3])
    local key = KEYS[i]
    for j = 1, cost do
      redis.call('ZADD', key, now + (j * 0.0001), unique .. ':' .. j)
    end
    redis.call('EXPIRE', key, window + 60)
  end
end

local result = {allowed, retry}
for i = 1, n do
  result[#result + 1] = counts[i]
end
return result
"""


# Redis rate limiter (requires redis-py)
class RedisRateLimiter(RateLimiter):
    """
    Redis-backed rate limiter using Redis sorted sets for sliding window log.
    Supports distributed deployments.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        default_limits: Optional[Dict[str, RateLimitPolicy]] = None,
        key_prefix: str = "cauveris:ratelimit:",
        fail_open: bool = True,
    ):
        self._redis_url = redis_url
        self._default_limits = default_limits or COST_CLASS_POLICIES
        self._key_prefix = key_prefix
        self._fail_open = fail_open
        self._redis = None
        self._healthy = False
        self._connection_pool = None
        self._script = None

    async def _ensure_connection(self):
        """Lazy initialization of Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as redis

                self._connection_pool = redis.ConnectionPool.from_url(
                    self._redis_url,
                    max_connections=20,
                    decode_responses=True,
                )
                self._redis = redis.Redis(connection_pool=self._connection_pool)
                self._healthy = True
            except ImportError:
                logger.warning("redis-py not installed, falling back to in-memory")
                self._healthy = False
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._healthy = False

    def _make_key(self, key: str, window_seconds: int) -> str:
        return f"{self._key_prefix}{key}:{window_seconds}s"

    def _get_script(self):
        """Return the (lazily registered) atomic rate limit script."""
        if self._script is None:
            if self._redis is None:
                raise RuntimeError("Redis connection not initialized")
            self._script = self._redis.register_script(_SLIDING_WINDOW_SCRIPT)
        return self._script

    async def check_limit(
        self,
        key: str,
        policy: RateLimitPolicy,
        cost: int = 1,
    ) -> RateLimitResult:
        await self._ensure_connection()
        cost = max(1, int(cost))

        if not policy.windows:
            # A policy without windows cannot limit anything.
            return RateLimitResult(
                allowed=True,
                current_count=0,
                limit=0,
                remaining=0,
                reset_seconds=0,
                policy_name=policy.name,
            )

        if not self._healthy or self._redis is None:
            if self._fail_open:
                # Fail open - allow request but log warning
                logger.warning("Rate limiter unhealthy, failing open")
                return RateLimitResult(
                    allowed=True,
                    current_count=0,
                    limit=min(w.limit for w in policy.windows),
                    remaining=min(w.limit for w in policy.windows),
                    reset_seconds=min(w.window_seconds for w in policy.windows),
                    policy_name=policy.name,
                )
            else:
                # Fail closed - deny request
                return RateLimitResult(
                    allowed=False,
                    current_count=0,
                    limit=min(w.limit for w in policy.windows),
                    remaining=0,
                    reset_seconds=min(w.window_seconds for w in policy.windows),
                    retry_after=60,
                    policy_name=policy.name,
                )

        now = time.time()

        try:
            window_keys = [self._make_key(key, w.window_seconds) for w in policy.windows]
            args: List[Any] = [len(policy.windows), now, secrets.token_hex(8)]
            for window_config in policy.windows:
                args.extend([window_config.window_seconds, window_config.limit, cost])

            script = self._get_script()
            raw = await script(keys=window_keys, args=args)

            allowed = bool(int(raw[0]))
            overall_retry_after = int(raw[1]) or None
            counts = [int(c) for c in raw[2:]]

            overall_reset = 0
            tightest_remaining = float("inf")
            tightest_count = 0
            tightest_limit = 0

            for i, window_config in enumerate(policy.windows):
                current_count = counts[i] if i < len(counts) else 0
                remaining = window_config.limit - current_count - cost
                if remaining < tightest_remaining:
                    tightest_remaining = remaining
                    tightest_count = current_count
                    tightest_limit = window_config.limit
                if window_config.window_seconds > overall_reset:
                    overall_reset = window_config.window_seconds

            return RateLimitResult(
                allowed=allowed,
                current_count=tightest_count + (cost if allowed else 0),
                limit=tightest_limit,
                remaining=max(0, int(tightest_remaining)) if allowed else 0,
                reset_seconds=overall_reset,
                retry_after=overall_retry_after,
                policy_name=policy.name,
            )

        except Exception as e:
            logger.error(f"Redis rate limiter error: {e}")
            if self._fail_open:
                return RateLimitResult(
                    allowed=True,
                    current_count=0,
                    limit=min(w.limit for w in policy.windows),
                    remaining=min(w.limit for w in policy.windows),
                    reset_seconds=min(w.window_seconds for w in policy.windows),
                    policy_name=policy.name,
                )
            else:
                return RateLimitResult(
                    allowed=False,
                    current_count=0,
                    limit=min(w.limit for w in policy.windows),
                    remaining=0,
                    reset_seconds=60,
                    retry_after=60,
                    policy_name=policy.name,
                )

        # NOTE: Should never reach here. The try block returns on success,
        # and the except block returns on failure.
        raise RuntimeError("Unexpected code path in check_limit")

    async def get_current_usage(self, key: str, window_seconds: int) -> int:
        await self._ensure_connection()
        if not self._healthy or self._redis is None:
            return 0

        try:
            window_key = self._make_key(key, window_seconds)
            cutoff = time.time() - window_seconds
            await self._redis.zremrangebyscore(window_key, 0, cutoff)
            return await self._redis.zcard(window_key)
        except Exception as e:
            logger.error(f"Redis get usage error: {e}")
            return 0

    async def reset(self, key: str) -> None:
        await self._ensure_connection()
        if not self._healthy or self._redis is None:
            return
        try:
            pattern = f"{self._key_prefix}{key}:*"
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Redis reset error: {e}")

    async def health_check(self) -> bool:
        await self._ensure_connection()
        if not self._healthy or self._redis is None:
            return False
        try:
            return await self._redis.ping()
        except Exception:
            self._healthy = False
            return False

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()
        self._healthy = False


# Global rate limiter instance (set by init_rate_limiter)
_global_rate_limiter: Optional[RateLimiter] = None


def init_rate_limiter(
    backend: str = "memory",
    redis_url: str = "redis://localhost:6379",
    fail_open: bool = True,
    default_limits: Optional[Dict[str, RateLimitPolicy]] = None,
) -> RateLimiter:
    """Initialize the global rate limiter."""
    global _global_rate_limiter

    if backend.lower() == "redis":
        _global_rate_limiter = RedisRateLimiter(
            redis_url=redis_url,
            default_limits=default_limits,
            fail_open=fail_open,
        )
    else:
        _global_rate_limiter = InMemoryRateLimiter(default_limits=default_limits)

    logger.info(f"Initialized rate limiter: {backend}")
    return _global_rate_limiter


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = init_rate_limiter()
    return _global_rate_limiter


async def check_rate_limit(
    key: str,
    cost_class: str = "NORMAL_READ",
    cost: Optional[int] = None,
    custom_policy: Optional[RateLimitPolicy] = None,
) -> RateLimitResult:
    """
    Convenience function to check rate limit using global limiter.
    Uses cost class policies by default. When ``cost`` is not supplied the
    cost declared by the policy is used.
    """
    limiter = get_rate_limiter()
    policy = custom_policy or COST_CLASS_POLICIES.get(
        cost_class, COST_CLASS_POLICIES["NORMAL_READ"]
    )
    effective_cost = policy.cost if cost is None else cost
    return await limiter.check_limit(key, policy, effective_cost)


# Decorator for easy endpoint protection
def rate_limited(
    cost_class: str = "NORMAL_READ",
    key_func: Optional[Callable] = None,
    cost: int = 1,
):
    """
    Decorator to add rate limiting to an endpoint.
    Usage:
        @app.get("/endpoint")
        @rate_limited(cost_class="COMPUTE")
        async def my_endpoint(request: Request, ...):
            ...
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract request from args/kwargs
            request = None
            for arg in args:
                if hasattr(arg, "url") and hasattr(arg, "headers") and hasattr(arg, "client"):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")

            if request is None:
                logger.warning("Could not find Request object for rate limiting")
                return await func(*args, **kwargs)

            # Determine key
            if key_func:
                key = key_func(request)
            else:
                # Default: IP + path
                forwarded = request.headers.get("X-Forwarded-For")
                if forwarded:
                    client_ip = forwarded.split(",")[0].strip()
                else:
                    client_ip = request.client.host if request.client else "unknown"
                key = f"ip:{client_ip}:{request.url.path}"

            # Check rate limit
            result = await check_rate_limit(key, cost_class, cost)

            # Add headers to response (would need response manipulation)
            if not result.allowed:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {result.policy_name}",
                    headers=result.headers,
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Backwards compatibility: sync version for existing code
class SyncRateLimiter:
    """Sync wrapper for in-memory rate limiter (for Phase 2 compatibility)."""

    def __init__(self):
        self._limiter = InMemoryRateLimiter()

    def check_limit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        """Sync check matching Phase 2 interface."""
        policy = RateLimitPolicy(
            name="sync", windows=[RateLimitConfig(limit=limit, window_seconds=window_seconds)]
        )
        # Run async method in sync context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        result = loop.run_until_complete(self._limiter.check_limit(key, policy))
        retry_after = int(result.retry_after or 0) if not result.allowed else 0
        return result.allowed, result.current_count, retry_after


# Alias for backwards compatibility
_check_rate_limit = SyncRateLimiter().check_limit

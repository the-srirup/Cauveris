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
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, List, Callable
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


# Cost class definitions mapping endpoints to policies
COST_CLASS_POLICIES: Dict[str, RateLimitPolicy] = {
    "LOW_COST": RateLimitPolicy(
        name="low_cost",
        windows=[
            RateLimitConfig(limit=100, window_seconds=60),      # 100/min
            RateLimitConfig(limit=1000, window_seconds=3600),   # 1000/hr
        ],
    ),
    "NORMAL_READ": RateLimitPolicy(
        name="normal_read",
        windows=[
            RateLimitConfig(limit=60, window_seconds=60),       # 60/min
            RateLimitConfig(limit=500, window_seconds=3600),    # 500/hr
        ],
    ),
    "PUBLIC_READ": RateLimitPolicy(
        name="public_read",
        windows=[
            RateLimitConfig(limit=200, window_seconds=60),      # 200/min
            RateLimitConfig(limit=2000, window_seconds=3600),   # 2000/hr
        ],
    ),
    "MUTATION": RateLimitPolicy(
        name="mutation",
        windows=[
            RateLimitConfig(limit=30, window_seconds=60),       # 30/min
            RateLimitConfig(limit=200, window_seconds=3600),    # 200/hr
        ],
        cost=1,
    ),
    "UPLOAD": RateLimitPolicy(
        name="upload",
        windows=[
            RateLimitConfig(limit=10, window_seconds=60),       # 10/min
            RateLimitConfig(limit=50, window_seconds=3600),     # 50/hr
        ],
        cost=5,
    ),
    "COMPUTE": RateLimitPolicy(
        name="compute",
        windows=[
            RateLimitConfig(limit=5, window_seconds=60),        # 5/min
            RateLimitConfig(limit=30, window_seconds=3600),     # 30/hr
        ],
        cost=10,
    ),
    "EXPERIMENT": RateLimitPolicy(
        name="experiment",
        windows=[
            RateLimitConfig(limit=3, window_seconds=60),        # 3/min
            RateLimitConfig(limit=10, window_seconds=3600),     # 10/hr
        ],
        cost=20,
    ),
    "PATCH": RateLimitPolicy(
        name="patch",
        windows=[
            RateLimitConfig(limit=5, window_seconds=60),        # 5/min
            RateLimitConfig(limit=20, window_seconds=3600),     # 20/hr
        ],
        cost=15,
    ),
    "DOWNLOAD": RateLimitPolicy(
        name="download",
        windows=[
            RateLimitConfig(limit=20, window_seconds=60),       # 20/min
            RateLimitConfig(limit=200, window_seconds=3600),    # 200/hr
        ],
        cost=2,
    ),
    "STREAM": RateLimitPolicy(
        name="stream",
        windows=[
            RateLimitConfig(limit=5, window_seconds=60),        # 5 concurrent
        ],
        cost=1,
    ),
    "MODEL": RateLimitPolicy(
        name="model",
        windows=[
            RateLimitConfig(limit=20, window_seconds=60),       # 20/min
            RateLimitConfig(limit=100, window_seconds=3600),    # 100/hr
        ],
        cost=50,
    ),
    "CRITICAL_COST": RateLimitPolicy(
        name="critical_cost",
        windows=[
            RateLimitConfig(limit=2, window_seconds=60),        # 2/min
            RateLimitConfig(limit=10, window_seconds=3600),     # 10/hr
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
        """Check all windows in the policy."""
        overall_allowed = True
        overall_remaining = float('inf')
        overall_reset = 0
        overall_retry_after = None
        current_counts = {}

        for window_config in policy.windows:
            window_key = f"{key}:{window_config.window_seconds}s"
            lock = self._get_lock(window_key)

            with lock:
                timestamps = self._data.get(window_key, [])
                pruned = self._prune_window(timestamps, window_config.window_seconds)
                self._data[window_key] = pruned

                current_count = len(pruned)
                current_counts[window_config.window_seconds] = current_count

                remaining = window_config.limit - current_count
                if remaining < overall_remaining:
                    overall_remaining = remaining

                if current_count >= window_config.limit:
                    overall_allowed = False
                    oldest = min(pruned) if pruned else time.time()
                    retry_after = int(oldest + window_config.window_seconds - time.time()) + 1
                    if overall_retry_after is None or retry_after < overall_retry_after:
                        overall_retry_after = max(retry_after, 1)

                reset_seconds = window_config.window_seconds
                if reset_seconds > overall_reset:
                    overall_reset = reset_seconds

                # If allowed, add the timestamp(s) for the cost
                if overall_allowed:
                    for _ in range(cost):
                        pruned.append(time.time())

        return RateLimitResult(
            allowed=overall_allowed,
            current_count=max(current_counts.values()) if current_counts else 0,
            limit=min(w.limit for w in policy.windows),
            remaining=max(0, int(overall_remaining)) if overall_allowed else 0,
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

    async def check_limit(
        self,
        key: str,
        policy: RateLimitPolicy,
        cost: int = 1,
    ) -> RateLimitResult:
        await self._ensure_connection()

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
        overall_allowed = True
        overall_remaining = float('inf')
        overall_reset = 0
        overall_retry_after = None
        current_counts = {}

        try:
            # Use pipeline for atomic operations
            pipe = self._redis.pipeline()

            for window_config in policy.windows:
                window_key = self._make_key(key, window_config.window_seconds)
                cutoff = now - window_config.window_seconds

                # Remove expired entries
                pipe.zremrangebyscore(window_key, 0, cutoff)

                # Count current entries
                pipe.zcard(window_key)

                # If we're going to add entries, prepare them
                # We'll add after checking all windows

            results = await pipe.execute()

            for i, window_config in enumerate(policy.windows):
                current_count = results[i * 2 + 1]  # zcard result
                current_counts[window_config.window_seconds] = current_count

                remaining = window_config.limit - current_count
                if remaining < overall_remaining:
                    overall_remaining = remaining

                if current_count >= window_config.limit:
                    overall_allowed = False
                    # Get oldest entry to calculate retry-after
                    window_key = self._make_key(key, window_config.window_seconds)
                    oldest_entries = await self._redis.zrange(window_key, 0, 0, withscores=True)
                    if oldest_entries:
                        oldest = oldest_entries[0][1]
                        retry_after = int(oldest + window_config.window_seconds - now) + 1
                        if overall_retry_after is None or retry_after < overall_retry_after:
                            overall_retry_after = max(retry_after, 1)

                reset_seconds = window_config.window_seconds
                if reset_seconds > overall_reset:
                    overall_reset = reset_seconds

            # If allowed, add new entries
            if overall_allowed:
                pipe = self._redis.pipeline()
                for window_config in policy.windows:
                    window_key = self._make_key(key, window_config.window_seconds)
                    for j in range(cost):
                        # Use timestamp + small offset to ensure uniqueness
                        score = now + (j * 0.001)
                        member = f"{now}:{j}"
                        pipe.zadd(window_key, {member: score})
                        # Set TTL to window + buffer
                        pipe.expire(window_key, window_config.window_seconds + 60)
                await pipe.execute()

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

        return RateLimitResult(
            allowed=overall_allowed,
            current_count=max(current_counts.values()) if current_counts else 0,
            limit=min(w.limit for w in policy.windows),
            remaining=max(0, int(overall_remaining)) if overall_allowed else 0,
            reset_seconds=overall_reset,
            retry_after=overall_retry_after,
            policy_name=policy.name,
        )

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
    cost: int = 1,
    custom_policy: Optional[RateLimitPolicy] = None,
) -> RateLimitResult:
    """
    Convenience function to check rate limit using global limiter.
    Uses cost class policies by default.
    """
    limiter = get_rate_limiter()
    policy = custom_policy or COST_CLASS_POLICIES.get(cost_class, COST_CLASS_POLICIES["NORMAL_READ"])
    return await limiter.check_limit(key, policy, cost)


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
            name="sync",
            windows=[RateLimitConfig(limit=limit, window_seconds=window_seconds)]
        )
        # Run async method in sync context
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        result = loop.run_until_complete(self._limiter.check_limit(key, policy))
        return result.allowed, result.current_count, result.retry_after if not result.allowed else 0


# Alias for backwards compatibility
_check_rate_limit = SyncRateLimiter().check_limit

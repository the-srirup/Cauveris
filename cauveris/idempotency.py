"""
Idempotency Key Support for Cauveris.

Provides duplicate request prevention for mutation endpoints using Idempotency-Key header.
- Stores: key, caller, operation, request hash, response reference, state, timestamps
- Returns 409 on key reuse with different body
- TTL-based cleanup of old records
- Supports both in-memory and Redis backends
"""

import time
import hashlib
import json
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum
from threading import Lock
import logging
from fastapi import Request, Response
from fastapi.responses import Response as FastAPIResponse

logger = logging.getLogger(__name__)


class IdempotencyState(Enum):
    """State of an idempotency record."""
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IdempotencyRecord:
    """Record of an idempotent request."""
    key: str
    caller_id: str
    operation: str
    request_hash: str
    request_body: str
    response_body: Optional[str] = None
    response_status: Optional[int] = None
    response_headers: Optional[Dict[str, str]] = None
    state: IdempotencyState = IdempotencyState.PROCESSING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    expires_at: float = field(default_factory=lambda: time.time() + 86400)  # 24h default TTL


class IdempotencyStore(ABC):
    """Abstract base class for idempotency key storage."""

    @abstractmethod
    async def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Get record by key."""
        pass

    @abstractmethod
    async def set(self, record: IdempotencyRecord) -> bool:
        """Store new record. Returns False if key exists."""
        pass

    @abstractmethod
    async def update(self, key: str, response_body: str, status: int, headers: Dict[str, str], state: IdempotencyState = IdempotencyState.COMPLETED) -> bool:
        """Update record with response. Returns True if updated."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete record. Returns True if deleted."""
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove expired records. Returns count removed."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check storage health."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connections."""
        pass


class InMemoryIdempotencyStore(IdempotencyStore):
    """In-memory idempotency store with TTL cleanup."""

    def __init__(self, default_ttl: int = 86400, cleanup_interval: int = 3600):
        self._data: Dict[str, IdempotencyRecord] = {}
        self._lock = Lock()
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None
        self._healthy = True

    async def start_cleanup_task(self):
        """Start background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """Background task to clean expired records."""
        while self._healthy:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Idempotency cleanup error: {e}")

    async def _ensure_cleanup_task(self):
        """Ensure cleanup task is running."""
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            except RuntimeError:
                # No event loop, will try later
                pass

    async def get(self, key: str) -> Optional[IdempotencyRecord]:
        await self._ensure_cleanup_task()
        with self._lock:
            record = self._data.get(key)
            if record and record.expires_at < time.time():
                # Expired
                del self._data[key]
                return None
            return record

    async def set(self, record: IdempotencyRecord) -> bool:
        with self._lock:
            if record.key in self._data:
                return False
            self._data[record.key] = record
            return True

    async def update(self, key: str, response_body: str, status: int, headers: Dict[str, str], state: IdempotencyState = IdempotencyState.COMPLETED) -> bool:
        with self._lock:
            record = self._data.get(key)
            if not record:
                return False
            record.response_body = response_body
            record.response_status = status
            record.response_headers = headers
            record.state = state
            record.completed_at = time.time()
            return True

    async def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    async def cleanup_expired(self) -> int:
        now = time.time()
        removed = 0
        with self._lock:
            expired_keys = [k for k, v in self._data.items() if v.expires_at < now]
            for k in expired_keys:
                del self._data[k]
                removed += 1
        if removed > 0:
            logger.debug(f"Cleaned up {removed} expired idempotency records")
        return removed

    async def health_check(self) -> bool:
        return self._healthy

    async def close(self) -> None:
        self._healthy = False
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


class RedisIdempotencyStore(IdempotencyStore):
    """Redis-backed idempotency store for distributed deployments."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "cauveris:idempotency:",
        default_ttl: int = 86400,
    ):
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl
        self._redis = None
        self._healthy = False

    async def _ensure_connection(self):
        if self._redis is None:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(self._redis_url, decode_responses=True)
                self._healthy = True
            except ImportError:
                logger.warning("redis-py not installed, cannot use RedisIdempotencyStore")
                self._healthy = False
            except Exception as e:
                logger.error(f"Failed to connect to Redis for idempotency: {e}")
                self._healthy = False

    def _make_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    async def get(self, key: str) -> Optional[IdempotencyRecord]:
        await self._ensure_connection()
        if not self._healthy or self._redis is None:
            return None

        try:
            data = await self._redis.get(self._make_key(key))
            if data is None:
                return None
            record_data = json.loads(data)
            # Check expiry
            if record_data.get("expires_at", 0) < time.time():
                await self._redis.delete(self._make_key(key))
                return None
            # Convert to record
            return IdempotencyRecord(
                key=record_data["key"],
                caller_id=record_data["caller_id"],
                operation=record_data["operation"],
                request_hash=record_data["request_hash"],
                request_body=record_data["request_body"],
                response_body=record_data.get("response_body"),
                response_status=record_data.get("response_status"),
                response_headers=record_data.get("response_headers"),
                state=IdempotencyState(record_data["state"]),
                created_at=record_data["created_at"],
                completed_at=record_data.get("completed_at"),
                expires_at=record_data["expires_at"],
            )
        except Exception as e:
            logger.error(f"Redis idempotency get error: {e}")
            return None

    async def set(self, record: IdempotencyRecord) -> bool:
        await self._ensure_connection()
        if not self._healthy or self._redis is None:
            return False

        try:
            key = self._make_key(record.key)
            # Use SET NX for atomic check-and-set
            data = json.dumps({
                "key": record.key,
                "caller_id": record.caller_id,
                "operation": record.operation,
                "request_hash": record.request_hash,
                "request_body": record.request_body,
                "response_body": record.response_body,
                "response_status": record.response_status,
                "response_headers": record.response_headers,
                "state": record.state.value,
                "created_at": record.created_at,
                "completed_at": record.completed_at,
                "expires_at": record.expires_at,
            })
            # SET with NX (only if not exists) and EX (expiry)
            ttl = int(record.expires_at - time.time())
            if ttl <= 0:
                ttl = self._default_ttl
            result = await self._redis.set(key, data, nx=True, ex=ttl)
            return result is True
        except Exception as e:
            logger.error(f"Redis idempotency set error: {e}")
            return False

    async def update(self, key: str, response_body: str, status: int, headers: Dict[str, str], state: IdempotencyState = IdempotencyState.COMPLETED) -> bool:
        await self._ensure_connection()
        if not self._healthy or self._redis is None:
            return False

        try:
            redis_key = self._make_key(key)
            # Get existing
            data = await self._redis.get(redis_key)
            if data is None:
                return False
            record_data = json.loads(data)

            # Update
            record_data["response_body"] = response_body
            record_data["response_status"] = status
            record_data["response_headers"] = headers
            record_data["state"] = state.value
            record_data["completed_at"] = time.time()

            # Save with same TTL
            ttl = int(record_data["expires_at"] - time.time())
            if ttl <= 0:
                ttl = self._default_ttl

            await self._redis.set(redis_key, json.dumps(record_data), ex=ttl)
            return True
        except Exception as e:
            logger.error(f"Redis idempotency update error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        await self._ensure_connection()
        if not self._healthy or self._redis is None:
            return False
        try:
            result = await self._redis.delete(self._make_key(key))
            return result > 0
        except Exception as e:
            logger.error(f"Redis idempotency delete error: {e}")
            return False

    async def cleanup_expired(self) -> int:
        # Redis handles expiry automatically via TTL
        return 0

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
        self._healthy = False


# Global store instance
_global_idempotency_store: Optional[IdempotencyStore] = None


def init_idempotency_store(
    backend: str = "memory",
    redis_url: str = "redis://localhost:6379",
    default_ttl: int = 86400,
) -> IdempotencyStore:
    """Initialize the global idempotency store."""
    global _global_idempotency_store

    if backend.lower() == "redis":
        _global_idempotency_store = RedisIdempotencyStore(
            redis_url=redis_url,
            default_ttl=default_ttl,
        )
    else:
        store = InMemoryIdempotencyStore(default_ttl=default_ttl)
        # Cleanup task will be started on first async operation
        _global_idempotency_store = store

    logger.info(f"Initialized idempotency store: {backend}")
    return _global_idempotency_store


def get_idempotency_store() -> Optional[IdempotencyStore]:
    """Get the global idempotency store instance. Auto-initializes if needed."""
    global _global_idempotency_store
    if _global_idempotency_store is None:
        from cauveris.config import get_settings
        settings = get_settings()
        if settings.idempotency_enabled:
            init_idempotency_store(
                backend=settings.idempotency_backend,
                redis_url=settings.idempotency_redis_url,
                default_ttl=settings.idempotency_ttl_seconds,
            )
    return _global_idempotency_store


def compute_request_hash(body: bytes, method: str, path: str) -> str:
    """Compute SHA256 hash of request for deduplication."""
    content = f"{method}:{path}:{body.decode('utf-8', errors='ignore')}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


async def check_idempotency(
    request: Request,
    idempotency_key: str,
    operation: str,
    store: Optional[IdempotencyStore] = None,
) -> tuple[bool, Optional[Dict[str, Any]], Optional["Response"]]:
    """
    Check idempotency key.
    Returns: (should_process, existing_response, error_response)
    - should_process=True: no existing key, caller should process request
    - should_process=False with existing_response: return cached response
    - error_response: FastAPI Response to return (409 conflict)
    """
    if store is None:
        store = get_idempotency_store()
    if store is None:
        return True, None, None  # No store configured, allow

    # Get caller identity
    caller_id = getattr(request.state, "user_id", None) or getattr(request.state, "client_ip", "unknown")

    record = await store.get(idempotency_key)
    if record is None:
        # No existing record, create pending one
        body = await request.body()
        request_hash = compute_request_hash(body, request.method, str(request.url.path))
        new_record = IdempotencyRecord(
            key=idempotency_key,
            caller_id=caller_id,
            operation=operation,
            request_hash=request_hash,
            request_body=body.decode('utf-8', errors='ignore'),
            state=IdempotencyState.PROCESSING,
        )
        created = await store.set(new_record)
        if not created:
            # Race condition - another request created it
            record = await store.get(idempotency_key)
            if record:
                return await check_idempotency(request, idempotency_key, operation, store)
        return True, None, None

    # Record exists - check if same request
    body = await request.body()
    request_hash = compute_request_hash(body, request.method, str(request.url.path))

    if record.request_hash != request_hash:
        # Different request with same key - conflict!
        from fastapi import Response
        error_body = json.dumps({
            "error": "Idempotency key conflict",
            "message": f"Key '{idempotency_key}' was used with a different request",
            "existing_operation": record.operation,
        })
        return False, None, Response(
            content=error_body,
            status_code=409,
            media_type="application/json",
            headers={"X-Idempotency-Conflict": "true"},
        )

    # Same request - check state
    if record.state == IdempotencyState.PROCESSING:
        # Still processing - caller should wait or retry
        from fastapi import Response
        error_body = json.dumps({
            "error": "Request still processing",
            "message": f"Request with key '{idempotency_key}' is still being processed",
            "retry_after": 5,
        })
        return False, None, Response(
            content=error_body,
            status_code=409,
            media_type="application/json",
            headers={"Retry-After": "5", "X-Idempotency-Processing": "true"},
        )

    elif record.state == IdempotencyState.COMPLETED:
        # Return cached response
        from fastapi import Response
        headers = record.response_headers or {}
        headers["X-Idempotency-Replay"] = "true"
        return False, {
            "body": record.response_body,
            "status": record.response_status,
            "headers": headers,
        }, None

    elif record.state == IdempotencyState.FAILED:
        # Previous attempt failed - allow retry with same key?
        # For now, allow retry by deleting and creating new
        await store.delete(idempotency_key)
        return await check_idempotency(request, idempotency_key, operation, store)

    return True, None, None


async def save_idempotent_response(
    idempotency_key: str,
    response_body: str,
    status: int,
    headers: Dict[str, str],
    state: IdempotencyState = IdempotencyState.COMPLETED,
    store: Optional[IdempotencyStore] = None,
) -> bool:
    """Save response for idempotency key."""
    if store is None:
        store = get_idempotency_store()
    if store is None:
        return True
    return await store.update(idempotency_key, response_body, status, headers, state)


# Middleware helper - Request and Response already imported at top


async def idempotency_middleware(request: Request, call_next):
    """
    Middleware to handle idempotency for mutation endpoints.
    Only applies to endpoints that opt-in via route dependencies or path matching.
    """
    # Skip if not a mutation method
    if request.method not in ["POST", "PUT", "PATCH", "DELETE"]:
        return await call_next(request)

    # Check for Idempotency-Key header
    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return await call_next(request)

    # Validate key format (alphanumeric, hyphen, underscore, max 256 chars)
    import re
    if not re.match(r'^[a-zA-Z0-9_-]{1,256}$', idempotency_key):
        from fastapi import Response
        return Response(
            content=json.dumps({"error": "Invalid Idempotency-Key format"}),
            status_code=400,
            media_type="application/json",
        )

    # Determine operation name from path
    operation = f"{request.method}:{request.url.path}"

    # Check idempotency
    should_process, cached, error = await check_idempotency(request, idempotency_key, operation)
    if error:
        return error

    if cached:
        # Return cached response
        return FastAPIResponse(
            content=cached["body"],
            status_code=cached["status"],
            headers=cached["headers"],
            media_type="application/json",
        )

    # Process request
    response = await call_next(request)

    # Save response for idempotency (only for successful responses)
    if response.status_code < 500:
        # Need to read response body
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk

        # Save for future replays
        await save_idempotent_response(
            idempotency_key,
            response_body.decode('utf-8', errors='ignore'),
            response.status_code,
            dict(response.headers),
            IdempotencyState.COMPLETED if response.status_code < 400 else IdempotencyState.FAILED,
        )

        # Return new response with same body
        return FastAPIResponse(
            content=response_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    return response


# Decorator for explicit endpoint control
def idempotent(operation_name: Optional[str] = None):
    """
    Decorator to add idempotency to an endpoint.
    Usage:
        @app.post("/endpoint")
        @idempotent("create_incident")
        async def my_endpoint(request: Request, ...):
            ...
    """
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            idempotency_key = request.headers.get("Idempotency-Key")
            if not idempotency_key:
                return await func(request, *args, **kwargs)

            operation = operation_name or f"{request.method}:{request.url.path}"
            should_process, cached, error = await check_idempotency(request, idempotency_key, operation)
            if error:
                return error
            if cached:
                from fastapi import Response
                return Response(
                    content=cached["body"],
                    status_code=cached["status"],
                    headers=cached["headers"],
                    media_type="application/json",
                )

            response = await func(request, *args, **kwargs)

            # Save response
            if hasattr(response, 'body'):
                body = response.body
            elif hasattr(response, 'body_iterator'):
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
            else:
                body = b""

            if response.status_code < 500:
                await save_idempotent_response(
                    idempotency_key,
                    body.decode('utf-8', errors='ignore'),
                    response.status_code,
                    dict(response.headers),
                    IdempotencyState.COMPLETED if response.status_code < 400 else IdempotencyState.FAILED,
                )

            return response
        return wrapper
    return decorator

"""
Concurrency Limits (Phase 5)
Semaphore-based capacity acquisition for expensive operations with:
- Per-user/org/incident/global limits
- Heartbeats and stale-job recovery
- Automatic release on success/failure/timeout/cancellation
"""
import asyncio
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, Optional
import logging

from cauveris.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ConcurrencySlot:
    """A reserved concurrency slot."""
    key: str
    owner_id: str
    acquired_at: float
    heartbeat_at: float
    metadata: Dict = field(default_factory=dict)


class ConcurrencyStore(ABC):
    """Abstract backend for concurrency tracking."""

    @abstractmethod
    async def acquire(self, key: str, owner_id: str, limit: int, timeout: float) -> Optional[ConcurrencySlot]:
        """Try to acquire a slot. Returns slot if acquired, None if timeout."""
        pass

    @abstractmethod
    async def release(self, key: str, owner_id: str) -> bool:
        """Release a slot. Returns True if released."""
        pass

    @abstractmethod
    async def heartbeat(self, key: str, owner_id: str) -> bool:
        """Update heartbeat timestamp. Returns True if slot exists."""
        pass

    @abstractmethod
    async def get_slot(self, key: str, owner_id: str) -> Optional[ConcurrencySlot]:
        """Get current slot info."""
        pass

    @abstractmethod
    async def list_slots(self, key: str) -> list[ConcurrencySlot]:
        """List all slots for a key (for monitoring)."""
        pass

    @abstractmethod
    async def cleanup_stale(self, stale_threshold: float) -> int:
        """Remove slots with heartbeat older than threshold. Returns count removed."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if store is healthy."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connections."""
        pass


class InMemoryConcurrencyStore(ConcurrencyStore):
    """In-memory implementation for single-process deployments."""

    def __init__(self):
        self._slots: Dict[str, Dict[str, ConcurrencySlot]] = {}  # key -> {owner_id: slot}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._waiting: Dict[str, Dict[str, asyncio.Event]] = {}  # key -> {owner_id: event}
        self._cleanup_task: Optional[asyncio.Task] = None

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def acquire(self, key: str, owner_id: str, limit: int, timeout: float) -> Optional[ConcurrencySlot]:
        lock = self._get_lock(key)
        start_time = time.time()

        while time.time() - start_time < timeout:
            async with lock:
                slots = self._slots.get(key, {})

                # Check if owner already has a slot
                if owner_id in slots:
                    slot = slots[owner_id]
                    slot.heartbeat_at = time.time()
                    return slot

                # Check capacity
                if len(slots) < limit:
                    now = time.time()
                    slot = ConcurrencySlot(
                        key=key,
                        owner_id=owner_id,
                        acquired_at=now,
                        heartbeat_at=now,
                    )
                    slots[owner_id] = slot
                    self._slots[key] = slots
                    logger.debug(f"Acquired concurrency slot: {key} for {owner_id} ({len(slots)}/{limit})")
                    return slot

                # Need to wait - create event if not exists
                if key not in self._waiting:
                    self._waiting[key] = {}
                if owner_id not in self._waiting[key]:
                    self._waiting[key][owner_id] = asyncio.Event()

                wait_event = self._waiting[key][owner_id]

            # Wait outside lock
            try:
                wait_task = asyncio.create_task(wait_event.wait())
                remaining = timeout - (time.time() - start_time)
                done, pending = await asyncio.wait(
                    [wait_task],
                    timeout=min(remaining, 0.5),
                    return_when=asyncio.FIRST_COMPLETED
                )
                for p in pending:
                    p.cancel()
            except asyncio.CancelledError:
                # Clean up wait event
                async with lock:
                    if key in self._waiting and owner_id in self._waiting[key]:
                        del self._waiting[key][owner_id]
                raise

        return None  # Timeout

    async def release(self, key: str, owner_id: str) -> bool:
        lock = self._get_lock(key)
        async with lock:
            slots = self._slots.get(key, {})
            if owner_id in slots:
                del slots[owner_id]
                logger.debug(f"Released concurrency slot: {key} for {owner_id} ({len(slots)} slots)")

                # Notify waiting owners
                if key in self._waiting:
                    for waiting_owner, event in self._waiting[key].items():
                        if not event.is_set():
                            event.set()
                            break  # Only wake one

                return True
            return False

    async def heartbeat(self, key: str, owner_id: str) -> bool:
        lock = self._get_lock(key)
        async with lock:
            slots = self._slots.get(key, {})
            if owner_id in slots:
                slots[owner_id].heartbeat_at = time.time()
                return True
            return False

    async def get_slot(self, key: str, owner_id: str) -> Optional[ConcurrencySlot]:
        lock = self._get_lock(key)
        async with lock:
            slots = self._slots.get(key, {})
            return slots.get(owner_id)

    async def list_slots(self, key: str) -> list[ConcurrencySlot]:
        lock = self._get_lock(key)
        async with lock:
            slots = self._slots.get(key, {})
            return list(slots.values())

    async def cleanup_stale(self, stale_threshold: float) -> int:
        removed = 0
        lock = self._get_lock("__cleanup__")
        async with lock:
            for key in list(self._slots.keys()):
                if key == "__cleanup__":
                    continue
                slots = self._slots[key]
                stale_owners = [
                    owner_id for owner_id, slot in slots.items()
                    if slot.heartbeat_at < stale_threshold
                ]
                for owner_id in stale_owners:
                    del slots[owner_id]
                    removed += 1
                    logger.warning(f"Cleaned up stale concurrency slot: {key} for {owner_id}")
        return removed

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


class ConcurrencyManager:
    """Manages concurrency limits for different operation types."""

    def __init__(self, store: ConcurrencyStore):
        self._store = store
        self._limits: Dict[str, int] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    def set_limit(self, scope: str, limit: int) -> None:
        """Set concurrency limit for a scope (e.g., 'pipeline', 'simulation', 'model')."""
        self._limits[scope] = max(1, limit)

    def get_limit(self, scope: str) -> int:
        """Get concurrency limit for a scope."""
        return self._limits.get(scope, 1)

    @asynccontextmanager
    async def acquire(self, scope: str, owner_id: str, timeout: Optional[float] = None, metadata: Optional[Dict] = None):
        """
        Acquire a concurrency slot.

        Usage:
            async with manager.acquire("pipeline", "user-123") as slot:
                # Do work

        Raises:
            ConcurrencyLimitExceeded: If timeout exceeded
        """
        limit = self._limits.get(scope, 1)
        timeout = timeout or get_settings().concurrency_acquire_timeout

        slot = await self._store.acquire(scope, owner_id, limit, timeout)
        if slot is None:
            raise ConcurrencyLimitExceeded(
                f"Concurrency limit exceeded for {scope} (limit={limit}), "
                f"timeout after {timeout}s"
            )

        if metadata:
            slot.metadata.update(metadata)

        try:
            yield slot
        except Exception:
            # Release on any exception
            await self._store.release(scope, owner_id)
            raise
        else:
            # Release on success
            await self._store.release(scope, owner_id)

    async def heartbeat(self, scope: str, owner_id: str) -> bool:
        """Send heartbeat for a slot."""
        return await self._store.heartbeat(scope, owner_id)

    async def start_heartbeats(self, interval: float = 30.0) -> None:
        """Start background heartbeat task to keep slots alive."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return

        async def heartbeat_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    # Heartbeats are called explicitly by workers, not automatically
                    # This is a placeholder for future global heartbeat coordination
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Heartbeat loop error: {e}")

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def start_cleanup(self, stale_threshold: float = 300.0, interval: float = 60.0) -> None:
        """Start background stale-slot cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            return

        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    removed = await self._store.cleanup_stale(time.time() - stale_threshold)
                    if removed:
                        logger.info(f"Cleaned up {removed} stale concurrency slots")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Cleanup loop error: {e}")

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def stop_background_tasks(self) -> None:
        """Stop all background tasks."""
        for task in [self._heartbeat_task, self._cleanup_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def get_stats(self, scope: str) -> Dict:
        """Get concurrency stats for a scope."""
        slots = await self._store.list_slots(scope)
        limit = self.get_limit(scope)
        return {
            "scope": scope,
            "limit": limit,
            "active": len(slots),
            "available": max(0, limit - len(slots)),
            "slots": [
                {
                    "owner_id": s.owner_id,
                    "acquired_at": s.acquired_at,
                    "heartbeat_at": s.heartbeat_at,
                    "age_seconds": time.time() - s.acquired_at,
                    "idle_seconds": time.time() - s.heartbeat_at,
                    "metadata": s.metadata,
                }
                for s in slots
            ]
        }


class ConcurrencyLimitExceeded(Exception):
    """Raised when concurrency limit is exceeded."""
    pass


# Global instance management
_concurrency_store: Optional[ConcurrencyStore] = None
_concurrency_manager: Optional[ConcurrencyManager] = None


def init_concurrency_store(backend: Optional[str] = None) -> ConcurrencyManager:
    """Initialize the global concurrency manager."""
    global _concurrency_store, _concurrency_manager

    settings = get_settings()
    backend = backend or settings.concurrency_backend

    if backend == "redis":
        # TODO: Implement Redis backend
        raise NotImplementedError("Redis backend not yet implemented")
    else:
        _concurrency_store = InMemoryConcurrencyStore()

    _concurrency_manager = ConcurrencyManager(_concurrency_store)

    # Configure default limits from settings
    _concurrency_manager.set_limit("pipeline", settings.max_concurrent_pipelines)
    _concurrency_manager.set_limit("simulation", settings.max_concurrent_simulations)
    _concurrency_manager.set_limit("model_inference", settings.max_concurrent_model_inferences)
    _concurrency_manager.set_limit("sandbox", settings.max_concurrent_sandboxes)
    _concurrency_manager.set_limit("patch_generation", settings.max_concurrent_patch_generation)

    return _concurrency_manager


def get_concurrency_manager() -> Optional[ConcurrencyManager]:
    """Get the global concurrency manager (lazy init)."""
    global _concurrency_manager
    if _concurrency_manager is None:
        return init_concurrency_store()
    return _concurrency_manager


async def close_concurrency_store() -> None:
    """Close the global concurrency store."""
    global _concurrency_store, _concurrency_manager
    if _concurrency_manager:
        await _concurrency_manager.stop_background_tasks()
    if _concurrency_store:
        await _concurrency_store.close()
    _concurrency_manager = None
    _concurrency_store = None

"""
Tests for Phase 5: Concurrency Limits
"""
import asyncio
import pytest
from cauveris.concurrency import (
    InMemoryConcurrencyStore,
    ConcurrencyManager,
    ConcurrencyLimitExceeded,
    ConcurrencySlot,
)
from cauveris.config import get_settings


@pytest.fixture
def store():
    """Create a fresh InMemoryConcurrencyStore."""
    return InMemoryConcurrencyStore()


@pytest.fixture
def manager(store):
    """Create a ConcurrencyManager with test limits."""
    mgr = ConcurrencyManager(store)
    mgr.set_limit("test", 2)
    return mgr


@pytest.mark.asyncio
async def test_acquire_single_slot(store):
    """Test acquiring a single slot."""
    slot = await store.acquire("test", "user1", 2, 1.0)
    assert slot is not None
    assert slot.key == "test"
    assert slot.owner_id == "user1"
    assert slot.heartbeat_at == slot.acquired_at

    released = await store.release("test", "user1")
    assert released is True


@pytest.mark.asyncio
async def test_acquire_up_to_limit(store):
    """Test acquiring up to the limit."""
    # Acquire first slot
    slot1 = await store.acquire("test", "user1", 2, 1.0)
    assert slot1 is not None

    # Acquire second slot
    slot2 = await store.acquire("test", "user2", 2, 1.0)
    assert slot2 is not None

    # Third should timeout/return None (we use short timeout)
    slot3 = await store.acquire("test", "user3", 2, 0.1)
    assert slot3 is None


@pytest.mark.asyncio
async def test_same_owner_can_reacquire(store):
    """Test that same owner can reacquire (returns existing slot)."""
    slot1 = await store.acquire("test", "user1", 2, 1.0)
    assert slot1 is not None

    # Reacquire - should return same slot with updated heartbeat
    slot2 = await store.acquire("test", "user1", 2, 1.0)
    assert slot2 is not None
    assert slot1 is slot2  # Same object
    assert slot2.heartbeat_at >= slot1.heartbeat_at


@pytest.mark.asyncio
async def test_release_notifies_waiter(store):
    """Test that releasing notifies a waiting owner."""
    # Fill up capacity
    await store.acquire("test", "user1", 2, 1.0)
    await store.acquire("test", "user2", 2, 1.0)

    # user3 tries to acquire (this will create wait event)
    # We need to call acquire with short timeout to trigger wait
    wait_task = asyncio.create_task(store.acquire("test", "user3", 2, 0.5))

    # Give time for wait event to be created
    await asyncio.sleep(0.05)

    # Release one
    released = await store.release("test", "user1")
    assert released is True

    # Waiter should get the slot
    slot = await wait_task
    assert slot is not None
    assert slot.owner_id == "user3"


@pytest.mark.asyncio
async def test_heartbeat(store):
    """Test heartbeat updates timestamp."""
    slot = await store.acquire("test", "user1", 2, 1.0)
    original_heartbeat = slot.heartbeat_at

    await asyncio.sleep(0.01)
    result = await store.heartbeat("test", "user1")
    assert result is True

    slot = await store.get_slot("test", "user1")
    assert slot.heartbeat_at > original_heartbeat


@pytest.mark.asyncio
async def test_cleanup_stale(store):
    """Test stale slot cleanup."""
    now = asyncio.get_event_loop().time()

    # Acquire or create slots with old heartbeat
    slot1 = await store.acquire("test", "user1", 2, 1.0)
    slot1.heartbeat_at = now - 500  # 500 seconds ago (stale)

    slot2 = await store.acquire("test2", "user2", 2, 1.0)
    slot2.heartbeat_at = now - 100  # 100 seconds ago (not stale with 300s threshold)

    removed = await store.cleanup_stale(now - 300)
    assert removed == 1

    # slot1 should be gone, slot2 should remain
    slots = await store.list_slots("test")
    assert len(slots) == 0

    slots2 = await store.list_slots("test2")
    assert len(slots2) == 1


@pytest.mark.asyncio
async def test_manager_acquire_release(manager):
    """Test ConcurrencyManager.acquire context manager."""
    async with manager.acquire("test", "user1") as slot:
        assert slot is not None
        assert slot.owner_id == "user1"

    # Slot should be released after context exits
    slots = await manager._store.list_slots("test")
    assert len(slots) == 0


@pytest.mark.asyncio
async def test_manager_limit_exceeded(manager):
    """Test ConcurrencyLimitExceeded when limit exceeded."""
    # Fill capacity
    async with manager.acquire("test", "user1"):
        async with manager.acquire("test", "user2"):
            # Third should exceed
            with pytest.raises(ConcurrencyLimitExceeded):
                async with manager.acquire("test", "user3", timeout=0.1):
                    pass


@pytest.mark.asyncio
async def test_manager_stats(manager):
    """Test get_stats."""
    async with manager.acquire("test", "user1"):
        stats = await manager.get_stats("test")
        assert stats["scope"] == "test"
        assert stats["limit"] == 2
        assert stats["active"] == 1
        assert stats["available"] == 1
        assert len(stats["slots"]) == 1
        assert stats["slots"][0]["owner_id"] == "user1"


@pytest.mark.asyncio
async def test_concurrent_acquire_same_owner(manager):
    """Test concurrent acquire attempts by same owner."""
    async with manager.acquire("test", "user1") as slot1:
        # Another acquire by same owner should return same slot (no new slot)
        slot2 = await manager._store.acquire("test", "user1", 2, 1.0)
        assert slot1 is slot2


@pytest.mark.asyncio
async def test_heartbeat_keeps_slot_alive(manager):
    """Test that heartbeats prevent cleanup."""
    async with manager.acquire("test", "user1") as slot:
        # Send heartbeat
        await manager.heartbeat("test", "user1")

        # Slot should still exist and have updated heartbeat
        retrieved = await manager._store.get_slot("test", "user1")
        assert retrieved is not None
        assert retrieved.heartbeat_at >= slot.acquired_at


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
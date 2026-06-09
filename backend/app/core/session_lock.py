"""Per-session execution lock.

Inspired by OpenClaw's lane-aware FIFO command queue: only one agent run
may be active per (channel_id, sender_id) session at a time.  This prevents
competing writes to shared session history and avoids tool/context races
when a user sends messages in rapid succession.

Usage::

    from app.core.session_lock import acquire_session_lock

    async with acquire_session_lock(channel_id, sender_id, timeout=60):
        # safe to run AI here
        ...

If the lock cannot be acquired within *timeout* seconds, an asyncio.TimeoutError
is raised so the caller can discard the message silently rather than letting
jobs pile up.
"""

import asyncio
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Global lock registry: session_key -> asyncio.Lock (LRU-ordered)
# Capped at _MAX_LOCKS to prevent unbounded memory growth from many
# unique (channel_id, sender_id) pairs.
_MAX_LOCKS = 10_000
_SESSION_LOCKS: OrderedDict[str, asyncio.Lock] = OrderedDict()
_REGISTRY_LOCK = asyncio.Lock()  # guards _SESSION_LOCKS mutations


async def _get_lock(session_key: str) -> asyncio.Lock:
    """Return the lock for *session_key*, creating it if necessary.

    Uses LRU eviction: when the registry exceeds ``_MAX_LOCKS`` entries,
    the oldest idle locks are removed.  A lock that is currently held
    (locked) is never evicted.
    """
    lock = _SESSION_LOCKS.get(session_key)
    if lock is not None:
        _SESSION_LOCKS.move_to_end(session_key)
        return lock
    async with _REGISTRY_LOCK:
        # Double-checked inside the meta-lock
        if session_key in _SESSION_LOCKS:
            _SESSION_LOCKS.move_to_end(session_key)
            return _SESSION_LOCKS[session_key]
        new_lock = asyncio.Lock()
        _SESSION_LOCKS[session_key] = new_lock
        # Evict oldest idle locks if over capacity
        while len(_SESSION_LOCKS) > _MAX_LOCKS:
            oldest_key, oldest_lock = next(iter(_SESSION_LOCKS.items()))
            if oldest_lock.locked():
                break  # never evict a lock that is held
            _SESSION_LOCKS.pop(oldest_key)
        return new_lock


@asynccontextmanager
async def acquire_session_lock(
    channel_id: int,
    sender_id: str,
    timeout: float = 60.0,
):
    """Async context manager that serialises runs for one (channel, sender).

    Raises asyncio.TimeoutError if the lock is not acquired within *timeout*.
    """
    session_key = f"{channel_id}:{sender_id}"
    lock = await _get_lock(session_key)
    try:
        acquired = await asyncio.wait_for(lock.acquire(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "Session lock timeout for %s — dropping message to avoid backlog",
            session_key,
        )
        raise
    try:
        yield
    finally:
        lock.release()

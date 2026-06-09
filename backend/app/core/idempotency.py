"""
Lightweight idempotency key support for write operations.

Usage:
    from app.core.idempotency import idempotency_check

    @router.post("/items")
    async def create_item(
        data: ...,
        idempotency_result = Depends(idempotency_check),
    ):
        if idempotency_result is not None:
            return idempotency_result  # cached response from previous identical request
        ...

Clients send `Idempotency-Key: <uuid>` header on POST/PUT requests.
Results are cached for 24 hours (in Redis if available, else in-memory LRU).
"""
import json
import logging
import time
from collections import OrderedDict
from typing import Any

from fastapi import Request

logger = logging.getLogger(__name__)

_TTL = 86400  # 24 hours
_MEMORY_MAX = 500
_PREFIX = "idempotency:"

_memory_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()


def _cleanup_memory():
    now = time.time()
    while _memory_cache:
        key, (exp, _) = next(iter(_memory_cache.items()))
        if exp > now:
            break
        _memory_cache.pop(key, None)


async def _get_redis():
    try:
        from redis.asyncio import from_url as redis_async_from_url
        from app.config import settings
        client = redis_async_from_url(settings.REDIS_URL, socket_connect_timeout=0.3)
        await client.ping()
        return client
    except Exception:
        return None


async def idempotency_check(request: Request):
    """FastAPI dependency: returns cached response if idempotency key was seen before."""
    key = request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")
    if not key or request.method not in ("POST", "PUT"):
        return None

    full_key = f"{_PREFIX}{key}"

    r = await _get_redis()
    if r:
        cached = await r.get(full_key)
        await r.aclose()
        if cached:
            return json.loads(cached)
    else:
        _cleanup_memory()
        entry = _memory_cache.get(full_key)
        if entry and entry[0] > time.time():
            return entry[1]

    request.state._idempotency_key = full_key
    return None


async def save_idempotency_result(request: Request, result: Any):
    """Call after successful write to cache the result for replay."""
    full_key = getattr(request.state, "_idempotency_key", None)
    if not full_key:
        return

    serialized = json.dumps(result, ensure_ascii=False, default=str)

    r = await _get_redis()
    if r:
        try:
            await r.setex(full_key, _TTL, serialized)
        except Exception:
            pass
        finally:
            await r.aclose()
    else:
        if len(_memory_cache) >= _MEMORY_MAX:
            _memory_cache.popitem(last=False)
        _memory_cache[full_key] = (time.time() + _TTL, result)

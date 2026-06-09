"""
Token 黑名单管理工具。

支持 Redis 存储，失败时回退到内存存储。
不依赖具体应用的 config，由调用方传入参数。
"""
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable
import logging

import jwt as pyjwt
from jwt.exceptions import PyJWTError

logger = logging.getLogger(__name__)

_DEFAULT_KEY_PREFIX = "rag:token_blacklist:"
_MEMORY_BLACKLIST_MAX = 10000

# Module-level state for Redis client and memory fallback
_async_redis_client = None
_redis_unavailable_until = 0.0
_memory_blacklist: dict[str, float] = {}


async def get_async_redis(
    redis_url: str,
    socket_connect_timeout: float = 0.5,
) -> Optional[object]:
    """
    Get an async Redis connection.
    Caches client and skips retries for 60s when unreachable.
    
    :param redis_url: Redis 连接 URL
    :param socket_connect_timeout: 连接超时秒数
    :return: Redis 客户端或 None（不可用时）
    """
    import time as _time
    global _async_redis_client, _redis_unavailable_until

    if _redis_unavailable_until > _time.time():
        return None

    if _async_redis_client is not None:
        try:
            await _async_redis_client.ping()
            return _async_redis_client
        except Exception:
            _async_redis_client = None

    try:
        from redis.asyncio import from_url as redis_async_from_url
        client = redis_async_from_url(
            redis_url, decode_responses=True, socket_connect_timeout=socket_connect_timeout
        )
        await client.ping()
        _async_redis_client = client
        return _async_redis_client
    except Exception:
        _redis_unavailable_until = _time.time() + 60
        return None


def cleanup_memory_blacklist() -> None:
    """清理过期的内存黑名单条目。"""
    import time as _time
    now = _time.time()
    expired = [jti for jti, exp in _memory_blacklist.items() if exp <= now]
    for jti in expired:
        _memory_blacklist.pop(jti, None)


async def revoke_token(
    token: str,
    secret_key: str,
    algorithm: str,
    redis_url: Optional[str] = None,
    key_prefix: Optional[str] = None,
) -> bool:
    """
    Add a token's JTI to the blacklist.
    
    :param token: JWT token string
    :param secret_key: JWT 签名密钥
    :param algorithm: JWT 算法
    :param redis_url: Redis 连接 URL，None 时仅使用内存
    :param key_prefix: Redis key 前缀，用于多租户隔离（默认 "rag:token_blacklist:"）
    :return: True on success
    """
    import time as _time
    prefix = key_prefix or _DEFAULT_KEY_PREFIX
    try:
        payload = pyjwt.decode(token, secret_key, algorithms=[algorithm])
        jti = payload.get("jti")
        exp = payload.get("exp")
        if not jti or not exp:
            return False
        ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 0)
        if ttl <= 0:
            return True
        
        if redis_url:
            r = await get_async_redis(redis_url)
            if r:
                await r.setex(f"{prefix}{jti}", ttl, "1")
                return True
        
        # Memory fallback
        if len(_memory_blacklist) >= _MEMORY_BLACKLIST_MAX:
            cleanup_memory_blacklist()
        _memory_blacklist[jti] = _time.time() + ttl
        if redis_url:
            logger.warning(
                "Token revoked via memory fallback (Redis unavailable). "
                "注意: 多 Worker 部署下此吊销仅对当前进程有效！"
            )
        return True
    except PyJWTError as e:
        logger.warning("Token revocation failed: %s", e)
    return False


class BlacklistUnavailableError(Exception):
    """Raised when the token blacklist cannot be checked (Redis down, no memory fallback)."""


async def is_token_revoked(
    jti: str,
    redis_url: Optional[str] = None,
    key_prefix: Optional[str] = None,
    strict: bool = True,
) -> bool:
    """
    Check if a token JTI is in the blacklist.

    :param jti: Token 的 JTI
    :param redis_url: Redis 连接 URL，None 时仅检查内存
    :param key_prefix: Redis key 前缀，用于多租户隔离（默认 "rag:token_blacklist:"）
    :param strict: True 时 Redis 不可用且内存无记录则视为已吊销（安全优先）
    :return: True if revoked (or if blacklist unavailable in strict mode)
    """
    import time as _time
    prefix = key_prefix or _DEFAULT_KEY_PREFIX
    redis_checked = False

    if redis_url:
        try:
            r = await get_async_redis(redis_url)
            if r:
                redis_checked = True
                return bool(await r.exists(f"{prefix}{jti}"))
        except Exception as exc:
            logger.warning("Token blacklist check failed (Redis unavailable): %s", exc)

    # Check memory blacklist
    exp = _memory_blacklist.get(jti)
    if exp is not None:
        if exp > _time.time():
            return True
        _memory_blacklist.pop(jti, None)
        return False

    # If Redis was expected but unavailable and no memory record exists,
    # in strict mode we treat the token as potentially revoked (fail-closed)
    if strict and redis_url and not redis_checked:
        logger.warning(
            "Token blacklist: Redis unavailable and JTI %s not in memory — "
            "rejecting token (fail-closed). Set strict=False to allow.",
            jti[:8],
        )
        return True

    return False


def reset_state() -> None:
    """Reset module state (for testing purposes)."""
    global _async_redis_client, _redis_unavailable_until
    _async_redis_client = None
    _redis_unavailable_until = 0.0
    _memory_blacklist.clear()

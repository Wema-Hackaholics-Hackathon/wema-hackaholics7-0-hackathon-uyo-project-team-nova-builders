"""Optional Redis cache helpers.

The application starts cleanly even if Redis is unavailable — all cache
operations degrade to no-ops and ``ping()`` returns False.

Usage:
    from app.utils.cache import get, set_ex, delete, ping

    await set_ex("key", value, ttl=300)
    data = await get("key")        # None if miss or Redis down
    await delete("key")
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

# Redis client — imported lazily so the app boots without redis installed
_redis: object | None = None

JsonValue = str | int | float | bool | list[object] | dict[str, object] | None


async def _get_client() -> object | None:
    """Lazily initialise the Redis client; returns None if Redis is misconfigured."""
    global _redis
    if _redis is not None:
        return _redis

    from app.config import get_settings
    settings = get_settings()
    if not settings.REDIS_URL:
        return None

    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        _redis = client
        return _redis
    except Exception as exc:
        log.warning("Redis unavailable: %s", exc)
        return None


async def ping() -> bool:
    """Return True if Redis is reachable, False otherwise."""
    client = await _get_client()
    if client is None:
        return False
    try:
        import redis.asyncio as aioredis
        assert isinstance(client, aioredis.Redis)
        result: object = await client.ping()  # pyright: ignore[reportUnknownMemberType]
        return bool(result)
    except Exception:
        return False


async def get(key: str) -> JsonValue:
    """Return the cached value (deserialised from JSON), or None on miss/error."""
    client = await _get_client()
    if client is None:
        return None
    try:
        import redis.asyncio as aioredis
        assert isinstance(client, aioredis.Redis)
        raw: object = await client.get(key)
        if raw is None:
            return None
        parsed: JsonValue = json.loads(str(raw))  # pyright: ignore[reportAny]
        return parsed
    except Exception:
        return None


async def set_ex(key: str, value: JsonValue, ttl: int = 300) -> None:
    """Cache *value* (serialised as JSON) under *key* with a TTL in seconds."""
    client = await _get_client()
    if client is None:
        return
    try:
        import redis.asyncio as aioredis
        assert isinstance(client, aioredis.Redis)
        _ = await client.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


async def delete(key: str) -> None:
    """Evict a cache key (no-op if Redis is down)."""
    client = await _get_client()
    if client is None:
        return
    try:
        import redis.asyncio as aioredis
        assert isinstance(client, aioredis.Redis)
        _ = await client.delete(key)
    except Exception:
        pass

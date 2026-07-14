import redis.asyncio as aioredis
import json
import structlog
from typing import Any, Optional
from app.config import settings


logger = structlog.get_logger(__name__)

# Shared async Redis client — used by every service that needs caching,
# rate limiting, blacklisting, or pub/sub.  Created at import time from
# the .env config so connections are pooled from the start.
redis_client = aioredis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    decode_responses=True
)


async def ping_redis() -> bool:
    """Check if Redis is reachable.  Returns ``True`` if PONG."""
    try:
        return await redis_client.ping()
    except Exception:
        return False


async def set_cache(key: str, value: Any, ttl: int = 60) -> None:
    """Store *value* (JSON-serialised) at *key* with a TTL of *ttl* seconds.

    Used across the codebase for caching user profiles, auth tokens,
    feed data, etc.  Silently no-ops if Redis is down.
    """
    try:
        json_value = json.dumps(value)
        await redis_client.setex(key, ttl, json_value)
    except Exception:
        pass


async def get_cache(key: str) -> Optional[Any]:
    """Retrieve a JSON-deserialised value at *key*, or ``None``.

    Returns ``None`` on cache miss or if Redis is unreachable.
    """
    try:
        cached = await redis_client.get(key)
        if cached is None:
            return None
        return json.loads(cached)
    except Exception:
        return None


async def delete_cache(key: str) -> None:
    """Remove *key* from Redis.

    Call this whenever the underlying data changes so the next request
    fetches fresh data from the DB.
    """
    try:
        await redis_client.delete(key)
    except Exception:
        pass


async def delete_cache_pattern(pattern: str) -> None:
    """Remove ALL keys matching *pattern* using SCAN (non-blocking).

    Useful when a change affects many cached items at once (e.g.
    invalidating all cached notifications for a user after a new one
    arrives).  Uses SCAN instead of KEYS to avoid blocking Redis on
    large key spaces.
    """
    try:
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor=cursor, match=pattern, count=100)
            if keys:
                await redis_client.delete(*keys)
            if cursor == 0:
                break
    except Exception:
        pass


async def check_redis_connection() -> bool:
    """Call once at startup to confirm Redis is reachable.

    If Redis is down the app still starts — caching and rate limiting
    gracefully degrade.  Returns ``True`` if connected.
    """
    if await ping_redis():
        logger.info("Redis connection successful")
        return True
    else:
        logger.error(
            "Redis connection failed; caching and rate-limiting will be disabled",
            extra={"extra_info": {"redis_host": settings.redis_host, "redis_port": settings.redis_port}},
        )
        return False


async def add_to_blacklist(token: str, ttl: int):
    """Add *token* to the Redis blacklist.

    Used during logout to invalidate an access token before its natural
    expiry.  The TTL is set to the token's remaining lifetime so the
    blacklist entry auto-expires.
    """
    try:
        await redis_client.setex(f"blacklist:{token}", ttl, "true")
    except Exception:
        pass


async def is_blacklisted(token: str) -> bool:
    """Check whether *token* is in the Redis blacklist.

    Returns ``True`` if blacklisted.  If Redis is down we return
    ``False`` (fail-open).  This is a security trade-off — for higher
    security you might want to return ``True`` when Redis is unavailable.
    """
    try:
        return await redis_client.exists(f"blacklist:{token}") > 0
    except Exception:
        return False


async def get_auth_cache_and_blacklist(token: str) -> tuple[bool, Optional[Any]]:
    """Fetch blacklist flag and auth cache in a single Redis round-trip.

    Returns ``(is_blacklisted, cached_user_payload_or_None)``.

    This is the hot path for every authenticated request — combining the
    two lookups into one ``MGET`` halves the Redis overhead.
    """
    try:
        blacklist_key = f"blacklist:{token}"
        auth_key = f"auth:user:{token}"
        blacklisted_value, cached_value = await redis_client.mget(blacklist_key, auth_key)
        if blacklisted_value is not None:
            return True, None
        if cached_value is None:
            return False, None
        return False, json.loads(cached_value)
    except Exception:
        return False, None


async def increment_cache_version(domain: str) -> int:
    """Increment the cache version counter for *domain*.

    This enables fast invalidation without SCAN loops.  After
    incrementing, all cached keys with old version numbers become
    stale and will miss on next read.

    Example: ``increment_cache_version("feed:home")`` bumps the counter
    so all ``feed:home:42:v5:...`` keys are effectively invalidated.
    """
    try:
        version_key = f"{domain}:version"
        new_version = await redis_client.incr(version_key)
        return new_version
    except Exception:
        return 1


async def get_cache_version(domain: str) -> int:
    """Get the current cache version for *domain*."""
    try:
        version_key = f"{domain}:version"
        version = await redis_client.get(version_key)
        return int(version) if version else 1
    except Exception:
        return 1


def build_versioned_feed_cache_key(feed_type: str, user_id: int, offset: int, limit: int, version: int) -> str:
    """Build a versioned feed cache key.

    Format: ``feed:<feed_type>:<user_id>:v<version>:<offset>:<limit>``

    Using versioned keys means we never need to delete individual feed
    cache entries — incrementing the version makes all old keys naturally
    expire unused.
    """
    return f"feed:{feed_type}:{user_id}:v{version}:{offset}:{limit}"


async def queue_post_view(post_id: int, user_id: int) -> None:
    """Queue a post view for async batch processing.

    We use a Redis SET (``post:views:queue``) to deduplicate views within
    the same batch window.  A Celery beat task periodically flushes this
    set to the ``post_views`` table.

    This decouples the read path from DB writes — viewing a post doesn't
    block on an INSERT.
    """
    try:
        view_queue_key = "post:views:queue"
        await redis_client.sadd(view_queue_key, f"{post_id}:{user_id}")
    except Exception:
        pass

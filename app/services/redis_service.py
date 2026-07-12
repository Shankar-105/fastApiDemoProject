# redis_service.py
# A simple Redis caching helper for our FastAPI project.
#
# WHAT IS REDIS?
#   Redis is an in-memory key-value store. Think of it like a super-fast
#   Python dictionary that lives outside your app.  Because the data sits
#   in RAM (not on disk like PostgreSQL), reads/writes are *extremely* fast
#   — perfect for caching responses so we don't hit the database every time.
#
# HOW THIS MODULE WORKS (step by step):
#   1. We create ONE shared async Redis connection when the app starts.
#   2. Before hitting the DB, a route checks Redis: "do I already have
#      this data cached?"  If YES → return the cached JSON instantly.
#   3. If NO → query the DB as usual, then STORE the result in Redis
#      with an expiration time (TTL). Next request gets the cached copy.
#   4. When data changes (create / update / delete), we INVALIDATE
#      (delete) the relevant cache keys so stale data is never served.

import redis.asyncio as aioredis
import json
import structlog
from typing import Any, Optional
from app.config import settings


logger = structlog.get_logger(__name__)

#  1. CREATE THE ASYNC REDIS CLIENT 
# This is similar to how db.py creates the SQLAlchemy engine.
# We make ONE client object and import it wherever we need caching.
#   host  = where your Redis server is running  (localhost / WSL)
#   port  = default Redis port 6379
#   db    = Redis has 16 databases (0-15), we use 0
#   decode_responses=True  →  gives us normal Python strings
#                              instead of raw bytes (b"hello")

redis_client = aioredis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    decode_responses=True       # ← very important for convenience
)

# 2. HELPER FUNCTIONS

async def ping_redis() -> bool:
    """
    Check if Redis is reachable.
    Returns True if connected, False otherwise.
    
    Under the hood this sends the PING command to the Redis server,
    and Redis replies with PONG.
    """
    try:
        return await redis_client.ping()   # → True
    except Exception:
        return False

async def set_cache(key: str, value: Any, ttl: int = 60) -> None:
    """
    Store something in Redis.
    Parameters
    ----------
    key : str
        A unique name for this cached item.
        Convention:  "resource_type:identifier"
        Examples:    "user_profile:42"   "all_users"   "post:108"

    value : Any
        The Python object to cache (dict, list, etc.).
        We serialize it to a JSON string before storing because
        Redis only stores strings (or bytes).

    ttl : int  (seconds, default 60)
        "Time To Live" — how long the key stays in Redis.
        After this many seconds Redis auto-deletes it.
        This ensures the cache doesn't serve outdated data forever.
    """
    try:
        json_value = json.dumps(value)
        await redis_client.setex(key,ttl,json_value)
    except Exception:
        # If Redis is down, silently skip caching — the route still works,
        # it just won't have the speed benefit. Never let cache failures
        # crash a route with a 500.
        pass

async def get_cache(key:str) -> Optional[Any]:
    """
    Retrieve something from Redis.
    Returns
    -------
    The original Python object (dict/list/etc.) if the key exists,
    or None if the key has expired or was never set.
    """
    try:
        cached = await redis_client.get(key)   # → JSON string or None
        if cached is None:
            return None                  # cache MISS
        return json.loads(cached)        # cache HIT
    except Exception:
        # If Redis is unreachable, behave as a cache miss so the route
        # falls through to the database and still returns a response.
        return None

async def delete_cache(key: str) -> None:
    """
    Remove a specific key from Redis (invalidate the cache).
    Call this when the underlying data changes, e.g. after a user
    updates their profile, so the next request fetches fresh data.
    """
    try:
        await redis_client.delete(key)
    except Exception:
        pass

async def delete_cache_pattern(pattern: str) -> None:
    """
    Remove ALL keys matching a pattern.
    Example:  delete_cache_pattern("user_profile:*")
    This would delete user_profile:1, user_profile:2, etc.

    Useful when a change affects many cached items at once,
    e.g. clearing all cached user profiles after a bulk update.

    ⚠️  SCAN is used instead of KEYS because KEYS blocks Redis
    on large datasets. SCAN iterates in small batches.
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

#  3. STARTUP CHECK 

async def check_redis_connection() -> bool:
    """
    Call this once at app startup to confirm Redis is reachable.
    Returns True if connected, False otherwise.
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
    """
    Adds a token to the Redis blacklist.
    """
    try:
        await redis_client.setex(f"blacklist:{token}", ttl, "true")
    except Exception:
        pass

async def is_blacklisted(token: str) -> bool:
    """
    Checks if a token is in the Redis blacklist.
    """
    try:
        return await redis_client.exists(f"blacklist:{token}") > 0
    except Exception:
        # If redis is down, we'll allow the token.
        # This is a security trade-off. For higher security, you might want to return True.
        return False


async def get_auth_cache_and_blacklist(token: str) -> tuple[bool, Optional[Any]]:
    """
    Fetch blacklist flag and auth cache in a single Redis roundtrip.
    Returns (is_blacklisted, cached_user_payload_or_none).
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


# --- Cache versioning for targeted invalidations ---
# Instead of deleting "feed:*" globally (which triggers SCAN loops and cache churn),
# use versioned keys like "feed:home:{user_id}:v{version}:{offset}:{limit}".
# When feed changes, increment the version counter, and old keys naturally expire.

async def increment_cache_version(domain: str) -> int:
    """
    Increment the cache version for a domain (e.g., 'feed:home', 'feed:explore').
    Returns the new version number.
    This enables fast invalidation without SCAN loops.
    
    Example: increment_cache_version("feed:home") increments feed:home:version.
    All cached keys with old version numbers become stale and will miss.
    """
    try:
        version_key = f"{domain}:version"
        new_version = await redis_client.incr(version_key)
        return new_version
    except Exception:
        return 1  # Default to version 1 if Redis is down


async def get_cache_version(domain: str) -> int:
    """
    Get the current cache version for a domain.
    """
    try:
        version_key = f"{domain}:version"
        version = await redis_client.get(version_key)
        return int(version) if version else 1
    except Exception:
        return 1


def build_versioned_feed_cache_key(feed_type: str, user_id: int, offset: int, limit: int, version: int) -> str:
    """
    Build a versioned feed cache key.
    feed_type: 'home' or 'explore'
    version: from get_cache_version()
    
    Example: feed:home:123:v5:0:10 (home feed for user 123, version 5, offset 0, limit 10)
    """
    return f"feed:{feed_type}:{user_id}:v{version}:{offset}:{limit}"


# --- Phase A: Async post view tracking (queue instead of sync insert) ---

async def queue_post_view(post_id: int, user_id: int) -> None:
    """
    Queue a post view for async processing instead of inserting synchronously.
    This decouples the read path from DB writes, reducing latency.
    
    The queue is a Redis SET to automatically deduplicate per request.
    A background task periodically flushes this to the database.
    """
    try:
        # Use a set to avoid duplicate inserts in the same batch window
        view_queue_key = f"post:views:queue"
        # Store as "{post_id}:{user_id}" for later parsing
        await redis_client.sadd(view_queue_key, f"{post_id}:{user_id}")
        # Do NOT set a short TTL here. The Celery beat task is responsible
        # for flushing and removing processed members. Keeping no expiry
        # avoids losing queued views before the periodic flush runs.
    except Exception:
        pass  # If Redis is down, silently skip queueing (views just won't be tracked)

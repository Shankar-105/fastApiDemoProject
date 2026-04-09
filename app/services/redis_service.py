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
from typing import Any, Optional
from app.config import settings

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
        print("✅ Redis connection successful!")
        return True
    else:
        print("❌ Redis connection FAILED — caching and rate-limiting will be disabled.")
        print(f"   Tried connecting to {settings.redis_host}:{settings.redis_port}")
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

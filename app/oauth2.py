from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import asyncio
import time
import uuid
from types import SimpleNamespace
from app import schemas as sch, models, db
from fastapi import status, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi.security import OAuth2PasswordBearer
from app.config import settings as cg
from app.services import redis_service


oauth2_scheme = OAuth2PasswordBearer(tokenUrl='login')

ALGORITHM = cg.algorithm
SECRET_KEY = cg.secret_key
EXPIRE_TIME = cg.access_token_expire_time


# ── Sync helpers (CPU-bound JWT cryptography) ──


def _createAccessToken_sync(data: dict) -> str:
    """Synchronous JWT encode — runs on a thread pool when called via ``createAccessToken()``.

    We add ``expTime``, ``iat``, and ``jti`` claims to every token so the
    auth middleware can check expiry without a DB round-trip, and so we
    can blacklist individual tokens by ``jti`` if needed.
    """
    dataCopy = data.copy()
    expireTime = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_TIME)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    dataCopy.update({
        "expTime": int(expireTime.timestamp()),
        "iat": now_ts,
        "jti": str(uuid.uuid4()),
    })
    jwtToken = jwt.encode(dataCopy, SECRET_KEY, algorithm=ALGORITHM)
    return jwtToken


def _decodeToken_sync(token: str) -> dict:
    """Synchronous JWT decode — runs on a thread pool when called via ``decodeToken()``.

    We validate the ``expTime`` claim ourselves (rather than relying on
    ``jose``'s ``options={"verify_exp": True}``) because the claim name is
    ``expTime``, not the standard ``exp``.
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    exp = payload.get("expTime")
    if exp is None or datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
        raise JWTError("Token has expired")
    return payload


# ── Async wrappers ──
# JWT encode/decode uses HMAC-SHA256 (or RSA) which is CPU-bound.
# ``asyncio.to_thread()`` pushes it off the event loop so other requests
# aren't blocked.  This matters on our 1 GB Azure VM where a slow
# single request could stall the whole process.


async def createAccessToken(data: dict) -> str:
    """Create a signed JWT access token, offloaded to a thread pool.

    Args:
        data: Must contain at least ``"userId"`` and ``"userName"``.

    Returns:
        The encoded JWT string.
    """
    return await asyncio.to_thread(_createAccessToken_sync, data)


async def decodeToken(token: str) -> dict:
    """Decode and validate a JWT access token, offloaded to a thread pool.

    Raises:
        JWTError: if the token is expired, malformed, or has an invalid signature.
    """
    return await asyncio.to_thread(_decodeToken_sync, token)


def _build_user_from_cache(cached: dict) -> models.User:
    """Rehydrate a ``SimpleNamespace`` user object from a cached dict.

    This lets us skip the DB entirely on cache hits.  The resulting object
    is not a true SQLAlchemy model — it's a lightweight stand-in with the
    same attributes.  ``created_at`` is parsed from ISO format back to a
    ``datetime``.

    Fallback defaults of ``0`` are applied for ``followers_cnt`` and
    ``following_cnt`` if they're missing from the cache (legacy entries).
    """
    user = SimpleNamespace()
    for key, value in cached.items():
        if key == "created_at" and value:
            try:
                setattr(user, key, datetime.fromisoformat(value))
            except Exception:
                setattr(user, key, None)
        else:
            setattr(user, key, value)
    if not hasattr(user, "followers_cnt"):
        user.followers_cnt = 0
    if not hasattr(user, "following_cnt"):
        user.following_cnt = 0
    return user


def _build_user_cache_payload(user: models.User) -> dict:
    """Extract the fields we cache for an authenticated user.

    We deliberately exclude ``followers_cnt`` and ``following_cnt`` because
    these change frequently (every follow/unfollow) and caching them would
    require invalidating ``auth:user:{token}`` on every social action.
    The route layer queries fresh counts when needed.
    """
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "bio": user.bio,
        "email": user.email,
        "email_verified": user.email_verified,
        "profile_picture": user.profile_picture,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _get_access_token_ttl_seconds(payload: dict) -> int:
    """Return the remaining lifetime (in seconds) of the access token in *payload*.

    Used as the TTL for the ``auth:user:{token}`` cache entry.  Ensures the
    cache entry expires at or before the token itself.
    """
    exp = payload.get("expTime")
    if exp:
        return max(0, int(exp - time.time()))
    return cg.access_token_expire_time * 60


async def _validate_access_token(token: str, credentials_exception):
    """Check blacklist, decode JWT, and ensure ``userId`` / ``userName`` claims exist.

    This is the shared validation step used by both ``verifyAccesstoken``
    and ``getCurrentUser``.
    """
    if await redis_service.is_blacklisted(token):
        raise credentials_exception

    try:
        payload = await decodeToken(token)
    except JWTError:
        raise credentials_exception

    user_id = payload.get("userId")
    username = payload.get("userName")
    if user_id is None or username is None:
        raise credentials_exception

    return payload


async def verifyAccesstoken(token: str, credentials_exception, dbs: AsyncSession):
    """Full token verification that also queries the DB to confirm the user exists.

    This is the older auth path (used in some legacy endpoints).  New code
    should prefer ``getCurrentUser`` which caches the user in Redis.
    """
    payload = await _validate_access_token(token, credentials_exception)
    user_id = payload.get("userId")

    result = await dbs.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user


from structlog.contextvars import bind_contextvars
from app.utils.exceptions import AuthenticationException


async def getCurrentUser(token: str = Depends(oauth2_scheme), dbs: AsyncSession = Depends(db.getDb)):
    """Resolve the authenticated user from the Bearer token.

    **Hot path for every protected route.**  The flow is:

    1. Single Redis ``MGET`` to check blacklist + fetch cached user
       payload — fast path, no DB hit.
    2. If cached and not blacklisted, return the lightweight user object
       immediately.
    3. On cache miss, validate the JWT, query the DB once, cache the
       result for the token's remaining lifetime, and return.

    The cached payload excludes follower/following counts (they change
    too frequently), so callers that need counts must query them fresh.

    Raises:
        AuthenticationException: if the token is blacklisted, expired,
            malformed, or the user was deleted.
    """
    # Single Redis roundtrip: check blacklist + token-scoped user cache.
    blacklisted, cached = await redis_service.get_auth_cache_and_blacklist(token)
    if blacklisted:
        raise AuthenticationException()

    # Cache hit: token was not blacklisted and user snapshot is available.
    # TTL on auth:user:{token} is bounded by token expiry, so we can skip DB lookup.
    if cached is not None:
        user = _build_user_from_cache(cached)
        bind_contextvars(user_id=user.id)
        return user

    # Cache miss: validate JWT claims/signature and then query DB once.
    cache_key = f"auth:user:{token}"
    payload = await _validate_access_token(token, AuthenticationException())

    # Not cached - get user from DB, then cache it for the remaining token lifetime.
    result = await dbs.execute(select(models.User).where(models.User.id == payload.get("userId")))
    user = result.scalars().first()
    if user is None:
        raise AuthenticationException()

    bind_contextvars(user_id=user.id)
    await redis_service.set_cache(cache_key, _build_user_cache_payload(user), ttl=_get_access_token_ttl_seconds(payload))
    return user

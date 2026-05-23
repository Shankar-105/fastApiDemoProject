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

# a scheme for Extracting the sent JWT token 
# from the Authorization Header
oauth2_scheme=OAuth2PasswordBearer(tokenUrl='login')

# basically for the generation of an JWT token it requries
# 1. an ALGORITHM
# 2. some user data like suppose here user id,username
# and to this we add a newField called the expiry time
# for that amount of time the jwt token will be valid
# 3. a secret key
ALGORITHM=cg.algorithm
SECRET_KEY=cg.secret_key
EXPIRE_TIME=cg.access_token_expire_time

# ── Sync helpers (CPU-bound JWT cryptography) — NEVER call these from async code directly ──
def _createAccessToken_sync(data: dict) -> str:
    """Synchronous JWT encode — runs on a thread pool when called via createAccessToken()."""
    dataCopy=data.copy()
    expireTime=datetime.now(timezone.utc)+timedelta(minutes=EXPIRE_TIME)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    dataCopy.update({
        "expTime": int(expireTime.timestamp()),
        "iat": now_ts,
        "jti": str(uuid.uuid4()),
    })
    jwtToken=jwt.encode(dataCopy,SECRET_KEY,algorithm=ALGORITHM)
    return jwtToken

def _decodeToken_sync(token: str) -> dict:
    """Synchronous JWT decode — runs on a thread pool when called via decodeToken()."""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    exp = payload.get("expTime")
    if exp is None or datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
        raise JWTError("Token has expired")
    return payload

# ── Async wrappers (offload CPU-bound JWT ops to a thread pool) ──
# jwt.encode() uses HMAC-SHA256 (or RSA) which is CPU-bound cryptography.
# asyncio.to_thread() pushes it off the event loop so other requests aren't blocked.

async def createAccessToken(data:dict) -> str:
    """Create a JWT token — offloaded to a thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(_createAccessToken_sync, data)

async def decodeToken(token: str) -> dict:
    """Decode a JWT token — offloaded to a thread pool to avoid blocking the event loop."""
    return await asyncio.to_thread(_decodeToken_sync, token)


def _build_user_from_cache(cached: dict) -> models.User:
    user = SimpleNamespace()
    for key, value in cached.items():
        if key == "created_at" and value:
            try:
                setattr(user, key, datetime.fromisoformat(value))
            except Exception:
                setattr(user, key, None)
        else:
            setattr(user, key, value)
    return user


def _build_user_cache_payload(user: models.User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "bio": user.bio,
        "email": user.email,
        "email_verified": user.email_verified,
        "profile_picture": user.profile_picture,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "followers_cnt": user.followers_cnt,
        "following_cnt": user.following_cnt,
    }


def _get_access_token_ttl_seconds(payload: dict) -> int:
    exp = payload.get("expTime")
    if exp:
        return max(0, int(exp - time.time()))
    return cg.access_token_expire_time * 60


async def _validate_access_token(token: str, credentials_exception):
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


async def verifyAccesstoken(token:str,credentials_exception,dbs:AsyncSession):
    payload = await _validate_access_token(token, credentials_exception)
    user_id = payload.get("userId")

    result = await dbs.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user is None:
        raise credentials_exception
    return user

from app.utils.logging import user_id_ctx
from app.utils.exceptions import AuthenticationException

# Get current user (for protected routes)
# in the parentheses the Depends(oauth2_scheme) returns the
# JWT Token which is stored in the token variable below
# and sent to the verifyAccesstoken() mtd
async def getCurrentUser(token: str = Depends(oauth2_scheme), dbs: AsyncSession = Depends(db.getDb)):
    # Single Redis roundtrip: check blacklist + token-scoped user cache.
    blacklisted, cached = await redis_service.get_auth_cache_and_blacklist(token)
    if blacklisted:
        raise AuthenticationException()

    # Cache hit: token was not blacklisted and user snapshot is available.
    # TTL on auth:user:{token} is bounded by token expiry, so we can skip DB lookup.
    if cached is not None:
        user = _build_user_from_cache(cached)
        user_id_ctx.set(user.id)
        return user

    # Cache miss: validate JWT claims/signature and then query DB once.
    cache_key = f"auth:user:{token}"
    payload = await _validate_access_token(token, AuthenticationException())

    # Not cached - get user from DB, then cache it for the remaining token lifetime.
    result = await dbs.execute(select(models.User).where(models.User.id == payload.get("userId")))
    user = result.scalars().first()
    if user is None:
        raise AuthenticationException()

    user_id_ctx.set(user.id)
    await redis_service.set_cache(cache_key, _build_user_cache_payload(user), ttl=_get_access_token_ttl_seconds(payload))
    return user
from jose import JWTError,jwt
from datetime import datetime,timedelta,timezone
import asyncio
from app import schemas as sch,models,db
from fastapi import status,HTTPException,Depends
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
    dataCopy.update({"expTime":int(expireTime.timestamp())})
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

async def verifyAccesstoken(token:str,credentials_exception,dbs:AsyncSession):
    if await redis_service.is_blacklisted(token):
        raise credentials_exception
    try:
        # decode's the token which returns a dict of the sent user info 
        # while creating a token (userId,userName) 
        # offloaded to thread pool via our async decodeToken() wrapper
        decodedToken=await decodeToken(token)
        # extract those userId and userName from the returned dict
        id: int=decodedToken.get("userId")
        username: str=decodedToken.get("userName")
        # if they aren't found meaning a malformed jwt token is sent
        # so we raise an exception
        if id is None or username is None:
            raise credentials_exception
        # if not then we query the db using the async select() pattern
        result=await dbs.execute(select(models.User).where(models.User.id == id))
        user=result.scalars().first()
        # If the user was deleted but the token is still valid, treat as unauthorized
        if user is None:
            raise credentials_exception
        return user
    # if the token itself is invalid we raise a JWTError
    except JWTError:
        raise credentials_exception

# Get current user (for protected routes)
# in the parentheses the Depends(oauth2_scheme) returns the
# JWT Token which is stored in the token variable below
# and sent to the verifyAccesstoken() mtd
async def getCurrentUser(token: str = Depends(oauth2_scheme),dbs:AsyncSession=Depends(db.getDb)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    return await verifyAccesstoken(token,credentials_exception,dbs)
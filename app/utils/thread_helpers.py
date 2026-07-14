import bcrypt
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app import models

# ── Sync helpers (CPU-bound bcrypt work) — NEVER call these from async code directly ──
def _hashPassword_sync(password: str) -> str:
    """Synchronous bcrypt hash — runs on a thread pool when called via hashPassword().

    Truncates passwords beyond 72 bytes (bcrypt's input limit).
    NOT called directly from async code — always use the async wrapper.
    """
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]  # bcrypt limit: 72 bytes
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')

def _verifyPassword_sync(plain_password: str, hashed_password: str) -> bool:
    """Synchronous bcrypt verify — runs on a thread pool when called via verifyPassword().

    Truncates input beyond 72 bytes to match hashPassword behavior.
    NOT called directly from async code — always use the async wrapper.
    """
    password_bytes = plain_password.encode('utf-8')
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]  # bcrypt limit: 72 bytes
    return bcrypt.hashpw(password_bytes, hashed_password.encode('utf-8')) == hashed_password.encode('utf-8')

# ── Async wrappers (offload CPU-bound bcrypt to a thread pool) ──
# asyncio.to_thread() runs the sync function on Python's default ThreadPoolExecutor
# so the event loop stays FREE to handle other requests while bcrypt crunches numbers.

async def hashPassword(password: str) -> str:
    """Hash a password using bcrypt, offloaded to a thread pool to avoid blocking the event loop.

    Wraps the CPU-bound _hashPassword_sync via asyncio.to_thread.
    Used by the auth service during signup and password change flows.
    """
    return await asyncio.to_thread(_hashPassword_sync, password)

async def verifyPassword(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash, offloaded to a thread pool.

    Wraps the CPU-bound _verifyPassword_sync via asyncio.to_thread.
    Used by the auth service during login and token refresh.
    """
    return await asyncio.to_thread(_verifyPassword_sync, plain_password, hashed_password)
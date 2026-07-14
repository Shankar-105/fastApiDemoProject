import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar
import structlog

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


logger = structlog.get_logger(__name__)

T = TypeVar("T")

TRANSIENT_PG_CODES = {"40001", "40P01"}


def _pg_code_from_error(error: BaseException) -> str | None:
    """Extract the PostgreSQL SQLSTATE code from a nested exception chain.

    ``OperationalError`` from asyncpg carries the code in different attributes
    depending on the driver version.  We walk ``.sqlstate``, ``.pgcode``, and
    their ``.orig`` counterparts to find it.
    """
    return (
        getattr(error, "sqlstate", None)
        or getattr(error, "pgcode", None)
        or getattr(getattr(error, "orig", None), "sqlstate", None)
        or getattr(getattr(error, "orig", None), "pgcode", None)
    )


def is_transient_db_error(error: BaseException) -> bool:
    """Return ``True`` if the error is a serialisation failure or deadlock.

    PostgreSQL error codes:
        ``40001`` — serialisation failure (e.g. ``SELECT … FOR UPDATE``
                    discovered a concurrent modification at commit time)
        ``40P01`` — deadlock detected, this session was chosen as the victim.

    Both are safe to retry because the transaction will have been rolled back
    automatically by the server.
    """
    return _pg_code_from_error(error) in TRANSIENT_PG_CODES


async def run_with_transient_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    db: AsyncSession | None = None,
    attempts: int = 3,
    base_delay: float = 0.05,
    max_delay: float = 0.25,
) -> T:
    """Execute *operation* and retry up to *attempts* times on transient PG errors.

    We built this after hitting ``could not serialize access`` errors under
    concurrent load (the 1 GB Azure VM makes lock contention more likely).
    The delay uses capped exponential backoff with jitter so we don't hammer
    the database on retries.

    If *db* is provided the session is rolled back before each retry so the
    new attempt starts with a clean transaction.

    Raises:
        OperationalError: if all attempts fail or the error is non-transient.
    """
    last_error: OperationalError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except OperationalError as error:
            if not is_transient_db_error(error) or attempt == attempts:
                logger.warning(
                    "Transient retry exhausted or non-transient DB error encountered",
                    extra={"extra_info": {"attempt": attempt, "attempts": attempts, "error": str(error)}},
                )
                raise
            last_error = error
            if db is not None:
                await db.rollback()
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            delay *= 0.5 + random.random()
            logger.warning(
                "Retrying transient DB operation",
                extra={"extra_info": {"attempt": attempt, "attempts": attempts, "delay": delay}},
            )
            await asyncio.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry wrapper exhausted without raising or returning")


async def lock_user_row(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    email: str | None = None,
) -> models.User:
    """Acquire a row-level lock on a user via ``SELECT … FOR UPDATE``.

    Must provide exactly one of *user_id* or *email*.

    We use this in password-reset and email-verify flows to prevent concurrent
    updates from causing lost writes (e.g. two simultaneous password resets
    on the same account).  The lock is held until the enclosing transaction
    commits or rolls back.

    Raises:
        ValueError: if neither or both keys are supplied.
        HTTPException 404: if no user matches.
    """
    if (user_id is None) == (email is None):
        raise ValueError("Provide exactly one lookup key")

    stmt = select(models.User)
    if user_id is not None:
        stmt = stmt.where(models.User.id == user_id)
    else:
        stmt = stmt.where(models.User.email == email)

    result = await db.execute(stmt.with_for_update())
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

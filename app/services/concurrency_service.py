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
    return (
        getattr(error, "sqlstate", None)
        or getattr(error, "pgcode", None)
        or getattr(getattr(error, "orig", None), "sqlstate", None)
        or getattr(getattr(error, "orig", None), "pgcode", None)
    )


def is_transient_db_error(error: BaseException) -> bool:
    return _pg_code_from_error(error) in TRANSIENT_PG_CODES


async def run_with_transient_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    db: AsyncSession | None = None,
    attempts: int = 3,
    base_delay: float = 0.05,
    max_delay: float = 0.25,
) -> T:
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
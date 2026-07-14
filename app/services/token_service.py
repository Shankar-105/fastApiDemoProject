import secrets
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
import structlog

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import models, oauth2
from app.config import settings


logger = structlog.get_logger(__name__)


def _hash_refresh_token(token_str: str) -> str:
    """Return the SHA-256 hex digest of *token_str*.

    We never store raw refresh tokens in the database.  The token table
    contains only hashes, so a DB leak doesn't expose usable tokens.
    """
    return hashlib.sha256(token_str.encode("utf-8")).hexdigest()


async def create_refresh_token(
    db: AsyncSession, user_id: int, family_id: str | None = None
) -> str:
    """Create a new refresh token row for *user_id* and return the raw token string.

    The token is a cryptographically random 43-character string
    (``secrets.token_urlsafe(32)``).  Only its SHA-256 hash is stored in
    the database.

    If *family_id* is ``None`` (first-time login), a new family UUID is
    generated.  During rotation the caller passes the existing family ID
    so all tokens from the same login session remain linked.

    **Does not commit** — the caller is responsible for committing the
    transaction, allowing atomic multi-row operations like rotation
    (revoke old + insert new in one commit).

    Args:
        db: Active async DB session.
        user_id: Owner of this refresh token.
        family_id: UUID grouping tokens by login session. ``None`` for new logins.

    Returns:
        The raw (unhashed) token string to return to the client.
    """
    logger.info("refresh_token_creating", user_id=user_id)
    token_str = secrets.token_urlsafe(32)
    if family_id is None:
        family_id = str(uuid.uuid4())

    row = models.RefreshToken(
        token=_hash_refresh_token(token_str),
        user_id=user_id,
        family_id=family_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(row)
    return token_str


async def rotate_refresh_token(
    db: AsyncSession, old_token_str: str
) -> tuple[str, str]:
    """Revoke *old_token_str* and issue a fresh access + refresh token pair.

    Implements refresh token rotation with a 60-second grace window in Redis
    so that harmless retries (network issues, client timeout) return the same
    successor tokens instead of triggering full family revocation.

    **Reuse detection**: if the old token is already revoked and the grace
    window has expired, we treat this as a stolen-token attack and revoke
    **all** tokens in the family (``revoke_family``).  The user must log in
    again.

    **Locking**: We ``SELECT … FOR UPDATE`` on the old token row to prevent
    concurrent rotations from racing.

    **Atomicity**: The revocation and new-token insert happen in a single
    commit, so the rotation is atomic.

    Args:
        db: Active async DB session.
        old_token_str: The raw refresh token string from the client.

    Returns:
        Tuple of ``(access_token, new_refresh_token)``.

    Raises:
        HTTPException 401: if token not found, expired, or reuse detected.
    """
    from fastapi import HTTPException, status  # local import to avoid circular
    from app.services import redis_service
    import json
    old_token_hash = _hash_refresh_token(old_token_str)
    logger.info("refresh_token_rotating")

    result = await db.execute(
        select(models.RefreshToken)
        .where(
            models.RefreshToken.token == old_token_hash
        )
        .with_for_update()
    )
    old_row = result.scalars().first()

    # ── Token not found at all ──
    if old_row is None:
        logger.warning("Refresh token rotation failed: token not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    # ── Token was already revoked (could be a retry or a real reuse) ──
    if old_row.revoked:
        # Check the 60-second grace window in Redis — if this is a harmless
        # retry of a successful rotation, return the same successor tokens.
        grace_key = f"rotation_grace:{old_token_hash}"
        try:
            grace_data = await redis_service.redis_client.get(grace_key)
            if grace_data:
                cached = json.loads(grace_data)
                logger.info("Refresh token rotation retry — returning cached successor")
                return cached["access_token"], cached["refresh_token"]
        except Exception:
            pass

        logger.warning("Refresh token reuse detected; revoking family", extra={"extra_info": {"family_id": old_row.family_id}})
        await revoke_family(db, old_row.family_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions revoked — please log in again.",
        )

    # ── Token expired ──
    if old_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        old_row.revoked = True
        await db.commit()
        logger.warning("Refresh token expired", extra={"extra_info": {"user_id": old_row.user_id}})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired. Please log in again.",
        )

    # ── All good — rotate ──
    old_row.revoked = True  # kill the old token

    new_refresh = await create_refresh_token(
        db, user_id=old_row.user_id, family_id=old_row.family_id
    )
    await db.commit()  # atomic commit: revoke old + insert new

    # Fetch the user to build the access token payload
    user_result = await db.execute(
        select(models.User).where(models.User.id == old_row.user_id)
    )
    user = user_result.scalars().first()
    access_token = await oauth2.createAccessToken(
        {"userId": user.id, "userName": user.username}
    )

    # Store the successor tokens in Redis for a 60-second grace window,
    # so harmless retries of this same rotation return the same pair
    # instead of being treated as a reuse attack.
    try:
        grace_key = f"rotation_grace:{old_token_hash}"
        grace_value = json.dumps({"access_token": access_token, "refresh_token": new_refresh})
        await redis_service.redis_client.set(grace_key, grace_value, ex=60)
    except Exception:
        pass

    logger.info("Refresh token rotated successfully", extra={"extra_info": {"user_id": old_row.user_id}})

    return access_token, new_refresh


async def revoke_family(db: AsyncSession, family_id: str) -> None:
    """Mark ALL tokens in *family_id* as revoked.

    Called when a reused (stolen) refresh token is detected.  This locks
    the user out of all sessions that share this family — they must log
    in again.

    The commit happens inside this function since it's always a standalone
    operation (never part of a larger transaction).
    """
    logger.info("Revoking refresh token family", extra={"extra_info": {"family_id": family_id}})
    await db.execute(
        update(models.RefreshToken)
        .where(models.RefreshToken.family_id == family_id)
        .values(revoked=True)
    )
    await db.commit()


async def revoke_all_user_tokens(db: AsyncSession, user_id: int) -> None:
    """Revoke every refresh token for *user_id*.

    Called on password change or logout.  Forces all existing sessions
    to re-authenticate.
    """
    logger.info("Revoking all refresh tokens for user", extra={"extra_info": {"user_id": user_id}})
    await db.execute(
        update(models.RefreshToken)
        .where(models.RefreshToken.user_id == user_id)
        .values(revoked=True)
    )
    await db.commit()

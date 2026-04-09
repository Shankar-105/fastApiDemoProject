import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import models, oauth2
from app.config import settings


async def create_refresh_token(
    db: AsyncSession, user_id: int, family_id: str | None = None
) -> str:

    token_str = secrets.token_urlsafe(32)  # 43-char cryptographically random
    if family_id is None:
        family_id = str(uuid.uuid4())

    row = models.RefreshToken(
        token=token_str,
        user_id=user_id,
        family_id=family_id,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(row)
    await db.commit()
    return token_str


async def rotate_refresh_token(
    db: AsyncSession, old_token_str: str
) -> tuple[str, str]:
    
    from fastapi import HTTPException, status  # local import to avoid circular

    result = await db.execute(
        select(models.RefreshToken).where(
            models.RefreshToken.token == old_token_str
        )
    )
    old_row = result.scalars().first()

    # ── Token not found at all ──
    if old_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    # ── Reuse detected — token was already revoked ──
    # Someone (attacker or real user) is replaying an old token.
    # Revoke the ENTIRE family to cut off both parties.
    if old_row.revoked:
        await revoke_family(db, old_row.family_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected. All sessions revoked — please log in again.",
        )

    # ── Token expired ──
    if old_row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        old_row.revoked = True
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired. Please log in again.",
        )

    # ── All good — rotate ──
    old_row.revoked = True  # kill the old token
    await db.flush()  # persist revocation before creating the new one

    new_refresh = await create_refresh_token(
        db, user_id=old_row.user_id, family_id=old_row.family_id
    )

    # Fetch the user to build the access token payload
    user_result = await db.execute(
        select(models.User).where(models.User.id == old_row.user_id)
    )
    user = user_result.scalars().first()
    access_token = await oauth2.createAccessToken(
        {"userId": user.id, "userName": user.username}
    )

    return access_token, new_refresh


async def revoke_family(db: AsyncSession, family_id: str) -> None:
    """Mark ALL tokens in this family as revoked (reuse detection response)."""
    await db.execute(
        update(models.RefreshToken)
        .where(models.RefreshToken.family_id == family_id)
        .values(revoked=True)
    )
    await db.commit()


async def revoke_all_user_tokens(db: AsyncSession, user_id: int) -> None:
    """Revoke every refresh token for a user (called on password change)."""
    await db.execute(
        update(models.RefreshToken)
        .where(models.RefreshToken.user_id == user_id)
        .values(revoked=True)
    )
    await db.commit()

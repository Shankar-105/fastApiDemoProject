from datetime import datetime
from sqlalchemy import select, delete
from app.celery_app import celery_app
from app.db import AsyncSessionLocal
from app.models import OTP


@celery_app.task(bind=True)
def cleanup_expired_otps(self):
    """Celery beat task: delete OTP records that have passed their expiry.

    Runs hourly (via beat_schedule) to prevent the otps table from
    accumulating stale rows. Reads the current UTC time and deletes
    all rows where expires_at <= now.
    """
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            await db.execute(delete(OTP).where(OTP.expires_at <= now))
            await db.commit()
    
    import asyncio
    asyncio.run(_cleanup())
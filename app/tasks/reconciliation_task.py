import asyncio

from app.celery_app import celery_app
from app.db import AsyncSessionLocal
from app.services.reconciliation_service import reconcile_denormalized_counters


@celery_app.task(bind=True)
def reconcile_denormalized_counters_task(self):
    """Celery beat task: reconcile denormalized counter columns (followers_cnt, etc.)

    Runs every 6 hours via beat_schedule. Calls the reconciliation service
    which counts actual rows in the connections/votes tables and updates
    the cached counters in users and posts to fix any drift.
    """
    async def _reconcile():
        async with AsyncSessionLocal() as db:
            return await reconcile_denormalized_counters(db)

    return asyncio.run(_reconcile())
import asyncio

from app.celery_app import celery_app
from app.db import AsyncSessionLocal
from app.services.reconciliation_service import reconcile_denormalized_counters


@celery_app.task(bind=True)
def reconcile_denormalized_counters_task(self):
    async def _reconcile():
        async with AsyncSessionLocal() as db:
            return await reconcile_denormalized_counters(db)

    return asyncio.run(_reconcile())
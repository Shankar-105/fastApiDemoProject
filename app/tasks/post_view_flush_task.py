from typing import List, Dict
import asyncio
from sqlalchemy import text
from app.celery_app import celery_app
from app.services.redis_service import redis_client
from app.db import async_engine


@celery_app.task(name="app.tasks.post_view_flush.flush_post_views")
def flush_post_views() -> None:
    """Celery beat task: flush queued post views from Redis into Postgres in a single bulk update.

    Behavior:
    - Reads all members from `post:views:queue` (members are "{post_id}:{user_id}").
    - Counts views per `post_id` and performs one `UPDATE ... FROM (VALUES ...)` SQL statement
      to increment `posts.views` for all affected posts in a single query.
    - Removes only the processed members from the Redis set.

    This task is safe to run infrequently (every 5 minutes). Redis entries are not expired
    automatically so the task controls removal.
    """

    async def _do_flush():
        members = await redis_client.smembers("post:views:queue")
        if not members:
            return

        counts: Dict[int, int] = {}
        to_remove: List[str] = []
        for m in members:
            try:
                post_id_str, _ = m.split(":", 1)
                pid = int(post_id_str)
                counts[pid] = counts.get(pid, 0) + 1
                to_remove.append(m)
            except Exception:
                # ignore malformed entries
                continue

        if not counts:
            # remove any malformed entries
            if to_remove:
                await redis_client.srem("post:views:queue", *to_remove)
            return

        # Build VALUES list for SQL (param-safe via text replacement since values are ints)
        values_sql = ",".join([f"({pid},{inc})" for pid, inc in counts.items()])
        table_name = "posts"
        sql = f"""
        UPDATE {table_name}
        SET views = {table_name}.views + data.increment
        FROM (VALUES {values_sql}) AS data(post_id, increment)
        WHERE {table_name}.id = data.post_id
        """

        try:
            async with async_engine.begin() as conn:
                await conn.execute(text(sql))
        except Exception:
            # Allow the task to be retried later; do not remove Redis entries on failure
            return

        # Remove processed members from Redis set
        try:
            await redis_client.srem("post:views:queue", *to_remove)
        except Exception:
            # If removal fails it's okay — items will be retried next tick
            pass

    asyncio.run(_do_flush())
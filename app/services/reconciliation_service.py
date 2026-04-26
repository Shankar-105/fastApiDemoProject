from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app import models


async def reconcile_denormalized_counters(db: AsyncSession) -> dict[str, int]:
    """Repair denormalized counters from source-of-truth tables."""
    repaired: dict[str, int] = {}

    msg_reaction_count = (
        select(func.count(models.MessageReaction.id))
        .where(models.MessageReaction.message_id == models.Message.id)
        .scalar_subquery()
    )
    msg_result = await db.execute(
        update(models.Message)
        .where(models.Message.reaction_cnt != msg_reaction_count)
        .values(reaction_cnt=msg_reaction_count)
    )
    repaired["message_reaction_cnt"] = msg_result.rowcount or 0

    shared_reaction_count = (
        select(func.count(models.SharedPostReaction.id))
        .where(models.SharedPostReaction.shared_post_id == models.SharedPost.id)
        .scalar_subquery()
    )
    shared_result = await db.execute(
        update(models.SharedPost)
        .where(models.SharedPost.reaction_cnt != shared_reaction_count)
        .values(reaction_cnt=shared_reaction_count)
    )
    repaired["shared_post_reaction_cnt"] = shared_result.rowcount or 0

    post_comment_count = (
        select(func.count(models.Comments.id))
        .where(models.Comments.post_id == models.Post.id)
        .scalar_subquery()
    )
    comment_result = await db.execute(
        update(models.Post)
        .where(models.Post.comments_cnt != post_comment_count)
        .values(comments_cnt=post_comment_count)
    )
    repaired["post_comments_cnt"] = comment_result.rowcount or 0

    post_view_count = (
        select(func.count(models.PostView.user_id))
        .where(models.PostView.post_id == models.Post.id)
        .scalar_subquery()
    )
    view_result = await db.execute(
        update(models.Post)
        .where(models.Post.views != post_view_count)
        .values(views=post_view_count)
    )
    repaired["post_views"] = view_result.rowcount or 0

    post_likes_count = (
        select(func.count(models.Votes.user_id))
        .where(models.Votes.post_id == models.Post.id, models.Votes.action == True)
        .scalar_subquery()
    )
    likes_result = await db.execute(
        update(models.Post)
        .where(models.Post.likes != post_likes_count)
        .values(likes=post_likes_count)
    )
    repaired["post_likes"] = likes_result.rowcount or 0

    post_dislikes_count = (
        select(func.count(models.Votes.user_id))
        .where(models.Votes.post_id == models.Post.id, models.Votes.action == False)
        .scalar_subquery()
    )
    dislikes_result = await db.execute(
        update(models.Post)
        .where(models.Post.dis_likes != post_dislikes_count)
        .values(dis_likes=post_dislikes_count)
    )
    repaired["post_dislikes"] = dislikes_result.rowcount or 0

    await db.commit()
    return repaired

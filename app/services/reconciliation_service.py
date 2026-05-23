from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app import models


logger = logging.getLogger("app")


async def reconcile_denormalized_counters(db: AsyncSession) -> dict[str, int]:
    """Repair denormalized counters from source-of-truth tables."""
    repaired: dict[str, int] = {}
    logger.info("Starting denormalized counter reconciliation")

    following_count = (
        select(func.count())
        .select_from(models.connections)
        .where(models.connections.c.follower_id == models.User.id)
        .scalar_subquery()
    )
    following_result = await db.execute(
        update(models.User)
        .where(models.User.following_cnt != following_count)
        .values(following_cnt=following_count)
    )
    repaired["user_following_cnt"] = following_result.rowcount or 0

    followers_count = (
        select(func.count())
        .select_from(models.connections)
        .where(models.connections.c.followed_id == models.User.id)
        .scalar_subquery()
    )
    followers_result = await db.execute(
        update(models.User)
        .where(models.User.followers_cnt != followers_count)
        .values(followers_cnt=followers_count)
    )
    repaired["user_followers_cnt"] = followers_result.rowcount or 0

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

    comment_like_count = (
        select(func.count(models.CommentVotes.user_id))
        .where(models.CommentVotes.comment_id == models.Comments.id, models.CommentVotes.like == True)
        .scalar_subquery()
    )
    comment_like_result = await db.execute(
        update(models.Comments)
        .where(models.Comments.likes != comment_like_count)
        .values(likes=comment_like_count)
    )
    repaired["comment_likes"] = comment_like_result.rowcount or 0

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
    logger.info("Completed denormalized counter reconciliation", extra={"extra_info": repaired})
    return repaired

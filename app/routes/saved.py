from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import db, models, oauth2, schemas as sch
from app.blob_service import get_blob_url

router = APIRouter(tags=["saved"])


def _build_post_detail(post: models.Post, is_liked: bool) -> sch.PostDetailResponse:
    media_url = get_blob_url("posts-media", post.media_path) if post.media_path else None
    owner = sch.UserBasicResponse(
        id=post.user.id,
        username=post.user.username,
        nickname=post.user.nickname,
        profile_pic=post.user.profile_picture,
    )
    return sch.PostDetailResponse(
        id=post.id,
        title=post.title,
        content=post.content,
        media_url=media_url,
        media_type=post.media_type,
        likes=post.likes,
        dislikes=post.dis_likes,
        views=post.views,
        comments_count=post.comments_cnt,
        enable_comments=post.enable_comments,
        hashtags=post.hashtags,
        created_at=post.created_at,
        is_liked=is_liked,
        owner=owner,
    )


@router.post("/saved/{post_id}", status_code=status.HTTP_201_CREATED, response_model=sch.SuccessResponse)
async def save_post(
    post_id: int,
    db_session: AsyncSession = Depends(db.getDb),
    current_user: models.User = Depends(oauth2.getCurrentUser),
):
    post_result = await db_session.execute(select(models.Post).where(models.Post.id == post_id))
    post = post_result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    existing_result = await db_session.execute(
        select(models.SavedPost).where(
            models.SavedPost.user_id == current_user.id,
            models.SavedPost.post_id == post_id,
        )
    )
    existing = existing_result.scalars().first()
    if existing:
        return sch.SuccessResponse(message="Post already saved")

    saved = models.SavedPost(user_id=current_user.id, post_id=post_id)
    db_session.add(saved)
    await db_session.commit()

    return sch.SuccessResponse(message="Post saved")


@router.delete("/saved/{post_id}", status_code=status.HTTP_200_OK, response_model=sch.SuccessResponse)
async def unsave_post(
    post_id: int,
    db_session: AsyncSession = Depends(db.getDb),
    current_user: models.User = Depends(oauth2.getCurrentUser),
):
    saved_result = await db_session.execute(
        select(models.SavedPost).where(
            models.SavedPost.user_id == current_user.id,
            models.SavedPost.post_id == post_id,
        )
    )
    saved = saved_result.scalars().first()
    if not saved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved post not found")

    await db_session.delete(saved)
    await db_session.commit()
    return sch.SuccessResponse(message="Saved post removed")


@router.get("/saved/me", status_code=status.HTTP_200_OK, response_model=sch.SavedPostsResponse)
async def get_saved_posts(
    db_session: AsyncSession = Depends(db.getDb),
    current_user: models.User = Depends(oauth2.getCurrentUser),
):
    saved_result = await db_session.execute(
        select(models.SavedPost)
        .where(models.SavedPost.user_id == current_user.id)
        .order_by(models.SavedPost.created_at.desc())
    )
    saved_rows = saved_result.scalars().all()

    if not saved_rows:
        return sch.SavedPostsResponse(saved=[])

    post_ids = [row.post_id for row in saved_rows]
    likes_result = await db_session.execute(
        select(models.Votes.post_id).where(
            models.Votes.user_id == current_user.id,
            models.Votes.action == True,
            models.Votes.post_id.in_(post_ids),
        )
    )
    liked_ids = {row[0] for row in likes_result.all()}

    payload = []
    for row in saved_rows:
        if not row.post:
            continue
        payload.append(
            sch.SavedPostItemResponse(
                id=row.id,
                post_id=row.post_id,
                saved_at=row.created_at,
                post=_build_post_detail(row.post, row.post_id in liked_ids),
            )
        )

    return sch.SavedPostsResponse(saved=payload)

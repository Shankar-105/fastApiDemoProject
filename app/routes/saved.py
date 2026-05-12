from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app import db, models, oauth2, schemas as sch
from app.services.blob_service import get_blob_url

router = APIRouter(
    prefix="",
    tags=["Saved Posts"]
)


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


@router.post("/posts/{post_id}/save", status_code=status.HTTP_201_CREATED, response_model=sch.SuccessResponse)
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


@router.delete("/posts/{post_id}/unsave", status_code=status.HTTP_200_OK, response_model=sch.SuccessResponse)
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


@router.get("/users/me/saved-posts", status_code=status.HTTP_200_OK, response_model=sch.SavedPostsResponse)
async def get_saved_posts(
    db_session: AsyncSession = Depends(db.getDb),
    current_user: models.User = Depends(oauth2.getCurrentUser),
):
    is_liked = (
        select(models.Votes.post_id)
        .where(
            models.Votes.user_id == current_user.id,
            models.Votes.post_id == models.Post.id,
            models.Votes.action == True,
        )
        .exists()
        .label("is_liked")
    )
    saved_result = await db_session.execute(
        select(
            models.SavedPost.id.label("saved_id"),
            models.SavedPost.post_id.label("saved_post_id"),
            models.SavedPost.created_at.label("saved_at"),
            models.Post.id.label("post_id"),
            models.Post.title,
            models.Post.content,
            models.Post.media_path,
            models.Post.media_type,
            models.Post.likes,
            models.Post.dis_likes,
            models.Post.views,
            models.Post.comments_cnt,
            models.Post.enable_comments,
            models.Post.hashtags,
            models.Post.created_at.label("post_created_at"),
            models.User.id.label("owner_id"),
            models.User.username.label("owner_username"),
            models.User.nickname.label("owner_nickname"),
            models.User.profile_picture.label("owner_profile_picture"),
            is_liked,
        )
        .join(models.Post, models.Post.id == models.SavedPost.post_id)
        .join(models.User, models.User.id == models.Post.user_id)
        .where(models.SavedPost.user_id == current_user.id)
        .order_by(models.SavedPost.created_at.desc())
    )
    saved_rows = saved_result.all()

    if not saved_rows:
        return sch.SavedPostsResponse(saved=[])

    payload = []
    for row in saved_rows:
        item = row._mapping
        media_url = get_blob_url("posts-media", item["media_path"]) if item["media_path"] else None
        owner = sch.UserBasicResponse(
            id=item["owner_id"],
            username=item["owner_username"],
            nickname=item["owner_nickname"],
            profile_pic=item["owner_profile_picture"],
        )
        post = sch.PostDetailResponse(
            id=item["post_id"],
            title=item["title"],
            content=item["content"],
            media_url=media_url,
            media_type=item["media_type"],
            likes=item["likes"],
            dislikes=item["dis_likes"],
            views=item["views"],
            comments_count=item["comments_cnt"],
            enable_comments=item["enable_comments"],
            hashtags=item["hashtags"],
            created_at=item["post_created_at"],
            is_liked=bool(item["is_liked"]),
            owner=owner,
        )
        payload.append(
            sch.SavedPostItemResponse(
                id=item["saved_id"],
                post_id=item["saved_post_id"],
                saved_at=item["saved_at"],
                post=post,
            )
        )

    return sch.SavedPostsResponse(saved=payload)


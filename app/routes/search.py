from fastapi import HTTPException,status,APIRouter,Depends
from app import models,db,schemas as sch,oauth2
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,func
from app.services.blob_service import get_blob_url
import logging

router=APIRouter(
    prefix="",
    tags=['Search']
)

logger = logging.getLogger("app")

@router.get("/search", status_code=status.HTTP_202_ACCEPTED, response_model=sch.SearchResultResponse)
async def search(searchParams: sch.SearchRequest = Depends(), db: AsyncSession = Depends(db.getDb), currenUser: models.User = Depends(oauth2.getCurrentUser)):
    logger.info(f"Search request from user {currenUser.id}: query='{searchParams.q}', orderBy='{searchParams.orderBy}'")
    if searchParams.q and searchParams.q.startswith("#"):
        hashtag = searchParams.q.lstrip("#")
        hashtag_filter = models.Post.hashtags.ilike(f"%{hashtag}%")
        total_count = func.count(models.Post.id).over().label("total_count")
        base_query = select(models.Post, total_count).where(models.Post.hashtags.isnot(None), hashtag_filter)
        if searchParams.orderBy == "likes":
            base_query = base_query.order_by(models.Post.likes.desc(), models.Post.created_at.desc())
        else:
            base_query = base_query.order_by(models.Post.created_at.desc())
        
        postsResult=await db.execute(base_query.offset(searchParams.offset).limit(searchParams.limit))
        rows=postsResult.all()
        resPosts=[row[0] for row in rows]
        total = int(rows[0][1]) if rows else 0
        
        posts = []
        for post in resPosts:
            posts.append(sch.PostListItemResponse(
                id=post.id,
                title=post.title,
                media_url=get_blob_url("posts-media", post.media_path) if post.media_path else None,
                media_type=post.media_type,
                likes=post.likes,
                comments_count=post.comments_cnt,
                created_at=post.created_at
            ))
        
        logger.info(f"Hashtag search completed: '{searchParams.q}', results: {total}")
        return sch.SearchResultResponse(
            result_type="posts",
            posts=posts,
            total=total
        )
    elif searchParams.q:
        user_filter = models.User.username.ilike(f"%{searchParams.q}%")
        total_count = func.count(models.User.id).over().label("total_count")
        usersResult=await db.execute(
            select(models.User, total_count)
            .where(user_filter)
            .order_by(models.User.username.asc())
            .offset(searchParams.offset)
            .limit(searchParams.limit)
        )
        rows=usersResult.all()
        resUsers=[row[0] for row in rows]
        total = int(rows[0][1]) if rows else 0
        
        users = []
        for user in resUsers:
            users.append(sch.UserBasicResponse(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                profile_pic=user.profile_picture
            ))
        
        logger.info(f"Username search completed: '{searchParams.q}', results: {total}")
        return sch.SearchResultResponse(
            result_type="users",
            users=users,
            total=total
        )
    else:
        logger.warning(f"Search failed - no query parameters provided by user {currenUser.id}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Query Parameters Required")

from fastapi import HTTPException,status,APIRouter,Depends
from app import models,db,schemas as sch,oauth2
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,func
from app.services.blob_service import get_blob_url
router=APIRouter(tags=['search'])

@router.get("/search", status_code=status.HTTP_202_ACCEPTED, response_model=sch.SearchResultResponse)
async def search(searchParams: sch.SearchRequest = Depends(), db: AsyncSession = Depends(db.getDb), currenUser: models.User = Depends(oauth2.getCurrentUser)):
    if searchParams.q and searchParams.q.startswith("#"):
        # Hashtag search - search for posts
        hashtag = searchParams.q.lstrip("#")
        hashtag_filter = models.Post.hashtags.ilike(f"%{hashtag}%")
        hashtag_rank = func.similarity(func.coalesce(models.Post.hashtags, ""), hashtag)
        base_query=select(models.Post).where(models.Post.hashtags.isnot(None), hashtag_filter)
        if searchParams.orderBy == "likes":
            base_query=base_query.order_by(models.Post.likes.desc(), hashtag_rank.desc(), models.Post.created_at.desc())
        else:
            base_query=base_query.order_by(hashtag_rank.desc(), models.Post.created_at.desc())

        # Count total
        count_query=select(func.count()).select_from(models.Post).where(models.Post.hashtags.isnot(None), hashtag_filter)
        totalResult=await db.execute(count_query)
        total=totalResult.scalar()
        
        # Fetch paginated results
        postsResult=await db.execute(base_query.offset(searchParams.offset).limit(searchParams.limit))
        resPosts=postsResult.scalars().all()
        
        # Build proper response for posts
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
        
        return sch.SearchResultResponse(
            result_type="posts",
            posts=posts,
            total=total
        )
    elif searchParams.q:
        # Username search - search for users
        user_filter = models.User.username.ilike(f"%{searchParams.q}%")
        usersResult=await db.execute(
            select(models.User)
            .where(user_filter)
            .order_by(func.similarity(models.User.username, searchParams.q).desc(), models.User.username.asc())
            .offset(searchParams.offset)
            .limit(searchParams.limit)
        )
        resUsers=usersResult.scalars().all()

        countResult=await db.execute(select(func.count()).select_from(models.User).where(user_filter))
        total=countResult.scalar()
        
        # Build proper response for users
        users = []
        for user in resUsers:
            users.append(sch.UserBasicResponse(
                id=user.id,
                username=user.username,
                nickname=user.nickname,
                profile_pic=user.profile_picture
            ))
        
        return sch.SearchResultResponse(
            result_type="users",
            users=users,
            total=total
        )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Query Parameters Required")

from fastapi import status,HTTPException,Depends,Body,APIRouter,Form,Query
from fastapi.responses import FileResponse
import app.schemas as sch
from typing import List
from app import models,db,oauth2
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_,distinct,func,case,update
import os
import asyncio
from fastapi import UploadFile,File
from app.services.redis_service import delete_cache
from app.services.blob_service import upload_blob, delete_blob, get_blob_url

router=APIRouter(
    tags=['me']
)

@router.get("/me/profile",status_code=status.HTTP_200_OK,response_model=sch.UserProfileResponse)
async def myProfile(db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Count posts via query for accuracy
    posts_count_result = await db.execute(select(func.count()).select_from(models.Post).where(models.Post.user_id==currentUser.id))
    posts_count = posts_count_result.scalar()
    return sch.UserProfileResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        bio=currentUser.bio or "",
        profile_picture=currentUser.profile_picture,
        posts_count=posts_count,
        followers_count=currentUser.followers_cnt,
        following_count=currentUser.following_cnt,
        created_at=currentUser.created_at
    )

@router.get("/me/profile/pic",status_code=status.HTTP_200_OK, response_model=sch.MediaInfo)
async def myProfilePicture(db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # get the current users profile pic
    profilePicturePath = currentUser.profile_picture
    # if he doesnt have a porfile pic return 404
    if not profilePicturePath:
        raise HTTPException(status_code=404, detail="No profile picture")
    return sch.MediaInfo(
        url=get_blob_url("profilepics", profilePicturePath),
        type="image"
    )
@router.delete("/me/profilepic/delete",status_code=status.HTTP_200_OK, response_model=sch.SuccessResponse)
async def removeProfilePicture(db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    profilePic=currentUser.profile_picture
    if not profilePic:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="No profile picture to remove")
    await delete_blob("profilepics", profilePic)
    currentUser.profile_picture=None
    await db.commit()
    # profile changed - bust the cached profile for this user
    await delete_cache(f"user_profile:{currentUser.id}")
    return sch.SuccessResponse(message="Profile picture removed successfully")

# retrives all posts using sqlAlchemy
@router.get("/me/posts", response_model=sch.PostListResponse)  
async def getAllPosts(limit:int=Query(10, ge=1, le=100),
    offset: int = Query(0,ge=0),
    db:AsyncSession=Depends(db.getDb),
    currentUser:models.User=Depends(oauth2.getCurrentUser)
    ):
    # calculate the total number of posts of the currentuser
    countResult=await db.execute(select(func.count()).select_from(models.Post).where(models.Post.user_id==currentUser.id))
    total=countResult.scalar()
    # only fetch the first 'limit' posts after skipping the first 'offset' posts
    # and order them by the latest as first
    postsResult=await db.execute(select(models.Post).where(models.Post.user_id==currentUser.id).order_by(models.Post.created_at.desc()).offset(offset).limit(limit))
    paginatedPosts=postsResult.scalars().all()
    
    # Get all post IDs the user has liked
    votesResult=await db.execute(select(models.Votes.post_id).where(models.Votes.user_id == currentUser.id, models.Votes.action == True))
    liked_post_ids = {row[0] for row in votesResult.all()}
    
    # Build proper response
    posts = []
    for post in paginatedPosts:
        media_url = None
        if post.media_path:
            media_url = get_blob_url("posts-media", post.media_path)
        posts.append(sch.PostListItemResponse(
            id=post.id,
            title=post.title,
            media_url=media_url,
            media_type=post.media_type,
            likes=post.likes,
            comments_count=post.comments_cnt,
            created_at=post.created_at,
            is_liked=post.id in liked_post_ids
        ))
    
    pagination = sch.PaginationMetadata(
        total=total,
        limit=limit,
        offset=offset,
        has_more=(limit+offset)<total
    )
    
    return sch.PostListResponse(
        posts=posts,
        pagination=pagination
    )
# a patch endpoint so that user can update what he wants to unlike put
# profile picture cannot be taken as a json data so it must be passed via Form
# and the username and bio can be passed via Body params but its resulting in an
# ambiguity as one of the section is being passed via Form and the other via Body
# so made everything to be passed via Form only
@router.patch("/me/updateInfo",status_code=status.HTTP_200_OK, response_model=sch.UserProfileResponse)
async def updateUserInfo(username:str=Form(None),bio:str=Form(None),profile_picture:UploadFile=File(None),db:AsyncSession=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # to store updates the user does
    updates={}
    if username:
        dupResult=await db.execute(select(models.User).where(models.User.username == username,models.User.id !=currentUser.id))
        if dupResult.scalars().first():
            raise HTTPException(status_code=400, detail="Username already taken")
        updates["username"] = username
    if bio:
        updates['bio']=bio
    if profile_picture:
        allowedFileTypes=['image/jpeg','image/png','image/gif']
        if profile_picture.content_type not in allowedFileTypes:
            raise HTTPException(status_code=400,detail="only jpeg,png,gif files allowed")
        blob_name=f"{currentUser.username}_{profile_picture.filename}"
        content_bytes = await profile_picture.read()
        await upload_blob("profilepics", blob_name, content_bytes, profile_picture.content_type)
        updates['profile_picture']=blob_name
        # if any updates update them
    if updates:
        await db.execute(update(models.User).where(models.User.id==currentUser.id).values(**updates))
        await db.commit()
        await db.refresh(currentUser)
        # profile changed - bust the cached profile for this user
        await delete_cache(f"user_profile:{currentUser.id}")
    
    # Count posts for response
    posts_count_result = await db.execute(select(func.count()).select_from(models.Post).where(models.Post.user_id==currentUser.id))
    posts_count = posts_count_result.scalar()
    
    # Build proper response
    return sch.UserProfileResponse(
        id=currentUser.id,
        username=currentUser.username,
        nickname=currentUser.nickname,
        bio=currentUser.bio,
        profile_picture=currentUser.profile_picture,
        posts_count=posts_count,
        followers_count=currentUser.followers_cnt,
        following_count=currentUser.following_cnt,
        created_at=currentUser.created_at
    )

@router.get("/me/votedOnPosts",status_code=status.HTTP_200_OK)
async def getVotedPosts(db:AsyncSession=Depends(db.getDb),currentUser:models.User =Depends(oauth2.getCurrentUser)):
    # Query voted posts via join
    result=await db.execute(
        select(models.Post).join(models.Votes, models.Votes.post_id==models.Post.id)
        .where(models.Votes.user_id==currentUser.id)
    )
    voted_posts=result.scalars().all()
    return {
                f"{currentUser.username} you have voted on posts":
            [
                {
                "post title":f"{posts.title}",
                "post id":f"{posts.id}",
                "post owner":f"{posts.user.username}"
            } 
                for posts in voted_posts
        ]
    }

@router.get("/me/voteStats",status_code=status.HTTP_200_OK, response_model=sch.VoteStatsResponse)
async def voteStatus(db:AsyncSession=Depends(db.getDb),currentUser:models.User = Depends(oauth2.getCurrentUser)):
    # using the func,case and quering - BUG FIX: summary returns a list of Row objects
    result=await db.execute(
        select(
            func.count(case((models.Votes.action==True, 1))).label("likes"),
            func.count(case((models.Votes.action==False, 1))).label("dislikes")
        ).where(models.Votes.user_id==currentUser.id)
    )
    summary=result.first()
    
    return sch.VoteStatsResponse(
        liked_posts_count=summary.likes if summary else 0,
        disliked_posts_count=summary.dislikes if summary else 0
    )

@router.get("/me/likedPosts")
async def get_liked_posts(db:AsyncSession = Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Query liked posts
    result=await db.execute(
        select(models.Post)
        .join(models.Votes, models.Votes.post_id==models.Post.id)
        .where(and_(models.Votes.user_id==currentUser.id, models.Votes.action==True))
    )
    liked_posts=result.scalars().all()
    return {
        f"{currentUser.username} your liked posts includes":
        [
            {
                "post id":posts.id,
                "post owner":posts.user.username
            }
            for posts in liked_posts
        ]
    }
@router.get("/me/dislikedPosts")
async def get_disliked_posts(db:AsyncSession = Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):    # Query disliked posts
    result=await db.execute(
        select(models.Post)
        .join(models.Votes,models.Votes.post_id==models.Post.id)
        .where(and_(models.Votes.user_id==currentUser.id, models.Votes.action==False))
    )
    liked_posts=result.scalars().all()
    return {
        f"{currentUser.username} your disliked posts includes":
        [
            {
                "post id":posts.id,
                "post owner":posts.user.username
            }
            for posts in liked_posts
        ]
    }

@router.get("/me/commented-on",status_code=status.HTTP_200_OK)
async def getCommentedPosts(db:AsyncSession=Depends(db.getDb),currentUser:models.User =Depends(oauth2.getCurrentUser)):
    # get the current users all commented posts id's ignore duplicates
    uniqueResult=await db.execute(select(distinct(models.Comments.post_id)).where(models.Comments.user_id==currentUser.id))
    uniquePostIds=uniqueResult.all()
    # the 'uniquePostIds' is a list of tuples where each tuple is
    # of the form (post_id1,) (post_id2,) so we exract the first elem
    # from each of the tuples in the list
    post_ids = [row[0] for row in uniquePostIds]
    # query for the post_ids in the Posts table
    postsResult=await db.execute(
        select(models.Post)
        .where(models.Post.id.in_(post_ids))
    )
    commented_posts=postsResult.scalars().all()
    return {
                f"{currentUser.username} you have commented on posts":
            [
                {
                "post title":f"{posts.title}",
                "post id":f"{posts.id}",
                "post owner":f"{posts.user.username}"
            } 
                for posts in commented_posts
        ]
    }

@router.get("/me/comment-stats",status_code=status.HTTP_200_OK, response_model=sch.CommentStatsResponse)
async def commentStatus(db:AsyncSession=Depends(db.getDb),currentUser:models.User = Depends(oauth2.getCurrentUser)):
    # Count total comments by user
    commentCountResult=await db.execute(select(func.count()).select_from(models.Comments).where(models.Comments.user_id==currentUser.id))
    comment_count=commentCountResult.scalar()
    # Count unique posts commented on
    uniquePostsResult=await db.execute(select(func.count(distinct(models.Comments.post_id))).where(models.Comments.user_id==currentUser.id))
    uniquePostIds=uniquePostsResult.scalar()
    return sch.CommentStatsResponse(
        total_comments=comment_count,
        unique_posts_commented=uniquePostIds
    )

from fastapi import status,HTTPException,Depends,Body,APIRouter,Form
from fastapi.responses import FileResponse
import app.schemas as sch
from typing import List
from app import models,db,oauth2
from sqlalchemy.orm import Session
import os,shutil
from fastapi import UploadFile,File
from sqlalchemy import and_,distinct,func,case

router=APIRouter(
    tags=['me']
)

@router.get("/me/profile",status_code=status.HTTP_200_OK,response_model=sch.UserProfile)
def myProfile(db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    currentUserProfile=sch.UserProfile(
        profilePicture=currentUser.profile_picture,
        username=currentUser.username,
        nickname=currentUser.nickname,
        bio=currentUser.bio,
        posts=len(currentUser.posts),
        followers=currentUser.followers_cnt,
        following=currentUser.following_cnt,
    )
    if not currentUserProfile.bio:
        currentUserProfile.bio=""
    if not currentUserProfile.profilePicture:
        currentUserProfile.profilePicture=""
    return currentUserProfile

@router.get("/me/profile/pic",status_code=status.HTTP_200_OK)
def myProfilePicture(db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # get the curretn users profile pic
    profilePicturePath = currentUser.profile_picture
    # if he doesnt have a porfile pic return 404
    if not profilePicturePath:
        raise HTTPException(status_code=404, detail="No profile picture")
    file_path=f"profilepics/{profilePicturePath}"
    # optional check
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Image not found")
    # return a FileResponse class response to view it directly
    # as in commit hash <96bd0a3> or else return the link and you can
    # view it in the broswer by entering the output url
    return sch.UserProfileDisplay.displayUserProfilePic(currentUser)
@router.delete("/me/profilepic/delete",status_code=status.HTTP_200_OK)
def removeProfilePicture(db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    profilePic=currentUser.profile_picture
    if not profilePic:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="no profile pic to remove")
    file_path=f"profilepics/{profilePic}"
    if os.path.exists(file_path):
        os.remove(file_path)
    currentUser.profile_picture=None
    db.commit()
    return {"message":"removed profile pic"}

# retrives all posts using sqlAlchemy
@router.get("/me/posts",response_model=List[sch.PostResponse])  
def getAllPosts(db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
   # allPosts=db.query(models.Post).filter(models.Post.user_id==currentUser.id).all()
   # simple way of querying 
   # Thanks to the relationship() method 
    allPosts=currentUser.posts
    return allPosts
# a patch endpoint so that user can update what he wants to unlike put
# profile picture cannot be taken as a json data so it must be passed via Form
# and the username and bio can be passed via Body params but its resulting in an
# ambiguity as one of the section is being passed via Form and the other via Body
# so made everything to be passed via Form only
@router.patch("/me/updateInfo",status_code=status.HTTP_200_OK)
def updateUserInfo(username:str=Form(None),bio:str=Form(None),profile_picture:UploadFile=File(None),db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # to store updates the user does
    updates={}
    if username:
        if db.query(models.User).filter(models.User.username == username,models.User.id !=currentUser.id).first():
            raise HTTPException(status_code=400, detail="Username already taken")
        updates["username"] = username
    if bio:
        updates['bio']=bio
    if profile_picture:
        # creating an profilepics directory to store the
        # users profile pics locally instead of inserting them
        # into the db which is a bad practice
        os.makedirs("profilepics", exist_ok=True)
        # allowing only certain file types
        # File.content_type method returns image/extension if its not
        # present in our list we raise an error
        allowedFileTypes=['image/jpeg','image/png','image/gif']
        if profile_picture.content_type not in allowedFileTypes:
            raise HTTPException(status_code=400,detail="only jpeg,png,gif files allowed")
        # file path to store in db we just store the filename in the db 
        # not the entire image or the entire path just the filename
        filename_toput_inDb=f"{currentUser.username}_{profile_picture.filename}"
        # this is the actual file path where the profile pics reside
        file_path=f"profilepics/{currentUser.username}_{profile_picture.filename}"
        # py methods to copy the argumented image in our file_path
        with open(file_path, "wb") as buffer:
           shutil.copyfileobj(profile_picture.file, buffer)
        updates['profile_picture']=filename_toput_inDb
        # if any updates update them
    if updates:
        db.query(models.User).filter(models.User.id==currentUser.id).update(updates)
        db.commit()
        db.refresh(currentUser)
    return updates

@router.get("/me/votedOnPosts",status_code=status.HTTP_200_OK)
def getVotedPosts(db:Session=Depends(db.getDb),currentUser:models.User =Depends(oauth2.getCurrentUser)):
    voted_posts=currentUser.voted_posts
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

@router.get("/me/voteStats",status_code=status.HTTP_200_OK)
def voteStatus(db:Session=Depends(db.getDb),currentUser:models.User = Depends(oauth2.getCurrentUser)):
    # using the func,case and quering in pass
    summary=db.query(
        func.count(case(models.Votes.action==True,1)).label("likes"),
        func.count(case(models.Votes.action==False,1)).label("dislikes")
    ).filter(models.User.id==currentUser.id).all()
    return {
        f"{currentUser.username} here's your vote stats":
       { 
           "number of liked posts":summary.likes,
           "number of dislked posts":summary.dislikes
       }
}

@router.get("/me/likedPosts")
def get_liked_posts(db:Session = Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    # Query liked posts
    liked_posts = (
        db.query(models.Post)
        .join(models.Votes, models.Votes.post_id==models.Post.id)
        .filter(and_(models.Votes.user_id==currentUser.id, models.Votes.action==True))
        .all()
    )
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
def get_liked_posts(db:Session = Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):    # Query disliked posts
    liked_posts = (
        db.query(models.Post)
        .join(models.Votes,models.Votes.post_id==models.Post.id)
        .filter(and_(models.Votes.user_id==currentUser.id, models.Votes.action==False))
        .all()
    )
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
def getCommentedPosts(db:Session=Depends(db.getDb),currentUser:models.User =Depends(oauth2.getCurrentUser)):
    # get the current users all commented posts id's ignore duplicates
    uniquePostIds=db.query(distinct(models.Comments.post_id)).filter(models.Comments.user_id==currentUser.id).all()
    # the 'uniquePostIds' is a list of tuples where each tuple is
    # of the form (post_id1,) (post_id2,) so we exract the first elem
    # from each of the tuples in the list
    post_ids = [row[0] for row in uniquePostIds]
    # query for the post_ids in the Posts table
    commented_posts=(
        db.query(models.Post)
        .filter(models.Post.id.in_(post_ids))
        .all()
    )
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

@router.get("/me/comment-stats",status_code=status.HTTP_200_OK)
def commentStatus(db:Session=Depends(db.getDb),currentUser:models.User = Depends(oauth2.getCurrentUser)):
    comment_count = currentUser.total_comments
    uniquePostIds=db.query(distinct(models.Comments.post_id)).filter(models.Comments.user_id==currentUser.id).count()
    return {
        f"{currentUser.username} here's your comment stats":
         f"you have a total of {len(comment_count)} comment's on {uniquePostIds} post's"
       }
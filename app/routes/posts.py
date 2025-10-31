from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import List
import app.schemas as sch
from app import models,oauth2
from app.db import getDb
from sqlalchemy.orm import Session
from sqlalchemy import and_

router=APIRouter(
    tags=['Posts']
)
# gets a specific post with id -> {postId}
@router.get("/posts/getPost/{postId}",response_model=sch.PostResponse)
def getPost(postId:int,db:Session=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    reqPost=db.query(models.Post).filter(and_(models.Post.id==postId,models.Post.user_id==currentUser.id)).first()
    if reqPost==None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with id {postId} not found")
    # is the post viewed before
    isViewed = db.query(models.PostView).filter(
        and_(models.PostView.post_id == postId, models.PostView.user_id == currentUser.id)
    ).first()
    # If no prior view, record the view and increment the count
    if not isViewed:
        # If no prior view, record the view and increment the count
        new_view = models.PostView(post_id=postId, user_id=currentUser.id)
        db.add(new_view)
        reqPost.views += 1
        db.commit()
        db.refresh(reqPost)  # Refresh to get updated post data
    return reqPost


# creates a new post using sqlAlchemy
@router.post("/posts/createPost",status_code=status.HTTP_201_CREATED,response_model=sch.PostResponse)
def createPosts(post:sch.PostEssentials=Body(...),db:Session=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    newPost=models.Post(**post.dict(),user_id=currentUser.id,views=1)
    db.add(newPost)
    db.commit()
    db.refresh(newPost)
    return newPost


# delets a specific post with the mentioned id -> {id}
@router.delete("/posts/deletePost/{postId}",response_model=sch.PostResponse)
def deletePost(postId:int,db:Session=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    postToDelete=db.query(models.Post).filter(and_(models.Post.id==postId,models.Post.user_id==currentUser.id)).first()
    if not postToDelete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {postId} not Found") 
    db.delete(postToDelete)
    db.commit()
    return postToDelete

# update a specific post with id -> {id}
@router.put("/posts/editPost/{postId}")
def editPost(postId:int,post:sch.PostEssentials,db:Session=Depends(getDb)):
    postToUpdate=db.query(models.Post).filter(models.Post.id==postId).first()
    if not postToUpdate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {postId} not Found")
    # from our argument of post we exclude the None values
    # and just pick up the set values and store into a dict update_data
    update_data = post.dict(exclude_unset=True)
    # now we traverse thorugh the update_data and put that data
    # in our postToUpdate
    for key, value in update_data.items():
        setattr(postToUpdate,key,value)
    # commit those updated changes
    db.commit()
    # refresh to qucikly view them below while returing 
    # if not refreshed below returned postToUpdate will be
    # sent as {} to the front End
    db.refresh(postToUpdate)
    return {"status":f"updated post with id {postId}","updatedPostData":postToUpdate}
from fastapi import status,HTTPException,Depends,Body,APIRouter
from typing import List
import app.schemas as sch
from app import models
from app.db import getDb
from sqlalchemy.orm import Session

router=APIRouter()
# retrives all posts using sqlAlchemy
@router.get("/posts/getAllPosts",response_model=List[sch.PostResponse])  
def getAllPosts(db:Session=Depends(getDb)):
    allPosts=db.query(models.Post).all()
    return allPosts

# gets a specific post with id -> {postId}
@router.get("/posts/getPost/{postId}")
def getPost(postId:int,db:Session=Depends(getDb)):
    reqPost=db.query(models.Post).filter(models.Post.id==postId).first()
    # same code when database isn't used
    '''
    reqPost=findPost(id)
    if reqPost==None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="post not found")
        # in the below code we're updating status code using Response class
        # response.status_code=status.HTTP_404_NOT_FOUND
        # return {"status":"post not found"} 
    '''
    if reqPost==None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with id {postId} not found")
    return {"status":"post found","data":reqPost}


# creates a new post using sqlAlchemy
@router.post("/posts/createPost",status_code=status.HTTP_201_CREATED)
def createPosts(post:sch.PostEssentials=Body(...),db:Session=Depends(getDb)):
    newPost=models.Post(**post.dict())
    db.add(newPost)
    db.commit()
    db.refresh(newPost)
    return {"status":"new post created","newPost Data":newPost}


# delets a specific post with the mentioned id -> {id}
@router.delete("/posts/deletePost/{postId}")
def deletePost(postId:int,db:Session=Depends(getDb)):
    
    postToDelete=db.query(models.Post).filter(models.Post.id==postId).first()
    if not postToDelete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {postId} not Found") 
    db.delete(postToDelete)
    db.commit()
    return {"status":f"deleted post with id {postId}","deletedPostData":postToDelete}

    # same code but without database
    '''postToDelete=findPost(id)
    if not postToDelete:
        # more prefered than just plainly returning as here
        # we are even changing the status code to 404
        # as the post is not found which is so practical
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {id} not Found")
        #return {"status":f"post with Id {id} not Found"}
    allPosts.remove(postToDelete)
    '''


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
     
    # same code without using databases psycopg setup!
    ''' idx=findPostIndex(id)
     if idx==-1:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {id} not Found")
     allPosts[idx]=post.dict()
     allPosts[idx]['id']=id
     '''
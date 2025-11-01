from fastapi import status,HTTPException,Depends,APIRouter,Form,UploadFile,File
import app.schemas as sch
from typing import Optional
from app import models,oauth2
from app.db import getDb
from sqlalchemy.orm import Session
from sqlalchemy import and_
import os,uuid,shutil
router=APIRouter(
    tags=['Posts']
)

MEDIA_FOLDER="posts_media"

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
@router.post("/posts/createPost",status_code=status.HTTP_201_CREATED)
def create_post(
    title:str=Form(...),
    content:str=Form(...),
    media:Optional[UploadFile]=File(None),  # Optional file
    db: Session=Depends(getDb),
    currentUser:dict=Depends(oauth2.getCurrentUser) 
):
    # set to None change if uploaded later
    media_path = None
    media_type = None
    if media:
        # ensure the file type is in bounds
        if media.content_type not in ["image/jpeg", "image/png", "video/mp4"]:
            raise HTTPException(400, "Only JPG, PNG, MP4 allowed")
        # Generate unique filename
        # using uuid Universally unique ID which generates a 36 characters
        ext=media.filename.split(".")[-1]
        filename=f"{uuid.uuid4()}.{ext}"
        file_path=os.path.join(MEDIA_FOLDER,filename)
        # transfer the data from args to the file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(media.file, buffer)
        # we will only store the filename in the db
        media_path=filename
        media_type="image" if media.content_type.startswith("image") else "video"
    new_post = models.Post(
        title=title,
        content=content,
        media_path=media_path,
        media_type=media_type,
        user_id=currentUser.id
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return {"message": "Post created!", "post": new_post}
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
def editPost(postId:int,post:sch.PostEssentials,db:Session=Depends(getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
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
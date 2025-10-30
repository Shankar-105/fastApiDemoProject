from fastapi import Body,HTTPException,status,APIRouter,Depends
from sqlalchemy.orm import Session
from app import oauth2,models,db,schemas as sch
from sqlalchemy import and_
router=APIRouter(tags=['comment'])

@router.post("/comment",status_code=status.HTTP_201_CREATED)
def create_comment(comment:sch.Comment=Body(...),db:Session=Depends(db.getDb),currentUser: models.User = Depends(oauth2.getCurrentUser)):
    # Check if the post exists
    post = db.query(models.Post).filter(models.Post.id == comment.post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Post with id {comment.post_id} not found")
    if not post.enable_comments:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"this post has comments disabled")
    # Create the comment
    new_comment =models.Comments(post_id=comment.post_id,user_id=currentUser.id,comment_content=comment.content)
    db.add(new_comment)
    # Update comments_cnt in the Post table
    if post.comments_cnt is None:
        post.comments_cnt =0
    post.comments_cnt += 1
    db.commit()
    db.refresh(new_comment)
    return {f"{currentUser.username} commented on":f"post {post.id}","comment content":comment.content}

@router.delete("/comments/delete_comment/{comment_id}",status_code=status.HTTP_200_OK)
def delete_comment(comment_id:int,db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    commentTodelete=db.query(models.Comments).filter(and_(models.Comments.id==comment_id,models.Comments.user_id==currentUser.id)).first()
    if not commentTodelete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"comment with Id {comment_id} not Found") 
    db.delete(commentTodelete)
    db.commit()
    return {"message":f"comment {comment_id} of user {currentUser.username} deleted"}

@router.patch("/comments/edit_comment/{comment_id}",status_code=status.HTTP_200_OK)
def editComment(comment_id:int,editInfo:sch.EditCommentModel=Body(...),db:Session=Depends(db.getDb),currentUser:models.User=Depends(oauth2.getCurrentUser)):
    commentToBeEdited=db.query(models.Comments).filter(and_(models.Comments.id==comment_id,models.Comments.user_id==currentUser.id)).first()
    if not commentToBeEdited:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {comment_id} not Found")
    commentToBeEdited.comment_content=editInfo.comment_content
    db.commit()
    db.refresh(commentToBeEdited)
    return {"message":f"successfully edited comment {comment_id} of user {currentUser.username}"}
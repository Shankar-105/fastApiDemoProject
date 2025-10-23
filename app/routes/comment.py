from fastapi import Body,HTTPException,status,APIRouter,Depends
from sqlalchemy.orm import Session
from app import oauth2,models,db
 
router=APIRouter(tags=['comment'])

@router.post("/comment",status_code=status.HTTP_201_CREATED)
def create_comment(content:str,post_id:int,db: Session=Depends(db.getDb), currentUser: int = Depends(oauth2.getCurrentUser)):
    # Check if the post exists
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Post with id {post_id} not found")
    if not post.enable_comments:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"this post has comments disabled")
    # Create the comment
    new_comment =models.Comments(post_id=post_id,user_id=currentUser.id,comment_content=content)
    db.add(new_comment)
    # Update comments_cnt in the Post table
    post.comments_cnt += 1
    db.commit()
    db.refresh(new_comment)
    return {f"{currentUser.username} commented on":f"post {post.id}","comment content":content}
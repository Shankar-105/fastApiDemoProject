from fastapi import HTTPException,status,Body,APIRouter,Depends,Request
from app import models,db,schemas as sch,oauth2
from sqlalchemy.orm import Session
from typing import List,Union
router=APIRouter(tags=['search'])

@router.get("/search",status_code=status.HTTP_202_ACCEPTED)
def search(request:Request,q:str=None,limit:int=10,offset:int=0,orderBy:str="created_at",db:Session=Depends(db.getDb),currenUser:models.User=Depends(oauth2.getCurrentUser)):
    print(request.query_params)
    # print(searchParams.dict())
    if q and q.startswith("#"):
        hashtag = q.lstrip("#")
        queryResult=db.query(models.Post).filter(models.Post.hashtags.ilike(f"%{hashtag}%"))
        if orderBy == "likes":
            queryResult=queryResult.order_by(models.Post.likes.desc())
        queryResult=queryResult.order_by(models.Post.created_at.asc())
        resPosts=queryResult.offset(offset).limit(limit).all()
        return resPosts
    elif q:
        resUsers=(
            db.query(models.User)
            .filter(models.User.username.ilike(f"%{q}%"))
            .offset(offset)
            .limit(limit)
            .all()
        )
        return resUsers
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Query Parameters Requrired")
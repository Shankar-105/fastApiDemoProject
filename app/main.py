# main.py
from fastapi import FastAPI,Response,status,HTTPException,Depends
from fastapi import Body
from pydantic import BaseModel
import random
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from app import models
from app.db import engine,getDb
from sqlalchemy.orm import Session


models.Base.metadata.create_all(bind=engine)

# fastapi instance
app = FastAPI()

# testing whether the db is connected or not
# testing successfull everything working fine!
'''
@app.get("/sqlAlchemyTesting")
def test(db:Session=Depends(getDb)):
    posts=db.query(models.Post).all()
    if not posts:
        return {"data":"no posts available"}
    return {"allPosts":posts}
'''
# sometimes the connection to the db may fail
# despite of passing the correct args to the params
# so we usaually try again to connect to the db
# here i have put the connection code inside a try block so that
# when the connection fails the program shouldn't crash
# and trying to connect again and again using the while loop
# until we make sure the connection is successfull
# the connection is set via sqlAlchemy so need to
# setup connnection again to psycopg
'''i=10
while i:
    try:
        conn=psycopg2.connect(host="localhost",database="fastApi",user="postgres",password="iota143",cursor_factory=RealDictCursor)
        myCursor=conn.cursor()
        print("DataBase Connection SuccessFull")
        break
    except Exception as error:
        i=i-1
        print("Connection to the Database Failed with an error : ",error,"trying again to connect")
        time.sleep(3)
'''

# Front end shouldn't send any uneccessary data 
# we need to define a schema that frontend need to follow when sending data from user
# structure or schema of the post using pydantic's BaseModel class

class Post(BaseModel):
    title:str
    content:str
    enableComments:bool=True


# basically when we don't connect to database we need
# some ds to store our posts and this list below does that
# but this is just for testing purposes becuz
# all the posts data will be lost after server stops 

# allPosts=[]


# find a post with id -> {id} while working on with list 'allPosts'
''' def findPost(id:int):
    reqPost=None
    for i in allPosts:
        if i['id'] == id:
            reqPost=i
            break
    return reqPost '''


# find the index of a post with certain id -> {id}
''' def findPostIndex(id:int):
    idx=-1
    for i in range(len(allPosts)):
        if allPosts[i]['id'] == id:
            idx=i
            break
    return idx '''


# retrives all posts using sqlAlchemy
@app.get("/posts/getAllPosts")  
def getAllPosts(db:Session=Depends(getDb)):
    allPosts=db.query(models.Post).all()
    if not allPosts:
        return {"data":"no posts available"}
    return {"allPosts":allPosts}

# gets a specific post with id -> {postId}
@app.get("/posts/getPost/{postId}")
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
@app.post("/posts/createPost",status_code=status.HTTP_201_CREATED)  
def createPosts(post:Post=Body(...),db:Session=Depends(getDb)):
    newPost=models.Post(**post.dict())
    db.add(newPost)
    db.commit()
    db.refresh(newPost)
    return {"status":"Post SuccessFully Created","postData":newPost}


# delets a specific post with the mentioned id -> {id}
@app.delete("/posts/deletePost/{postId}")
def deletePost(postId:int,db:Session=Depends(getDb)):
    
    deletedPost=db.query(models.Post).filter(models.Post.id==postId).first()
    if not deletedPost:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {postId} not Found") 
    db.delete(deletedPost)
    db.commit()
    return {"status":f"deleted post with id {postId}","deletedPostData":deletedPost}

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
@app.put("/posts/editPost/{postId}")
def editPost(postId:int,post:Post):
     myCursor.execute("update posts set title=%s,content=%s,\"enableComments\"=%s where id=%s returning *",(post.title,post.content,post.enableComments,str(postId)))
     updatedPost=myCursor.fetchone()
     conn.commit()
     if not updatedPost:
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {postId} not Found")
    # same code without using databases psycopg setup!
     ''' idx=findPostIndex(id)
     if idx==-1:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {id} not Found")
     allPosts[idx]=post.dict()
     allPosts[idx]['id']=id
     '''
     return {"status":f"updated post with id {postId}","updatedPostData":updatedPost}
     
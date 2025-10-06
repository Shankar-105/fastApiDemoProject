# main.py
from fastapi import FastAPI,Response,status,HTTPException
from fastapi import Body
from pydantic import BaseModel
import random
import psycopg2
from psycopg2.extras import RealDictCursor
import time
# fastapi instance

i=10
app = FastAPI()
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



# Front end shouldn't send any uneccessary data 
# we need to define a schema that frontend need to follow when sending data from user
# structure or schema of the post

class Post(BaseModel):
    title:str
    content:str
    enableComments:bool=True


# list to store all posts without databases!
# allPosts=[]


# find a post with id -> {id}
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


# retrives all posts
@app.get("/posts/getAllPosts")  
def getAllPosts():
    myCursor.execute("select * from posts")
    allPosts = myCursor.fetchall()
    if not allPosts:
        return {"data":"no posts"}
    return {"allPosts":allPosts}
  # same code without using database 
    ''' 
    if not allPosts:
        return {"data":"no posts"}
    return {"allPosts":allPosts}
    '''


# gets a specific post with id -> {id}
@app.get("/posts/getPost/{postId}")
def getPost(postId:int):
    myCursor.execute("select * from posts where id=%s",(str(postId)))
    reqPost=myCursor.fetchone()
    '''
    reqPost=findPost(id)
    if reqPost==None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="post not found")
        # updating status using Response class
        # response.status_code=status.HTTP_404_NOT_FOUND
        # return {"status":"post not found"} 
    '''
    if reqPost==None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with id {postId} not found")
    return {"status":"post found","data":reqPost}


# creates a new post
@app.post("/posts/createPost",status_code=status.HTTP_201_CREATED)  
def createPosts(post:Post=Body(...)):
    myCursor.execute("insert into posts (title,content,\"enableComments\") values (%s,%s,%s) returning * ",(post.title,post.content,post.enableComments))
    newPost=myCursor.fetchone()
    conn.commit()

    # same code without using database
    '''
    newPost=post.dict()
    newPost['id']=random.randrange(0,100000)
    allPosts.append(newPost)
    '''
    return {"status":"Post SuccessFully Created","postData":newPost}


# delets a specific post with the mentioned id -> {id}
@app.delete("/posts/deletePost/{postId}")
def deletePost(postId:int):
    myCursor.execute("delete from posts where id=%s returning * ",(str(postId)))
    deletedPost=myCursor.fetchone()
    conn.commit()
    if not deletedPost:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail=f"post with Id {postId} not Found") 
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
     
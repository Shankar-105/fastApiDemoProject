from fastapi import APIRouter
from app.routes import (
    auth, posts, users, me, like, connect, 
    comment, search, changepassword, feed, 
    saved, notifications, celery_tasks
)
from app.messaging import (
    chat, chat_history, share, delete_msg, 
    delete_shares, edit_msg, msg_info, 
    msg_reaction, share_reaction, media_msg, clear_chat
)

api_v1_router = APIRouter()

# Core Domain Routers
api_v1_router.include_router(posts.router)
api_v1_router.include_router(me.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(auth.router)
api_v1_router.include_router(like.router)
api_v1_router.include_router(connect.router)
api_v1_router.include_router(comment.router)
api_v1_router.include_router(search.router)
api_v1_router.include_router(changepassword.router)
api_v1_router.include_router(feed.router)
api_v1_router.include_router(saved.router)
api_v1_router.include_router(notifications.router)

# Messaging Routers
api_v1_router.include_router(chat.router)
api_v1_router.include_router(chat_history.router)
api_v1_router.include_router(share.router)
api_v1_router.include_router(delete_msg.router)
api_v1_router.include_router(delete_shares.router)
api_v1_router.include_router(edit_msg.router)
api_v1_router.include_router(msg_info.router)
api_v1_router.include_router(msg_reaction.router)
api_v1_router.include_router(share_reaction.router)
api_v1_router.include_router(media_msg.router)
api_v1_router.include_router(clear_chat.router)

# Admin/System Routers
api_v1_router.include_router(celery_tasks.router)
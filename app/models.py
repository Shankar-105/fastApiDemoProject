import enum
from app.db import Base
from sqlalchemy import Column,Integer,String,Boolean,ForeignKey,Table,DateTime,UniqueConstraint,Enum
from sqlalchemy.sql.expression import null,text
from sqlalchemy.sql.sqltypes import TIMESTAMP
from sqlalchemy.orm import relationship, backref
from datetime import datetime
from sqlalchemy.sql import func

# ── Notification type enum ──
class NotificationType(str, enum.Enum):
    like    = "like"
    comment = "comment"
    follow  = "follow"
# structure or model of the db tables

connections = Table(
    'connections', Base.metadata,
    Column('followed_id',Integer,ForeignKey('users.id',ondelete="CASCADE"),primary_key=True),
    Column('follower_id',Integer,ForeignKey('users.id',ondelete="CASCADE"),primary_key=True)
)

class SharedPostReplies(Base):
    __tablename__ = "shared_post_replies"

    reply_msg_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    shared_post_id = Column(Integer, ForeignKey("shared_posts.id", ondelete="CASCADE"), primary_key=True)

    # Relationships
    reply_message = relationship("Message", foreign_keys=[reply_msg_id],backref=backref("replies_to_share", lazy="selectin"), lazy="selectin")
    shared_post = relationship("SharedPost", foreign_keys=[shared_post_id],backref=backref("replies", lazy="selectin"), lazy="selectin")

class SharedPost(Base):
    __tablename__ = "shared_posts"

    id = Column(Integer,primary_key=True)
    post_id = Column(Integer,ForeignKey("posts.id", ondelete="CASCADE"))
    from_user_id = Column(Integer,ForeignKey("users.id", ondelete="CASCADE"))
    to_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    message = Column(String, nullable=True)  # Optional caption when sharing
    created_at = Column(DateTime, default=datetime.utcnow)
    is_read=Column(Boolean,default=False,server_default="false")
    is_deleted_for_everyone = Column(Boolean, default=False, server_default='false')
    reaction_cnt=Column(Integer,default=0,server_default="0")
    # Relationships
    post = relationship("Post",back_populates="shared_posts", lazy="selectin")
    from_user = relationship("User", foreign_keys=[from_user_id],back_populates="sent_posts", lazy="selectin")
    to_user = relationship("User", foreign_keys=[to_user_id],back_populates="received_posts", lazy="selectin")
    reactions = relationship(
        "SharedPostReaction",
        backref=backref("shared_post", lazy="selectin"),
        cascade="all, delete-orphan",
        lazy="selectin"
    )

# models.py
class DeletedMessage(Base):
    __tablename__ = "deleted_messages"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    deleted_at = Column(DateTime, default=datetime.utcnow)
    # Unique: one user can't delete same msg twice
    __table_args__ = (UniqueConstraint('user_id', 'message_id',name='uq_user_deleted_msg'),)

# models.py
class DeletedSharedPost(Base):
    __tablename__ = "deleted_shared_posts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    shared_post_id = Column(Integer, ForeignKey("shared_posts.id", ondelete="CASCADE"))
    deleted_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    # which user has deleted
    user = relationship("User", lazy="selectin")
    # which post has been deleted
    shared_post = relationship("SharedPost", lazy="selectin")

class OTP(Base):
    __tablename__ = "otps"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)  # Only 1 per email
    otp = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())

class Votes(Base):
    __tablename__='votes'
    post_id=Column(Integer,ForeignKey("posts.id",ondelete="CASCADE"),primary_key=True,nullable=False)
    user_id=Column(Integer,ForeignKey("users.id",ondelete="CASCADE"),primary_key=True,nullable=False)
    action=Column(Boolean,nullable=False)

class CommentVotes(Base):
    __tablename__='comment_votes'
    comment_id=Column(Integer,ForeignKey("comments.id",ondelete="CASCADE"),primary_key=True,nullable=False)
    user_id=Column(Integer,ForeignKey("users.id",ondelete="CASCADE"),primary_key=True,nullable=False)
    like=Column(Boolean,nullable=False)

class Comments(Base):
    __tablename__='comments'
    id = Column(Integer,primary_key=True)
    post_id=Column(Integer,ForeignKey("posts.id",ondelete="CASCADE"),nullable=False)
    user_id=Column(Integer,ForeignKey("users.id",ondelete="CASCADE"),nullable=False)
    comment_content=Column(String,nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    likes=Column(Integer,default=0,server_default=text("0"),nullable=False)
class Post(Base):
    __tablename__='posts'
    id=Column(Integer,primary_key=True,nullable=False)
    media_path = Column(String, nullable=True)  # NEW: stores "posts_media/funny_cat.mp4"
    media_type = Column(String, nullable=True)  # "image" or "video"
    title=Column(String,nullable=False)
    content=Column(String,nullable=False)
    enable_comments=Column(Boolean,server_default="TRUE",nullable=False)
    created_at=Column(TIMESTAMP(timezone=True),nullable=False,server_default=text('now()'))
    user_id=Column(Integer,ForeignKey("users.id",ondelete="CASCADE"),nullable=False)
    likes=Column(Integer,default=0,server_default="0",nullable=False)
    dis_likes=Column(Integer,default=0,server_default="0",nullable=False)
    views=Column(Integer,default=0,server_default=text("0"))
    comments_cnt=Column(Integer,default=0,server_default=text("0"))
    hashtags=Column(String,nullable=True)

    shared_posts = relationship("SharedPost",back_populates="post", lazy="selectin")


class SavedPost(Base):
    __tablename__ = "saved_posts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", backref=backref("saved_posts", lazy="selectin"), lazy="selectin")
    post = relationship("Post", lazy="selectin")

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_saved_user_post"),)

class PostView(Base):
    __tablename__ = "post_views"
    post_id = Column(Integer, ForeignKey("posts.id",ondelete="CASCADE"),primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id",ondelete="CASCADE"),primary_key=True)
    viewed_at = Column(DateTime,default=datetime.utcnow)
class User(Base):
        __tablename__='users'
        id=Column(Integer,primary_key=True,nullable=False)
        username=Column(String,nullable=False,unique=True)
        password=Column(String,nullable=False)
        nickname=Column(String,nullable=False)
        bio=Column(String,nullable=True)
        email=Column(String,nullable=True)
        email_verified=Column(Boolean, default=False, server_default="false", nullable=False)
        profile_picture=Column(String,nullable=True)
        created_at=Column(TIMESTAMP(timezone=True),nullable=False,server_default=text('now()'))
        last_seen_at=Column(DateTime(timezone=True), nullable=True)
        followers_cnt=Column(Integer,default=0,server_default="0",nullable=False)
        following_cnt=Column(Integer,default=0,server_default="0",nullable=False)
        version_id=Column(Integer,nullable=False,default=1,server_default=text("1"))
        # added relationship between the posts table and the users table so that
        # when you actually need all the posts of a user there's no need from now on 
        # to go check the posts table and query it for Posts.user_id==currentUser.id
        # inorder to get all posts of a certain user but rather by declaring this relationship
        # you just do the currentUser.posts and sqlAlchemy internally does the joins
        # and retrievs you all of the users posts!
        posts=relationship('Post',backref=backref('user', lazy='selectin'), lazy='selectin')
        # a many to many relationship
        followers = relationship(
        'User',
        secondary=connections,  # The middle table
        primaryjoin=(connections.c.followed_id == id),  # "I am the follwed guyy"
        secondaryjoin=(connections.c.follower_id == id),  # "They are my followers"
        backref=backref('following', lazy='selectin'),  # reverse property
        lazy='selectin'
    )
        voted_posts = relationship(
        'Post',
        secondary='votes',  # The middle table
        primaryjoin=(Votes.user_id == id),  # User.id links to Votes.user_id
        secondaryjoin=(Votes.post_id == Post.id),  # Votes.post_id links to Post.id
        backref=backref('voters', lazy='selectin'),  # allows posts to access users who voted on them
        lazy='selectin'
    )
        total_comments=relationship('Comments',backref=backref('user', lazy='selectin'), lazy='selectin')
        sent_posts = relationship("SharedPost", foreign_keys=[SharedPost.from_user_id],back_populates="from_user", lazy="selectin")
        received_posts = relationship("SharedPost", foreign_keys=[SharedPost.to_user_id],back_populates="to_user", lazy="selectin")
        shared_post_reactions = relationship("SharedPostReaction", back_populates="user", lazy="selectin")

        __mapper_args__ = {"version_id_col": version_id}
class MessageReplies(Base):
    __tablename__ = "message_replies"
    reply_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    original_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    # Relationships (optional, for easier querying)
    reply_msg = relationship("Message", foreign_keys=[reply_id], lazy="selectin")
    original_msg = relationship("Message", foreign_keys=[original_id], lazy="selectin")
class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    media_url = Column(String,default=False,server_default="false")
    media_type = Column(String,default=False,server_default="false")
    content = Column(String, nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True),server_default=func.now())
    is_read = Column(Boolean,default=False)
    is_deleted_for_everyone = Column(Boolean, default=False, server_default='false')
    is_edited=Column(Boolean,default=False,server_default="false")
    edited_at=Column(DateTime,nullable=True)
    read_at = Column(DateTime(timezone=True),nullable=True)
    reaction_cnt=Column(Integer,default=0,server_default="0")
    is_reply_msg = Column(Boolean,default=False)
    is_reply_to_share = Column(Boolean,default=False,server_default="false")
    # optional relationships for later maybe useful
    # when you do a Obj.sender where Obj is the object of class Message
    # it returns which user has sent that message and the same for Obj.recceiver
    # and also when you add a 'backpopulates' or 'backref' with a somename and on
    # User side you do that Object.thatBackrefName on a User object then it returns  
    # a list of all the messages that particular user has sent or received
    sender = relationship("User", foreign_keys=[sender_id], lazy="selectin")
    receiver = relationship("User", foreign_keys=[receiver_id], lazy="selectin")
    # get the hecking list of all reactions on this message
    reactions = relationship(
        "MessageReaction",
        backref=backref("message", lazy="selectin"),
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    # get the list of all reacted users on this message
    reacted_users = relationship(
    "User",
    secondary="message_reactions",
    primaryjoin="Message.id == message_reactions.c.message_id",
    secondaryjoin="User.id == message_reactions.c.user_id",
    viewonly=True
    )
    # if the Message obj is a reply message
    # thrn we need to know the original message
    # so that we can simply display in chat_history isntead of complex joins
    replied_by = relationship(
        "MessageReplies",
        foreign_keys=[MessageReplies.original_id],
        back_populates="original_msg",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    # One message can reply to one
    replies_to = relationship(
        "MessageReplies",
        foreign_keys=[MessageReplies.reply_id],
        back_populates="reply_msg",
        uselist=False,  # important: only one parent
        lazy="selectin"
    )
    # Add this inside class Message (in models.py)

    # Direct link from a reply-message → the SharedPost it replies to
    reply_to_shared_post = relationship(
        "SharedPost",
        secondary="shared_post_replies",
        primaryjoin="Message.id == SharedPostReplies.reply_msg_id",
        secondaryjoin="SharedPostReplies.shared_post_id == SharedPost.id",
        uselist=False,           # One message replies to exactly one shared post
        viewonly=True
    )
# separate message reaction table to track who reacted to teh msg
class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(Integer,primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reaction = Column(String,nullable=False)  # ex: "❤️", "😂"
    # get the user reacted
    user = relationship("User", backref=backref("message_reactions", lazy="selectin"), lazy="selectin")
    __table_args__ = (UniqueConstraint('message_id', 'user_id', name='unique_user_reaction'),)

class SharedPostReaction(Base):
    __tablename__ = "shared_post_reactions"

    id = Column(Integer, primary_key=True)
    shared_post_id = Column(Integer, ForeignKey("shared_posts.id",ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reaction = Column(String,nullable=False)

    # Relationships
    user = relationship("User", back_populates="shared_post_reactions", lazy="selectin")
    __table_args__ = (UniqueConstraint('shared_post_id', 'user_id', name='unique_shared_post_reaction'),)


class Notification(Base):
    """
    Stores every notification a user receives.

    owner_id  — the user who RECEIVES this notification
    actor_id  — the user who TRIGGERED it (liked, commented, followed)
    type      — one of: 'like', 'comment', 'follow'
    entity_id — the post/comment being liked or commented on
                NULL for follow notifications (no specific content entity)
    entity_type — 'post' or 'comment' so the client knows what to navigate to
                  NULL for follow notifications
    text      — pre-built human-readable string: "shank liked your post"
    is_read   — False until the user explicitly reads it (client calls PATCH)
    """
    __tablename__ = "notifications"

    id          = Column(Integer, primary_key=True)
    owner_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type        = Column(Enum(NotificationType), nullable=False)
    entity_id   = Column(Integer, nullable=True)   # post_id or comment_id; NULL for follows
    entity_type = Column(String,  nullable=True)   # "post" | "comment" | NULL
    text        = Column(String,  nullable=False)
    is_read     = Column(Boolean, default=False, server_default="false", nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    # who receives this notification
    owner = relationship("User", foreign_keys=[owner_id], backref=backref("notifications", lazy="selectin"), lazy="selectin")
    # who triggered this notification (we need their username + profile pic for the client)
    actor = relationship("User", foreign_keys=[actor_id], lazy="selectin")


class RefreshToken(Base):
    """
    Stores every refresh token ever issued.

    token      — opaque random string (secrets.token_urlsafe), NOT a JWT
    family_id  — UUID that groups all tokens born from a single login session.
                 When reuse is detected, all tokens in the family are revoked.
    revoked    — set to True when the token is rotated or explicitly revoked
    """
    __tablename__ = "refresh_tokens"

    id         = Column(Integer, primary_key=True)
    token      = Column(String, unique=True, index=True, nullable=False)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    family_id  = Column(String, nullable=False, index=True)
    revoked    = Column(Boolean, default=False, server_default="false", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", lazy="selectin")
from fastapi import APIRouter,Depends
from app import schemas, models, oauth2, db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.utils.socket_manager import manager
from app.services import redis_service
from typing import List
import json
import structlog


logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/messaging",
    tags=['Messaging']
)

# same as the message_reaction but here the shares are
# stored in the SharedPosts table so we query that insted of
# the messages table
@router.get("/shares/{shared_id}/reactions", response_model=List[schemas.ReactedUsers])
async def get_shared_post_reactions(
    shared_id: int,
    db: AsyncSession = Depends(db.getDb),
    currentUser: models.User = Depends(oauth2.getCurrentUser)
):
    """Return all reactions on a shared post with user details.

    Requires the requesting user to be either the sender or receiver of the
    shared post. Returns a list of {user_id, username, profile_pic, reaction}.
    Mirrors msg_reaction.msg_reactions but queries SharedPostReaction.
    Called from the shared post reactions popup.
    """
    logger.debug("fetching_shared_post_reactions", shared_id=shared_id, user_id=currentUser.id)
    result = await db.execute(
        select(models.SharedPost).where(models.SharedPost.id == shared_id)
    )
    shared = result.scalars().first()
    if not shared:
        logger.warning("shared_post_reactions_not_found", shared_id=shared_id, user_id=currentUser.id)
        return
    if shared.from_user_id != currentUser.id and shared.to_user_id != currentUser.id:
        logger.warning("shared_post_reactions_unauthorized", shared_id=shared_id, user_id=currentUser.id)
        return

    reactions_result = await db.execute(
        select(models.SharedPostReaction)
        .options(selectinload(models.SharedPostReaction.user))
        .where(models.SharedPostReaction.shared_post_id == shared_id)
    )
    reactions = reactions_result.scalars().all()
    return [
        {
            "user_id": r.user.id,
            "username": r.user.username,
            "profile_pic": r.user.profile_picture,
            "reaction": r.reaction
        }
        for r in reactions
    ]

async def react_to_shared_post(
    reaction: schemas.ReactionPayload,
    user_id: int,
    db: AsyncSession
):
    """Add, change, or remove a reaction on a shared post (toggle logic).

    Only the from_user and to_user of the shared post are eligible to react.
    Toggle semantics mirror msg_reaction.react: create / toggle-off / update.
    Publishes a "reaction_update" event to Redis pub/sub with the updated
    reaction count, falling back to local WebSocket delivery. Called from the
    WebSocket dispatch loop when type == "shared_post_reaction".
    """
    logger.info("handling_shared_post_reaction", shared_id=reaction.message_id, user_id=user_id, reaction=reaction.reaction)
    # message_id is nothing but share_id
    result = await db.execute(
        select(models.SharedPost).where(models.SharedPost.id == reaction.message_id)
    )
    shared = result.scalars().first()
    if not shared:
        logger.warning("shared_post_reaction_not_found", shared_id=reaction.message_id, user_id=user_id)
        return {"status": "not found"}

    eligible = [shared.from_user_id, shared.to_user_id]

    if user_id not in eligible:
        logger.warning("shared_post_reaction_unauthorized", shared_id=reaction.message_id, user_id=user_id)
        return {"status": "unauthorized"}

    existing_result = await db.execute(
        select(models.SharedPostReaction).where(
            models.SharedPostReaction.shared_post_id == reaction.message_id,
            models.SharedPostReaction.user_id == user_id
        )
    )
    existing = existing_result.scalars().first()

    isNewRecord = False
    if not existing:
        isNewRecord=True
        # New reaction
        new_reaction = models.SharedPostReaction(
            shared_post_id=reaction.message_id,
            user_id=user_id,
            reaction=reaction.reaction
        )
        db.add(new_reaction)
    elif existing.reaction == reaction.reaction:
        isNewRecord=False
        # Toggle off
        await db.delete(existing)
    else:
        isNewRecord=True
        # Change reaction
        existing.reaction = reaction.reaction
    # commit any change
    await db.commit()
    # No refresh needed - expire_on_commit=False keeps object attributes
    
    payload = {
        "type": "reaction_update",
        "data": {
            "message_id":shared.id,
            "reaction": reaction.reaction if isNewRecord else None,
            "reaction_count":shared.reaction_cnt,
            "reacted_by": user_id
        },
        "receiver_id": shared.to_user_id
    }

    sender_payload = dict(payload)
    sender_payload["receiver_id"] = shared.from_user_id
    try:
        await redis_service.redis_client.publish("chat:messages", json.dumps(sender_payload))
        await redis_service.redis_client.publish("chat:messages", json.dumps(payload))
        logger.info("Share reaction published to Redis", extra={"extra_info": {"shared_id": shared.id, "user_id": user_id}})
    except Exception as e:
        logger.warning("Failed to publish share reaction to Redis", extra={"extra_info": {"shared_id": shared.id, "user_id": user_id, "error": str(e)}})
        # Fallback to local sends
        try:
            await manager.send_personal_message(sender_payload, shared.from_user_id)
        except Exception:
            pass
        try:
            await manager.send_json_to_user(payload, shared.to_user_id)
        except Exception:
            manager.disconnect(shared.to_user_id)

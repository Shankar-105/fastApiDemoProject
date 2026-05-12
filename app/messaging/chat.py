from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from app import schemas, oauth2,db
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.socket_manager import manager
from app.messaging import delete_msg,delete_shares,dm,edit_msg,load_missed_msgs,msg_reaction,share_reaction,reply_msg,reply_to_share,media_msg,read_receipt
import json
import asyncio
router = APIRouter(
    prefix="/messaging",
    tags=["Messaging"]
)

PRESENCE_HEARTBEAT_TIMEOUT_SECONDS = 45

# ping_task=None

@router.websocket("/ws/{user_id}")
async def chat(
    websocket: WebSocket,
    user_id: int,
    token: str = Query(None, description="Search query params"),
    db: AsyncSession = Depends(db.getDb)
):
    heartbeat_event = asyncio.Event()
    heartbeat_task: asyncio.Task | None = None

    if not token:
        await websocket.close(code=1008)
        return
    try:
        current_user = await oauth2.getCurrentUser(token, db)
        if current_user.id != user_id:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect(user_id, websocket)
    heartbeat_event.set()  # initial connect counts as alive
    heartbeat_task = asyncio.create_task(
        manager.run_presence_watchdog(websocket, heartbeat_event, PRESENCE_HEARTBEAT_TIMEOUT_SECONDS)
    )
    await manager.broadcast_presence_update(db, user_id, online=True, last_seen_at=None)

    missed_content = await load_missed_msgs.load_missed_content(current_user.id, db)
    if missed_content:
        missed_content.reverse()
    for item in missed_content:
        try:
            await websocket.send_json(item)
        except Exception:
            print("WebSocket broken during missed content delivery")
            break

    def _safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    try:
        while True:
            data = await websocket.receive_text()
            data = data.replace('\r', '')
            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = message_data.get("type")

            if message_data.get("type") == "delete_for_everyone":
                msg_id = _safe_int(message_data.get("message_id"))
                recv_id = _safe_int(message_data.get("receiver_id"))
                if msg_id is None or recv_id is None:
                    continue
                await delete_msg.delete_for_everyone(
                    db=db,
                    message_id=msg_id,
                    sender_id=current_user.id,
                    receiver_id=recv_id
                )

            elif msg_type == "reaction":
                reacted_by = current_user.id
                reaction_emoji = message_data.get("reaction")
                msg_id = _safe_int(message_data.get("message_id"))
                if not reaction_emoji or msg_id is None:
                    continue
                reactionPayLoad = schemas.ReactionPayload(
                    message_id=msg_id,
                    reaction=reaction_emoji
                )
                await msg_reaction.react(reactionPayLoad, reacted_by, db)

            elif msg_type == "shared_post_reaction":
                reacted_by = current_user.id
                reaction_emoji = message_data.get("reaction")
                shared_id = _safe_int(message_data.get("shared_post_id"))
                if not reaction_emoji or shared_id is None:
                    continue

                reaction_payload = schemas.ReactionPayload(
                    message_id=shared_id,
                    reaction=reaction_emoji
                )
                await share_reaction.react_to_shared_post(reaction_payload, reacted_by, db)

            elif msg_type == "edit_message":
                msg_id = _safe_int(message_data.get("msg_id"))
                recv_id = _safe_int(message_data.get("receiver_id"))
                new_content = (message_data.get("new_content") or "").strip()
                if msg_id is None or recv_id is None or not new_content:
                    continue
                await edit_msg.edit_message(
                    db=db,
                    message_id=msg_id,
                    new_content=new_content,
                    sender_id=current_user.id,
                    recv_id=recv_id
                )

            elif msg_type == "delete_share_for_everyone":
                share_id = _safe_int(message_data.get("message_id"))
                recv_id = _safe_int(message_data.get("receiver_id"))
                if share_id is None or recv_id is None:
                    continue
                await delete_shares.delete_share_for_everyone(
                    db=db,
                    share_id=share_id,
                    sender_id=current_user.id,
                    receiver_id=recv_id
                )

            elif msg_type == "typing":
                is_typing = bool(message_data.get("is_typing"))
                receiver_id = _safe_int(message_data.get("receiver_id"))
                if receiver_id is None:
                    continue
                await manager.typing_status(
                    message_type=msg_type,
                    receiver_id=receiver_id,
                    typing_status=is_typing,
                )

            elif msg_type == "presence_heartbeat":
                await manager.ack_presence_heartbeat(user_id, heartbeat_event)

            elif msg_type == "read_receipt":
                await read_receipt.mark_as_read(message_data, current_user.id, db)

            elif msg_type == "reply_message":
                receiver_id = _safe_int(message_data.get("to"))
                reply_msg_id = _safe_int(message_data.get("reply_msg_id"))
                content = message_data.get("content")
                media_url = message_data.get("media_url")
                media_type = message_data.get("media_type")
                if receiver_id is None or reply_msg_id is None:
                    continue
                payload = schemas.ReplyMessageSchema(
                    to=receiver_id,
                    reply_msg_id=reply_msg_id,
                    content=content,
                    media_type=media_type,
                    media_url=media_url
                )
                await reply_msg.reply_msg(payload, current_user.id, db)

            elif msg_type == "reply_to_share":
                receiver_id = _safe_int(message_data.get("to"))
                shared_post_id = _safe_int(message_data.get("reply_share_id"))
                content = message_data.get("content")
                media_url = message_data.get("media_url")
                media_type = message_data.get("media_type")
                if receiver_id is None or shared_post_id is None:
                    continue
                payload = schemas.ReplyToShareSchema(
                    to=receiver_id,
                    shared_post_id=shared_post_id,
                    content=content,
                    media_type=media_type,
                    media_url=media_url
                )
                await reply_to_share.reply_share(payload, current_user.id, db)

            else:
                receiver_id = _safe_int(message_data.get("to"))
                content = message_data.get("content")
                media_url = message_data.get("media_url")
                media_type = message_data.get("media_type")
                if receiver_id is None:
                    continue
                payload = schemas.MessageSchema(
                    to=receiver_id,
                    content=content,
                    media_type=media_type,
                    media_url=media_url
                )
                await dm.messageUser(payload, current_user.id, db)

    except WebSocketDisconnect:
        seen_at = await manager.mark_last_seen(db, user_id)
        manager.disconnect(user_id, client_initiated=True, last_seen_at=seen_at)
        await manager.broadcast_presence_update(db, user_id, online=False, last_seen_at=seen_at)
    except Exception as e:
        print(e)
        seen_at = await manager.mark_last_seen(db, user_id)
        manager.disconnect(user_id, client_initiated=False, last_seen_at=seen_at)
        await manager.broadcast_presence_update(db, user_id, online=False, last_seen_at=seen_at)
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()

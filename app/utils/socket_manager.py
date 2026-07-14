# connection_manager.py
from fastapi import WebSocket
from typing import Dict
import json
import asyncio
from datetime import datetime, timezone
from fastapi.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, union
from app import models

class ConnectionManager:
    """Manages active WebSocket connections with presence tracking and peer awareness.

    Maintains one active WebSocket per user (older connections are displaced).
    Provides presence (online/last_seen) data, injects peer presence into
    messages, and supports heartbeat-based staleness detection. Used by
    the WebSocket chat/notification endpoints.

    The single module-level ``manager`` instance is shared across the app.
    """

    def __init__(self):
        """Initialize empty connection and last-seen maps."""
        self.active_connections: Dict[int, WebSocket] = {}
        self.last_seen_map: Dict[int, datetime] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        """Accept and register a WebSocket for the given user.

        If the user already has an active socket, the old one is
        forcibly disconnected (server-initiated close) to guarantee
        at most one concurrent connection per user.
        """
        if user_id in self.active_connections:
            self.disconnect(user_id, client_initiated=False)

        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int, client_initiated: bool = True, last_seen_at: datetime | None = None):
        """Remove a user's WebSocket and optionally cache their last_seen timestamp.

        When ``client_initiated`` is False (server-forced), tries to
        close the old socket gracefully via asyncio task.
        """
        ws = self.active_connections.pop(user_id, None)
        if last_seen_at is not None:
            self.last_seen_map[user_id] = last_seen_at
        if ws and not client_initiated and ws.application_state == WebSocketState.CONNECTED:
            try:
                asyncio.create_task(ws.close(code=1000, reason="Server initiated disconnect"))
            except Exception:
                pass

    def is_online(self, user_id: int) -> bool:
        """Check if a user currently has an active WebSocket connection."""
        return bool(ws and ws.application_state == WebSocketState.CONNECTED)

    def get_last_seen(self, user_id: int) -> datetime | None:
        """Return the cached last_seen timestamp for a user, or None if unknown.

        This is an in-memory fast path; the durable value lives in users.last_seen_at.
        """

    def _iso_or_none(self, dt: datetime | None) -> str | None:
        """Convert a datetime to ISO-8601 string, returning None for None input.

        Naive datetimes are assumed to be UTC and are timezone-aware'd.
        """
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    def get_presence_payload(self, user_id: int) -> dict:
        """Build a presence status dict for a user (online + last_seen_at).

        Returns {'user_id': ..., 'online': bool, 'last_seen_at': str | None}.
        Injected into messages by _inject_peer_presence() for real-time UX.
        """
        last_seen = None if online else self.get_last_seen(user_id)
        return {
            "user_id": user_id,
            "online": online,
            "last_seen_at": self._iso_or_none(last_seen),
        }

    async def mark_last_seen(self, db: AsyncSession, user_id: int) -> datetime:
        """Persist the current UTC timestamp as the user's last_seen_at in the DB.

        Used when a user disconnects or sends a presence heartbeat.
        Returns the seen_at datetime for further use (e.g. broadcast).
        """
        seen_at = datetime.now(timezone.utc)
        try:
            await db.execute(
                update(models.User)
                .where(models.User.id == user_id)
                .values(last_seen_at=seen_at)
            )
            await db.commit()
        except Exception:
            await db.rollback()
        return seen_at

    async def _peer_ids(self, db: AsyncSession, user_id: int) -> set[int]:
        """Query the database for all user IDs that have chatted or shared posts with this user.

        Union of sender/receiver pairs from messages and shared_posts.
        Used by broadcast_presence_update() to notify only relevant peers.
        """
        peer_union = union(
            select(models.Message.receiver_id.label("peer_id")).where(models.Message.sender_id == user_id),
            select(models.Message.sender_id.label("peer_id")).where(models.Message.receiver_id == user_id),
            select(models.SharedPost.to_user_id.label("peer_id")).where(models.SharedPost.from_user_id == user_id),
            select(models.SharedPost.from_user_id.label("peer_id")).where(models.SharedPost.to_user_id == user_id),
        ).subquery()

        result = await db.execute(
            select(peer_union.c.peer_id).where(
                peer_union.c.peer_id.is_not(None),
                peer_union.c.peer_id != user_id,
            )
        )
        return set(result.scalars().all())

    async def broadcast_presence_update(
        self,
        db: AsyncSession,
        user_id: int,
        online: bool,
        last_seen_at: datetime | None = None,
    ) -> None:
        """Notify all peers of a user that their presence status changed.

        Sends a 'presence_update' message to every user who has ever
        exchanged messages or shared posts with this user.
        """
        payload = {
            "type": "presence_update",
            "presence": {
                "user_id": user_id,
                "online": online,
                "last_seen_at": self._iso_or_none(last_seen_at),
            },
        }
        peers = await self._peer_ids(db, user_id)
        for peer_id in peers:
            await self.send_personal_message(payload, peer_id)

    async def run_presence_watchdog(
        self,
        websocket: WebSocket,
        heartbeat_event: asyncio.Event,
        timeout_seconds: int,
    ) -> None:
        """Coroutine: close a WebSocket if no heartbeat is received within the timeout.

        Runs as a concurrent task per connection. Blocking on the event
        with asyncio.wait_for — if the event isn't set within the window,
        the socket is closed with code 1001 (heartbeat timeout).
        """
        try:
            while True:
                await asyncio.wait_for(heartbeat_event.wait(), timeout=timeout_seconds)
                heartbeat_event.clear()
        except asyncio.TimeoutError:
            try:
                await websocket.close(code=1001, reason="Presence heartbeat timeout")
            except Exception:
                pass
        except asyncio.CancelledError:
            return

    async def ack_presence_heartbeat(self, user_id: int, heartbeat_event: asyncio.Event) -> None:
        """Acknowledge a presence heartbeat by setting the event and sending a response.

        Signals the watchdog that the client is still alive, and replies
        with a 'presence_ack' message to confirm receipt.
        """
        heartbeat_event.set()
        await self.send_personal_message({"type": "presence_ack"}, user_id)

    def _inject_peer_presence(self, message: dict, target_user_id: int) -> dict:
        """Enrich a message with the sender's or receiver's presence info.

        Determines the peer (the user on the other end of the conversation)
        and attaches their online/last_seen status so the client can show
        real-time presence without an extra API call.
        """
        if not isinstance(message, dict):
            return message

        payload = dict(message)
        sender_id = payload.get("sender_id")
        receiver_id = payload.get("receiver_id")
        peer_id = None

        if isinstance(sender_id, int) and isinstance(receiver_id, int):
            if target_user_id == receiver_id:
                peer_id = sender_id
            elif target_user_id == sender_id:
                peer_id = receiver_id
        elif isinstance(payload.get("actor_id"), int):
            peer_id = payload.get("actor_id")

        if peer_id is not None:
            payload["peer_presence"] = self.get_presence_payload(peer_id)

        return payload

    async def send_personal_message(self, message: dict, user_id: int):
        """Send a JSON message to a specific user's WebSocket (via send_json).

        Injects peer presence before sending. If the send fails (disconnected
        socket), the user is removed from active connections.
        """
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                payload = self._inject_peer_presence(message, user_id)
                await ws.send_json(payload)
            except Exception:
                self.disconnect(user_id, client_initiated=False)
        
    async def send_json_to_user(self, message: dict, user_id: int):
        """Send a JSON-serialized string message to a specific user's WebSocket.

        Similar to send_personal_message but uses send_text with manual
        json.dumps. Injects peer presence. Falls back to disconnect on error.
        """
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                payload = self._inject_peer_presence(message, user_id)
                await ws.send_text(json.dumps(payload))
            except Exception:
                self.disconnect(user_id, client_initiated=False)

    async def send_to_user(self, message: str, receiver_id: int):
        """Send a raw text message to a specific user's WebSocket.

        Lower-level than send_personal_message — no peer presence injection.
        Used for pre-serialized payloads. Disconnects on send failure.
        """
        ws = self.active_connections.get(receiver_id)
        if ws:
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(receiver_id, client_initiated=False)
                    
    async def typing_status(self, message_type: str, receiver_id: int, typing_status: bool):
        """Send a typing indicator to the specified receiver via WebSocket.

        The payload contains the message_type and a boolean typing_status.
        Delegates to send_personal_message for delivery.
        """
        message = {
            "type": message_type,
            "typing_status": typing_status
        }
        return await self.send_personal_message(message=message, user_id=receiver_id)

# single manager instance
manager = ConnectionManager()

# connection_manager.py
from fastapi import WebSocket
from typing import Dict
import json
import asyncio
from datetime import datetime, timezone
from fastapi.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app import models

class ConnectionManager:
    def __init__(self):
        # user_id -> active websocket
        self.active_connections: Dict[int, WebSocket] = {}
        # last seen cache (in-memory fast path; durable value is also persisted in DB)
        self.last_seen_map: Dict[int, datetime] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        # Ensure a single active socket per user to avoid duplicate delivery.
        if user_id in self.active_connections:
            self.disconnect(user_id, client_initiated=False)

        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int, client_initiated: bool = True, last_seen_at: datetime | None = None):
        ws = self.active_connections.pop(user_id, None)
        if last_seen_at is not None:
            self.last_seen_map[user_id] = last_seen_at
        if ws and not client_initiated and ws.application_state == WebSocketState.CONNECTED:
            try:
                asyncio.create_task(ws.close(code=1000, reason="Server initiated disconnect"))
            except Exception:
                pass

    def is_online(self, user_id: int) -> bool:
        ws = self.active_connections.get(user_id)
        return bool(ws and ws.application_state == WebSocketState.CONNECTED)

    def get_last_seen(self, user_id: int) -> datetime | None:
        return self.last_seen_map.get(user_id)

    def _iso_or_none(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    def get_presence_payload(self, user_id: int) -> dict:
        online = self.is_online(user_id)
        last_seen = None if online else self.get_last_seen(user_id)
        return {
            "user_id": user_id,
            "online": online,
            "last_seen_at": self._iso_or_none(last_seen),
        }

    async def mark_last_seen(self, db: AsyncSession, user_id: int) -> datetime:
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
        peers: set[int] = set()

        sent_to = await db.execute(
            select(models.Message.receiver_id).where(models.Message.sender_id == user_id)
        )
        peers.update(row[0] for row in sent_to.all())

        received_from = await db.execute(
            select(models.Message.sender_id).where(models.Message.receiver_id == user_id)
        )
        peers.update(row[0] for row in received_from.all())

        shared_to = await db.execute(
            select(models.SharedPost.to_user_id).where(models.SharedPost.from_user_id == user_id)
        )
        peers.update(row[0] for row in shared_to.all())

        shared_from = await db.execute(
            select(models.SharedPost.from_user_id).where(models.SharedPost.to_user_id == user_id)
        )
        peers.update(row[0] for row in shared_from.all())

        peers.discard(user_id)
        return peers

    async def broadcast_presence_update(
        self,
        db: AsyncSession,
        user_id: int,
        online: bool,
        last_seen_at: datetime | None = None,
    ) -> None:
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
        """Close stale sockets when heartbeats stop arriving."""
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
        heartbeat_event.set()
        await self.send_personal_message({"type": "presence_ack"}, user_id)

    def _inject_peer_presence(self, message: dict, target_user_id: int) -> dict:
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
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                payload = self._inject_peer_presence(message, user_id)
                await ws.send_json(payload)
            except Exception:
                self.disconnect(user_id, client_initiated=False)
        
    async def send_json_to_user(self, message: dict, user_id: int):
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                payload = self._inject_peer_presence(message, user_id)
                await ws.send_text(json.dumps(payload))
            except Exception:
                self.disconnect(user_id, client_initiated=False)

    async def send_to_user(self, message: str, receiver_id: int):
        ws = self.active_connections.get(receiver_id)
        if ws:
            try:
                await ws.send_text(message)
            except Exception:
                self.disconnect(receiver_id, client_initiated=False)
                    
    async def typing_status(self, message_type: str, receiver_id: int, typing_status: bool):
            message={
            "type":message_type,
            "typing_status":typing_status
            }
            return await self.send_personal_message(message=message,user_id=receiver_id)
# single manager instance
manager = ConnectionManager()
# connection_manager.py
from fastapi import WebSocket
from typing import Dict
import json
import asyncio
from datetime import datetime, timezone
from fastapi.websockets import WebSocketState

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
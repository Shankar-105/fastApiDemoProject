# connection_manager.py
from fastapi import WebSocket
from typing import Dict
import json
import asyncio
from datetime import datetime
from fastapi.websockets import WebSocketState

class ConnectionManager:
    def __init__(self):
        # store dict per user: {user_id: {"ws": WebSocket, "pong_event": Event, "last_pong": datetime}}
        self.active_connections: Dict[int, Dict] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        # Ensure a single active socket per user to avoid duplicate delivery.
        if user_id in self.active_connections:
            self.disconnect(user_id, client_initiated=False)

        await websocket.accept()
        self.active_connections[user_id] = {
            "ws": websocket,
            "pong_event": asyncio.Event(),
            "last_pong": datetime.utcnow()
        }
        # Run heartbeat task per connection.
        self.active_connections[user_id]["ping_task"] = asyncio.create_task(
            self._per_connection_pinger(user_id)
        )

    def disconnect(self, user_id: int, client_initiated: bool = True):
        conn = self.active_connections.get(user_id)
        if conn:
            task = conn.get("ping_task")
            if task:
                task.cancel()
                if not client_initiated:
                    ws = conn.get("ws")
                    if ws and ws.application_state == WebSocketState.CONNECTED:
                        try:
                            asyncio.create_task(ws.close(code=1000, reason="Server initiated disconnect"))
                        except Exception:
                            pass
            del self.active_connections[user_id]

    async def send_personal_message(self, message: dict, user_id: int):
        conn = self.active_connections.get(user_id)
        if conn:
            try:
                await conn["ws"].send_json(message)
            except Exception:
                self.disconnect(user_id, client_initiated=False)
        
    async def send_json_to_user(self, message: dict, user_id: int):
        conn = self.active_connections.get(user_id)
        if conn:
            try:
                await conn["ws"].send_text(json.dumps(message))
            except Exception:
                self.disconnect(user_id, client_initiated=False)

    async def send_to_user(self, message: str, receiver_id: int):
        conn = self.active_connections.get(receiver_id)
        if conn:
            try:
                await conn["ws"].send_text(message)
            except Exception:
                self.disconnect(receiver_id, client_initiated=False)

    def mark_pong(self, user_id: int):
        """Called by main reader when a pong is received for user_id."""
        conn = self.active_connections.get(user_id)
        if conn and conn["ws"].application_state == WebSocketState.CONNECTED:
            conn["pong_event"].set()
            conn["last_pong"] = datetime.utcnow()
            conn["pong_event"] = asyncio.Event()

    async def send_ping(self, user_id: int) -> bool:
        """Send ping to the given user's websocket and wait for the corresponding event."""
        conn = self.active_connections.get(user_id)
        if not conn:
            return False
        ws = conn["ws"]
        event = conn["pong_event"]
        try:
            await ws.send_json({"type": "ping"})
            await asyncio.wait_for(event.wait(), timeout=20.0)
            return True
        except asyncio.TimeoutError:
            return False
        except Exception:
            return False

    async def _per_connection_pinger(self, user_id: int):
        """Independent ping loop for a single connection."""
        try:
            while True:
                await asyncio.sleep(20.0)
                ok = await self.send_ping(user_id)
                if not ok:
                    self.disconnect(user_id,client_initiated=False)
                    break
        except asyncio.CancelledError:
            return
        except Exception:
            self.disconnect(user_id, client_initiated=False)
                    
    async def typing_status(self, message_type: str, receiver_id: int, typing_status: bool):
            message={
            "type":message_type,
            "typing_status":typing_status
            }
            return await self.send_personal_message(message=message,user_id=receiver_id)
# single manager instance
manager = ConnectionManager()
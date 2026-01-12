"""WebSocket connection manager with presence tracking."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Dict, Optional

from fastapi import WebSocket


class ConnectionManager:
    """Track active WebSocket connections grouped by rooms."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._user_sockets: dict[str, set[WebSocket]] = defaultdict(set)
        self._socket_user: dict[WebSocket, str] = {}
        self._presence: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, *, user_id: str, rooms: Optional[list[str]] = None) -> None:
        await websocket.accept()
        async with self._lock:
            self._user_sockets[user_id].add(websocket)
            self._socket_user[websocket] = user_id
            if rooms:
                for room in rooms:
                    self._connections[room].add(websocket)

    async def disconnect(self, websocket: WebSocket, *, user_id: Optional[str] = None) -> None:
        async with self._lock:
            if user_id is None:
                user_id = self._socket_user.get(websocket)
            if user_id and user_id in self._user_sockets:
                self._user_sockets[user_id].discard(websocket)
                if not self._user_sockets[user_id]:
                    del self._user_sockets[user_id]
            self._socket_user.pop(websocket, None)
            for room, room_sockets in list(self._connections.items()):
                room_sockets.discard(websocket)
                if not room_sockets:
                    del self._connections[room]

    async def join_room(self, websocket: WebSocket, room: str) -> None:
        async with self._lock:
            self._connections[room].add(websocket)

    async def leave_room(self, websocket: WebSocket, room: str) -> None:
        async with self._lock:
            if room in self._connections:
                self._connections[room].discard(websocket)
                if not self._connections[room]:
                    del self._connections[room]

    async def broadcast(self, room: str, message: dict[str, Any]) -> None:
        payload = message.copy()
        payload.setdefault("event", "broadcast")
        async with self._lock:
            targets = list(self._connections.get(room, set()))
        for socket in targets:
            try:
                await socket.send_json(payload)
            except Exception:  # pragma: no cover - network errors
                await self.disconnect(socket)

    async def send_to_user(self, user_id: str, message: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._user_sockets.get(user_id, set()))
        for socket in sockets:
            try:
                await socket.send_json(message)
            except Exception:  # pragma: no cover
                await self.disconnect(socket, user_id=user_id)

    async def set_presence(self, user_id: str, *, status: str, context: Optional[dict[str, Any]] = None) -> None:
        async with self._lock:
            self._presence[user_id] = {"status": status, "context": context or {}}

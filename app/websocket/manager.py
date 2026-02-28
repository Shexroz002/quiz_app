from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class SessionConnectionManager:
    """Tracks WebSocket connections per quiz session."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, session_id: int) -> None:
        await websocket.accept()
        self._connections[session_id].add(websocket)

    def disconnect(self, websocket: WebSocket, session_id: int) -> None:
        connections = self._connections.get(session_id)
        if not connections:
            return

        connections.discard(websocket)
        if not connections:
            self._connections.pop(session_id, None)

    def count(self, session_id: int) -> int:
        return len(self._connections.get(session_id, set()))

    async def broadcast(
        self,
        session_id: int,
        event: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        message = {"event": event, "data": payload or {}}
        stale_connections: list[WebSocket] = []

        for connection in self._connections.get(session_id, set()):
            try:
                await connection.send_json(message)
            except (RuntimeError, WebSocketDisconnect):
                stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(connection, session_id)


session_ws_manager = SessionConnectionManager()

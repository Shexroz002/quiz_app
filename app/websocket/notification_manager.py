from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect


class NotificationConnectionManager:
    """Tracks WebSocket connections per user for notifications."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        connections = self._connections.get(user_id)
        if not connections:
            return

        connections.discard(websocket)
        if not connections:
            self._connections.pop(user_id, None)

    def is_connected(self, user_id: int) -> bool:
        """Check if user has any active connections."""
        return len(self._connections.get(user_id, set())) > 0

    def count(self, user_id: int) -> int:
        """Get the number of active connections for a user."""
        return len(self._connections.get(user_id, set()))

    async def send_to_user(
        self,
        user_id: int,
        notification_type: str,
        payload: dict[str, Any] | None = None,
        unread_count: int | None = None,
    ) -> bool:
        """
        Send notification to a specific user.
        Returns True if at least one message was sent successfully.
        """
        message = {
            "type": notification_type,
            "data": payload or {},
        }
        stale_connections: list[WebSocket] = []
        sent = False

        for connection in self._connections.get(user_id, set()):
            try:
                await connection.send_json(message)
                if unread_count is not None:
                    await connection.send_json({
                        "type": "notification_count_update",
                        "data": {"count": unread_count}
                    })
                sent = True
            except (RuntimeError, WebSocketDisconnect):
                stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(connection, user_id)

        return sent


notification_manager = NotificationConnectionManager()


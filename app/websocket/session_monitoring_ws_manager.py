from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class SessionMonitoringWSManager:
    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, session_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[session_id].add(websocket)

    def disconnect(self, session_id: int, websocket: WebSocket) -> None:
        if session_id in self._connections:
            self._connections[session_id].discard(websocket)
            if not self._connections[session_id]:
                del self._connections[session_id]

    async def broadcast(
        self,
        session_id: int,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        dead_connections: list[WebSocket] = []
        for ws in self._connections.get(session_id, set()):
            try:
                await ws.send_json({
                    "event": event,
                    "payload": payload,
                })
            except Exception:
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(session_id, ws)

    def count(self, session_id: int) -> int:
        return len(self._connections.get(session_id, set()))

session_monitoring_ws_manager = SessionMonitoringWSManager()
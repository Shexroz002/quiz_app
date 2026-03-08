from __future__ import annotations

from json import JSONDecodeError

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

from app.websocket.notification_manager import notification_manager
from app.websocket.utils import authenticate_websocket

notification_ws_router = APIRouter(tags=["Notification WebSocket"])

"""
WebSocket endpoint for user notifications.
 ws://localhost:8000/ws/notifications/{user_id}?token=abc123
"""
@notification_ws_router.websocket("/ws/notifications/{user_id}")
async def notification_websocket(websocket: WebSocket) -> None:
    user = await authenticate_websocket(websocket)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        path_user_id = int(websocket.path_params["user_id"])
    except (KeyError, ValueError, TypeError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if user.id != path_user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await notification_manager.connect(websocket, user.id)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        notification_manager.disconnect(websocket, user.id)
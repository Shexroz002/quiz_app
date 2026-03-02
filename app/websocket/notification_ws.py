from __future__ import annotations

from json import JSONDecodeError

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.notification_manager import notification_manager
from app.websocket.utils import authenticate_websocket

notification_ws_router = APIRouter(tags=["Notification WebSocket"])


@notification_ws_router.websocket("/ws/notifications")
async def notification_websocket(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for user notifications.
    Connect with: ws://localhost:8000/ws/notifications?token=<jwt_token>
    """
    user = await authenticate_websocket(websocket)
    if not user:
        return

    await notification_manager.connect(websocket, user.id)

    # Send connection success message
    await websocket.send_json({
        "type": "connection_established",
        "data": {
            "user_id": user.id,
            "message": "Connected to notification service",
        }
    })

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "data": {"detail": "Message must be valid JSON."}}
                )
                continue

            event = message.get("event")

            if event == "ping":
                await websocket.send_json({"type": "pong", "data": {}})
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": {"detail": "Unsupported event. Use event='ping' for heartbeat."},
                    }
                )

    except WebSocketDisconnect:
        notification_manager.disconnect(websocket, user.id)
    except Exception:
        notification_manager.disconnect(websocket, user.id)
        raise

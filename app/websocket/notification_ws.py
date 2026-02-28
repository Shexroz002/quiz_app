from __future__ import annotations

from json import JSONDecodeError

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.database.base import AsyncSessionLocal
from app.core.security.jwt import decode_token
from app.models import User
from app.repositories.account.user_repo import UserRepository
from app.websocket.notification_manager import notification_manager

notification_ws_router = APIRouter(tags=["Notification WebSocket"])


async def _authenticate_websocket(websocket: WebSocket) -> User | None:
    """Authenticate user via WebSocket token."""
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Token is required")
        return None

    payload = decode_token(token)
    user_id = payload.get("sub") if payload else None
    if not user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return None

    async with AsyncSessionLocal() as db:
        user_repo = UserRepository(db)
        user = await user_repo.get_by_id(int(user_id))
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not found")
            return None

        return user


@notification_ws_router.websocket("/ws/notifications")
async def notification_websocket(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for user notifications.
    Connect with: ws://localhost:8000/ws/notifications?token=<jwt_token>
    """
    user = await _authenticate_websocket(websocket)
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


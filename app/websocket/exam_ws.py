from __future__ import annotations

from json import JSONDecodeError

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.database.base import AsyncSessionLocal
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository
from app.repositories.quiz.session_participant import SessionParticipantRepository
from app.websocket.manager import session_ws_manager
from app.websocket.utils.auth_ws import authenticate_websocket

quiz_session_ws_router = APIRouter(tags=["Quiz Session WebSocket"])


async def _is_authorized_for_session(user_id: int, session_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        session_repo = QuizSessionRepository(db)
        participant_repo = SessionParticipantRepository(db)

        session = await session_repo.get_by_id(session_id)
        if not session:
            return False

        if session.host_id == user_id:
            return True

        return await participant_repo.is_participant(session_id=session_id, user_id=user_id)


# WebSocket endpoint for quiz session participation and real-time updates

@quiz_session_ws_router.websocket("/ws/quiz/sessions/{session_id}")
async def quiz_session_websocket(websocket: WebSocket, session_id: int) -> None:
    user = await authenticate_websocket(websocket)
    if not user:
        return

    is_authorized = await _is_authorized_for_session(user_id=user.id, session_id=session_id)
    if not is_authorized:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Forbidden")
        return

    await session_ws_manager.connect(websocket, session_id)

    await session_ws_manager.broadcast(
        session_id=session_id,
        event="participant_connected",
        payload={
            "user_id": user.id,
            "username": user.username,
            "avatar_url": user.profile_image if user.profile_image else None,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "participants_online": session_ws_manager.count(session_id)},
    )

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except JSONDecodeError:
                await websocket.send_json(
                    {"event": "error", "data": {"detail": "Message must be valid JSON."}}
                )
                continue

            event = message.get("event")

            if event == "ping":
                await websocket.send_json({"event": "pong", "data": {}})
            else:
                await websocket.send_json(
                    {
                        "event": "error",
                        "data": {"detail": "Unsupported event. Use event='ping' for heartbeat."},
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        session_ws_manager.disconnect(websocket, session_id)
        await session_ws_manager.broadcast(
            session_id=session_id,
            event="participant_disconnected",
            payload={
                "user_id": user.id,
                "username": user.username,
                "avatar_url": user.profile_image if user.profile_image else None,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "participants_online": session_ws_manager.count(session_id)},
        )

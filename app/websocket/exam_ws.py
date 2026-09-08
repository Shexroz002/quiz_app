from __future__ import annotations

from json import JSONDecodeError

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from app.core.database.base import AsyncSessionLocal
from app.core.database.redis import redis_client
from app.repositories.account import UserRepository
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository
from app.repositories.quiz.session_participant import SessionParticipantRepository
from app.repositories.quiz.quiz_repo import QuizRepository
from app.schemas.quiz.question import BASE_URL
from app.schemas.sessions.session_monitoring import ConnectionStatus, ParticipantLiveStatus
from app.services.redis_service.session_live import SessionLiveStateService
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

async def _change_participant(user_id: int, session_id: int):
    async with AsyncSessionLocal() as db:
        participant_repo = SessionParticipantRepository(db)
        participant = await participant_repo.get_by_session_user(session_id=session_id, user_id=user_id)
        if not participant:
            return None

        session = await QuizSessionRepository(db).get_by_id(session_id)
        user = await UserRepository(db).get_by_id(user_id)
        if not session or not user:
            return None

        await participant_repo.mark_ready(participant)
        await db.commit()

        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
        live_state_service = SessionLiveStateService(redis_client)
        await live_state_service.create_or_get_initial_state(
            session_id=session_id,
            participant_id=participant.id,
            user_id=user.id,
            full_name=full_name,
            nickname=participant.nickname,
            profile_image=f"{BASE_URL}/{user.profile_image}" if user.profile_image else None,
            is_host=participant.is_host,
            total_questions=await QuizRepository(db).quiz_question_count(session.quiz_id),
            connection_status=ConnectionStatus.ONLINE,
            status=ParticipantLiveStatus.READY,
        )
        return await live_state_service.mark_ready(session_id, participant.id)



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
    ready_state = await _change_participant(user_id=user.id, session_id=session_id)
    if ready_state:
        await session_ws_manager.broadcast(
            session_id=session_id,
            event="participant_ready",
            payload={
                "user_id": user.id,
                "status": "ready",
            },
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
            if event == "chat_message":
                user_info = {
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "avatar_url": f"{BASE_URL}/{user.profile_image}" if user.profile_image else None,
                }
                data = {
                    "user_info": user_info,
                    "message": message.get("message"),
                }
                await session_ws_manager.broadcast(
                    session_id=session_id,
                    event="chat_message",
                    payload=data
                )
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

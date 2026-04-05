from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from app.core.database.redis import get_redis_client
from app.core.database.session import AsyncSessionLocal
from app.repositories.quiz.session_participant import SessionParticipantRepository
from app.services.redis_service.session_live import SessionLiveStateService
from app.websocket.session_monitoring_ws_manager import session_monitoring_ws_manager
from app.websocket.utils import authenticate_websocket

quiz_sessions = APIRouter()

# ws://localhost:8000/ws/quiz-sessions/{session_id}/participants/{participant_id}
@quiz_sessions.websocket("/ws/quiz-sessions/{session_id}")
async def student_quiz_session_websocket(
    websocket: WebSocket,
    session_id: int,
    redis: Redis = Depends(get_redis_client),
):

    user = await authenticate_websocket(websocket)
    if not user:
        return
    # await websocket.accept()
    await session_monitoring_ws_manager.connect(session_id, websocket)
    live_state_service = SessionLiveStateService(redis)

    # async with AsyncSessionLocal() as db:
    #     participant_repo = SessionParticipantRepository(db)
    #
    #     participant = await participant_repo.get_by_session_user(
    #         session_id=session_id,
    #         user_id=user.id
    #     )
    #
    #     if not participant:
    #         await websocket.close(code=1008, reason="Not a participant")
    #         return

    # participant_id = participant.id

    try:
        # state = await live_state_service.mark_online(session_id, participant_id)
        #
        # if state:
        #     await session_monitoring_ws_manager.broadcast(
        #         session_id=session_id,
        #         event="participant_monitoring_updated",
        #         payload={
        #             "session_id": session_id,
        #             "participant": state.model_dump(mode="json"),
        #         },
        #     )

        while True:
            data = await websocket.receive_json()
            event = data.get("event")

            # if event == "heartbeat":
            #     state = await live_state_service.touch_heartbeat(session_id, participant_id)
            #
            #     if state:
            #         await session_monitoring_ws_manager.broadcast(
            #             session_id=session_id,
            #             event="participant_monitoring_updated",
            #             payload={
            #                 "session_id": session_id,
            #                 "participant": state.model_dump(mode="json"),
            #             },
            #         )

            await websocket.send_json({
                "event": "heartbeat_ack",
                "payload": {"ok": True},
            })

    except WebSocketDisconnect:
        # state = await live_state_service.mark_offline(session_id, participant_id)
        #
        # if state:
        #     await session_monitoring_ws_manager.broadcast(
        #         session_id=session_id,
        #         event="participant_monitoring_updated",
        #         payload={
        #             "session_id": session_id,
        #             "participant": state.model_dump(mode="json"),
        #         },
        #     )
        pass

    except Exception:
        # state = await live_state_service.mark_offline(session_id, participant_id)
        #
        # if state:
        #     await session_monitoring_ws_manager.broadcast(
        #         session_id=session_id,
        #         event="participant_monitoring_updated",
        #         payload={
        #             "session_id": session_id,
        #             "participant": state.model_dump(mode="json"),
        #         },
        #     )
        await websocket.close()


from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.bot.services.quiz_room import queue_room_maintenance
from app.bot.services.single_player_result import request_single_player_result_delivery
from app.bot.services.webapp_auth import validate_init_data
from app.bot.utils.registration import get_user_by_telegram_id
from app.core.config import settings
from app.core.database.base import get_db
from app.core.security.jwt import create_access_token
from app.models import User
from app.models.account.user import UserType
from app.schemas.quiz.quiz_attempt import FinishQuizResponse, SubmitAnswerRequest, SubmitAnswerResponse
from app.schemas.quiz.quiz_session import StartSessionSinglePlayerResponse
from app.services.quiz.multiplayer import MultiplayerQuizService

router = APIRouter(prefix="/api/v1/bot", tags=["Telegram Mini App"])


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(min_length=1, max_length=16384)


class SinglePlayerResultHandoffResponse(BaseModel):
    accepted: bool
    already_delivered: bool


@router.post("/auth/")
async def authenticate_webapp(payload: TelegramAuthRequest, response: Response):
    try:
        telegram_id = validate_init_data(payload.init_data, settings.TELEGRAM_BOT_TOKEN)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(401, "Telegram sessiyasi yaroqsiz. Botdan testni qayta oching.")
    user = await get_user_by_telegram_id(telegram_id)
    if not user or not user.is_active or user.role not in (UserType.student, UserType.schoolboy):
        raise HTTPException(403, "Avval botda talaba sifatida ro'yxatdan o'ting.")
    response.headers["Cache-Control"] = "no-store"
    return {"access_token": create_access_token(str(user.id)), "token_type": "bearer", "user_id": user.id}


@router.post(
    "/single-player/{session_id}/result/",
    response_model=SinglePlayerResultHandoffResponse,
)
async def handoff_single_player_result(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    delivery = await request_single_player_result_delivery(db, session_id, current_user)
    return {
        "accepted": True,
        "already_delivered": delivery.delivered_at is not None,
    }


@router.get("/rooms/{session_id}/state/")
async def room_state(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    state = await MultiplayerQuizService(db).player_state(session_id, current_user.id)
    if state["status"] == "finished":
        queue_room_maintenance(session_id)
    return state


@router.get("/rooms/{session_id}/questions/", response_model=StartSessionSinglePlayerResponse)
async def room_questions(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await MultiplayerQuizService(db).questions(session_id, current_user.id)


@router.post("/rooms/{session_id}/answer/", response_model=SubmitAnswerResponse)
async def room_answer(
    session_id: int,
    payload: SubmitAnswerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await MultiplayerQuizService(db).answer(session_id, current_user, payload)
    except HTTPException as exc:
        if exc.status_code == 409:
            queue_room_maintenance(session_id)
        raise


@router.post("/rooms/{session_id}/finish/", response_model=FinishQuizResponse)
async def room_finish(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await MultiplayerQuizService(db).finish(session_id, current_user.id)
    queue_room_maintenance(session_id)
    return result

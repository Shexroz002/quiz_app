from typing import List

from fastapi import APIRouter, Depends
from fastapi_pagination import Page

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.models import User

from app.schemas.quiz.quiz_session import (
    QuizSessionResponse,
    GroupQuizSessionCreate, StartSessionResponse, StartSessionSinglePlayerResponse

)
from app.schemas.quiz.session_participant import SessionParticipantList

from app.services.quiz.quiz_session import get_quiz_session_service

quiz_group_session_router = APIRouter(prefix="/live", tags=["Quiz Sessions"])

""""
    BEGIN: Multiplayer Quiz Session Endpoints
"""


@quiz_group_session_router.post("/", status_code=201, response_model=QuizSessionResponse)
async def quiz_session_create(
        quiz_session_data: GroupQuizSessionCreate,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.create_group_session(quiz_session_data, current_user)




@quiz_group_session_router.get("/{session_id}/info/", response_model=QuizSessionResponse)
async def get_multiplayer_player_quiz_info(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_single_player_quiz_info(session_id, current_user.id, is_question=False,
                                                          status="waiting")


@quiz_group_session_router.get("/{session_id}/participants/", response_model=Page[SessionParticipantList])
async def get_session_participants(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_participant(session_id, current_user)


@quiz_group_session_router.post("/{session_id}/start/", response_model=StartSessionResponse)
async def start_quiz_session(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.start_session(session_id, current_user)


@quiz_group_session_router.get("/{session_id}/questions/", response_model=StartSessionSinglePlayerResponse)
async def get_quiz_session_questions(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.multiplayer_session_quiz_info(session_id, current_user.id)
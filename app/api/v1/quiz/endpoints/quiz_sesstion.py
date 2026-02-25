from typing import List

from fastapi import APIRouter, Depends, Body

from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.quiz_session import QuizSessionCreate
from app.schemas.quiz.session_participant import SessionParticipantList

from app.services.quiz.quiz_session import get_quiz_session_service

quiz_session_router = APIRouter(prefix="/sessions", tags=["Quiz Sessions"])


@quiz_session_router.post("/create/", status_code=201)
async def quiz_session_create(
        quiz_session_data: QuizSessionCreate = Body(...),
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service)
):
    return await quiz_session.create(quiz_session_data, current_user)


@quiz_session_router.post("/join/", response_model=List[SessionParticipantList])
async def quiz_session_join(
        session_code: str = Body(..., embed=True),
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service)
):
    participant = await quiz_session.add_participant(session_code, current_user)

    if not participant:
        return {"error": "Invalid session code"}

    return participant


@quiz_session_router.get("/{session_id}/participants/", response_model=List[SessionParticipantList])
async def get_session_participants(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service)
):
    session = await quiz_session.get(session_id, current_user.id)

    if not session:
        return {"error": "Session not found or access denied"}
    result = await quiz_session.get_participant(session_id)

    return result


@quiz_session_router.post("/{session_id}/start/")
async def start_quiz_session(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service)
):
    session = await quiz_session.start_session(session_id, current_user)

    if not session:
        return {"error": "Session not found or access denied"}

    return session

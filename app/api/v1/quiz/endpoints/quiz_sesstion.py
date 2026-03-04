from typing import List, Annotated

from fastapi import APIRouter, Depends
from fastapi.params import Body

from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.quiz_attempt import (
    FinishQuizResponse,
    ParticipantResultResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse, AnswerItem,
)
from app.schemas.quiz.quiz_session import (
    JoinSessionRequest,
    QuizSessionCreate,
    QuizSessionResponse,
    StartSessionResponse, StartSessionSinglePlayerResponse, StartSessionSinglePlayerBaseResponse,
    QuestionErrorAnalyticSessionResponse,
)
from app.schemas.quiz.session_participant import SessionParticipantList
from app.services.quiz.quiz_session import get_quiz_session_service

quiz_session_router = APIRouter(prefix="/sessions", tags=["Quiz Sessions"])


@quiz_session_router.post("/create/", status_code=201, response_model=QuizSessionResponse)
async def quiz_session_create(
        quiz_session_data: QuizSessionCreate,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.create(quiz_session_data, current_user)


@quiz_session_router.post("/join/", response_model=List[SessionParticipantList])
async def quiz_session_join(
        payload: JoinSessionRequest,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.add_participant(payload.session_code, current_user)


@quiz_session_router.get("/{session_id}/participants/", response_model=List[SessionParticipantList])
async def get_session_participants(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_participant(session_id, current_user)


@quiz_session_router.post("/{session_id}/start/", response_model=StartSessionResponse)
async def start_quiz_session(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.start_session(session_id, current_user)


@quiz_session_router.post("/{session_id}/answer/", response_model=SubmitAnswerResponse)
async def submit_answer(
        session_id: int,
        payload: SubmitAnswerRequest,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.submit_answer(session_id, current_user, payload)


@quiz_session_router.post("/{session_id}/finish/", response_model=FinishQuizResponse)
async def finish_quiz(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.finish_quiz(session_id, current_user)


@quiz_session_router.get("/{session_id}/results/", response_model=List[ParticipantResultResponse])
async def host_participant_results(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_all_participant_results(session_id, current_user)


@quiz_session_router.get("/{session_id}/topic-statistic/")
async def topic_statistic(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.topic_statistic(session_id, current_user)


# quiz start for single player
@quiz_session_router.post("/{quiz_id}/start-single-player/", response_model=StartSessionSinglePlayerBaseResponse)
async def start_single_player_quiz(
        quiz_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.start_single_player_quiz(quiz_id, current_user)


@quiz_session_router.get("/{session_id}/start-single-player/info", response_model=StartSessionSinglePlayerResponse)
async def get_single_player_quiz_info(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_single_player_quiz_info(session_id, current_user.id)


@quiz_session_router.post("/{session_id}/finish-single-player/", response_model=FinishQuizResponse)
async def finish_single_player_quiz(
        session_id: int,
        answers: Annotated[
            list[AnswerItem],
            Body(
                ...,
                examples=[[
                    {"question_id": 1, "selected_option": "A"},
                    {"question_id": 2, "selected_option": "C"},
                ]],
            ),
        ],
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.finish_single_player_quiz(session_id, current_user.id, answers)

@quiz_session_router.get("/{session_id}/single-player-error-analysis/",response_model=List[QuestionErrorAnalyticSessionResponse])
async def single_player_error_analysis(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.single_player_error_analysis(session_id, current_user.id)
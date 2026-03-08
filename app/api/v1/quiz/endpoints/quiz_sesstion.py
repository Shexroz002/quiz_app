from typing import List, Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.params import Body

from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.notification.notification import NotificationCreateSchema
from app.schemas.quiz.quiz_attempt import (
    FinishQuizResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse, AnswerItem,
)
from app.schemas.quiz.quiz_session import (
    JoinSessionRequest,
    QuizSessionCreate,
    QuizSessionResponse,
    StartSessionResponse, StartSessionSinglePlayerResponse, StartSessionSinglePlayerBaseResponse,
    QuestionErrorAnalyticSessionResponse, SessionLeaderboardRow, ParticipantResultResponse
)
from app.schemas.quiz.session_participant import SessionParticipantList
from app.services.notification.notification_service import get_notification_service
from app.services.quiz.quiz_session import get_quiz_session_service

quiz_session_router = APIRouter(prefix="/sessions", tags=["Quiz Sessions"])

""""
    BEGIN: Multiplayer Quiz Session Endpoints
"""


@quiz_session_router.post("/multiplayer/create/", status_code=201, response_model=QuizSessionResponse)
async def quiz_session_create(
        quiz_session_data: QuizSessionCreate,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.create(quiz_session_data, current_user)


@quiz_session_router.post("/multiplayer/join/", response_model=List[SessionParticipantList])
async def quiz_session_join(
        payload: JoinSessionRequest,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.add_participant(payload.session_code, current_user)


@quiz_session_router.get("/multiplayer/{session_id}/info/", response_model=QuizSessionResponse)
async def get_multiplayer_player_quiz_info(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_single_player_quiz_info(session_id, current_user.id, is_question=False,
                                                          status="waiting")


@quiz_session_router.get("/multiplayer/{session_id}/participants/", response_model=List[SessionParticipantList])
async def get_session_participants(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_participant(session_id, current_user)


@quiz_session_router.post("/multiplayer/{session_id}/start/", response_model=StartSessionResponse)
async def start_quiz_session(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.start_session(session_id, current_user)


@quiz_session_router.post("/multiplayer/{session_id}/answer/", response_model=SubmitAnswerResponse)
async def submit_answer(
        session_id: int,
        payload: SubmitAnswerRequest,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.submit_answer(session_id, current_user, payload)

""" Invite other players to the quiz session"""
@quiz_session_router.post("/multiplayer/{session_id}/invite/")
async def invite_players(
        session_id: int,
        recipient_id: int = Body(..., embed=True, description="ID of the user to invite"),
        current_user: User = Depends(get_current_user),
        notification_service=Depends(get_notification_service),
):
    data={
        "recipient_id": recipient_id,
        "sender_id": current_user.id,
        "type": "test_invite",
        "action_type": "test_invite",
        "payload": {"session_id": session_id},
        "title": "Quiz Session  taklif",
        "message": "You have been invited to join a quiz session"
    }
    data_schema = NotificationCreateSchema(**data)
    await notification_service.create_notification(data_schema)
    return {"message": "Invitation sent successfully"}


@quiz_session_router.post("/multiplayer/{session_id}/finish/", response_model=FinishQuizResponse)
async def finish_quiz(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.finish_quiz(session_id, current_user)


@quiz_session_router.get("/multiplayer/{session_id}/results/", response_model=List[ParticipantResultResponse])
async def host_participant_results(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_all_participant_results(session_id, current_user)


@quiz_session_router.get("/multiplayer/{session_id}/topic-statistic/")
async def topic_statistic(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.topic_statistic(session_id, current_user)


""" END: Multiplayer Quiz Session Endpoints """

"""    BEGIN: Single Player Quiz Session Endpoints  """


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
    return await quiz_session.get_single_player_quiz_info(session_id, current_user.id, status="running")


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


"""   END: Single Player Quiz Session Endpoints  """


@quiz_session_router.get("/{session_id}/single-player-error-analysis/",
                         response_model=List[QuestionErrorAnalyticSessionResponse])
async def single_player_error_analysis(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.single_player_error_analysis(session_id, current_user.id)


# fetch quiz session hisotry for single player
@quiz_session_router.get("/me/history/", response_model=List[SessionLeaderboardRow])
async def single_player_quiz_history(
        search: Optional[str] = Query(
            default=None,
            description="Search by quiz title or subject",
            min_length=1,
        ),
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.personal_quiz_session_history(current_user.id, search)


@quiz_session_router.get("/{session_id}/leaderboard/", response_model=List[ParticipantResultResponse])
async def quiz_session_leaderboard(
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.session_participant_rank_list(session_id, current_user.id)

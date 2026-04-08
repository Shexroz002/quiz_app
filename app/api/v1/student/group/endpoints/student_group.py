from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Form, UploadFile, File, Query, Path
from fastapi_pagination import Page

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.models import User
from app.models.group.student_group import GroupColor
from app.schemas.group.student_group import StudentGroupResponseSchema, StudentGroupCreateSchema, \
    StudentGroupUpdateSchema, StudentGroupCardSchema, GroupCoverImageResponseSchema, GroupMemberTableItemSchema, \
    StudentGroupDetailCardSchema, GroupStudentPerformanceSchema, GroupTestResultItemSchema
from app.schemas.quiz.quiz_session import SessionResultsDetailSchema, ParticipantResultResponse, \
    SessionQuestionAccuracyItemSchema
from app.services.group.student_group_service import get_student_group_service, StudentGroupService
from app.services.quiz.quiz_session import get_quiz_session_service

group_router_v2 = APIRouter(prefix="", )


@group_router_v2.get("/", response_model=Page[StudentGroupCardSchema])
async def list_groups(
        search: str | None = Query(None, description="Search  by group name"),
        subject_id: int | None = Query(None, description="Filter by subject ID"),
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    return await service.list_groups_by_member_id(member_id=current_user.id, search=search, subject_id=subject_id, )


@group_router_v2.get("/{group_id}/detail-card", response_model=StudentGroupDetailCardSchema)
async def get_group_detail_card(
        group_id: int,
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    data = await service.group_detail_card_for_student(
        group_id=group_id,
        member_id=current_user.id,
    )
    if not data:
        raise HTTPException(status_code=404, detail="Group not found")
    return data


@group_router_v2.get("/{group_id}/students-performance", response_model=Page[GroupStudentPerformanceSchema])
async def get_group_students_performance(
        group_id: int,
        search: str | None = Query(None),
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    return await service.group_students_performance(group_id=group_id, member_id=current_user.id, search=search)


@group_router_v2.get("/{group_id}/sessions", response_model=Page[GroupTestResultItemSchema])
async def get_group_tests(
        group_id: int,
        current_user=Depends(get_current_user),
        service: StudentGroupService = Depends(get_student_group_service),
):
    return await service.group_test_results(group_id=group_id, member_id=current_user.id)


@group_router_v2.get(
    "/{group_id}/results/{session_id}",
    response_model=SessionResultsDetailSchema,
)
async def get_session_results_detail(
        group_id: int,
        session_id: int,
        current_user=Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    data = await quiz_session.student_session_result_details(
        session_id=session_id,
        group_id=group_id,
        member_id=current_user.id,
    )
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data


@group_router_v2.get(
    "/{group_id}/question-accuracy/{session_id}",
    response_model=list[SessionQuestionAccuracyItemSchema],
)
async def get_session_question_accuracy(
        group_id: int,
        session_id: int,
        current_user=Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.student_session_question_accuracy(
        session_id=session_id,
        group_id=group_id,
        member_id=current_user.id,
    )


@group_router_v2.get("/{group_id}/leaderboard/{session_id}", response_model=Page[ParticipantResultResponse])
async def quiz_session_leaderboard(
        group_id: int,
        session_id: int,
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.student_session_participant_rank_list(session_id=session_id, group_id=group_id,
                                                                    member_id=current_user.id, )

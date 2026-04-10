from fastapi import APIRouter, Depends
from fastapi_pagination import Page

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.quiz_session import (
    TeacherOverviewResponse
)
from app.schemas.statistic.teacher_dashboard import TeacherActivityChartResponse
from app.schemas.statistic.teacher_statistics import TeacherAnalyticsOverviewResponse, TeacherGroupResultsResponse, \
    TeacherWeakTopicsResponse, WeakStudentsResponse, WeakStudentsFilterParams

from app.services.quiz.quiz_session import get_quiz_session_service

statistic_router = APIRouter(prefix="", tags=["Statistics"])


@statistic_router.get("/card", status_code=201, response_model=TeacherOverviewResponse)
async def teacher_dashboard_cards(
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_teacher_overview_cards(current_user.id)


@statistic_router.get("/activity-chart", response_model=TeacherActivityChartResponse)
async def activity_chart_teacher(
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_teacher_activity_chart(current_user.id)


@statistic_router.get("/overview", response_model=TeacherAnalyticsOverviewResponse)
async def teacher_analytics_overviews(
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_teacher_analytics_overview(current_user.id)


@statistic_router.get("/groups", response_model=Page[TeacherGroupResultsResponse])
async def teacher_group_results(
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_teacher_group_results(current_user.id)


@statistic_router.get("/week-topics", response_model=Page[TeacherWeakTopicsResponse])
async def teacher_week_topics(
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_teacher_weak_topics(current_user.id)


@statistic_router.get("/week-students", response_model=Page[WeakStudentsResponse])
async def teacher_weak_students(
        filters: WeakStudentsFilterParams = Depends(),
        current_user: User = Depends(get_current_user),
        quiz_session=Depends(get_quiz_session_service),
):
    return await quiz_session.get_teacher_weak_students(current_user.id, filters)

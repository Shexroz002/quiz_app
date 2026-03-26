from fastapi import APIRouter

from app.api.v1.teacher.quiz_session.endpoints.group_quiz_live import quiz_group_session_router

quiz_group_live_base = APIRouter(prefix="/quiz-sessions", tags=["Group Quiz Live"])
quiz_group_live_base.include_router(quiz_group_session_router)
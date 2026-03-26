from fastapi import APIRouter

from app.api.v1.teacher.quiz.endpoints.quiz import teacher_quiz_router

base_teacher_quiz_router = APIRouter(prefix="/quizzes", tags=["Teacher Quiz"])
base_teacher_quiz_router.include_router(teacher_quiz_router)

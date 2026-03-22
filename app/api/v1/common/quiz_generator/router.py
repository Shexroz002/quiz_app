from fastapi import APIRouter

from app.api.v1.common.quiz_generator.endpoints.ai_quiz import ai_quiz_generator

quiz_generator_router = APIRouter(prefix="/quiz-generator", tags=["Quiz Generator"])
quiz_generator_router.include_router(ai_quiz_generator)

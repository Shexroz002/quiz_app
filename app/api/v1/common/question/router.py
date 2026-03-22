from fastapi import APIRouter

from app.api.v1.common.question.endpoints.question import question_router


base_question_router = APIRouter(prefix="/question", tags=["Question Management"])
base_question_router.include_router(question_router)
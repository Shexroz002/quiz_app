from typing import List
from fastapi import APIRouter, Depends
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.quiz import QuizListSchema, QuizUpdateSchema
from app.services.quiz.quiz_service import get_quiz_service

quiz_router = APIRouter(prefix="", tags=["Quiz Management"])


@quiz_router.get("/list/", response_model=List[QuizListSchema])
async def list_quizzes(current_user: User = Depends(get_current_user), quiz_service=Depends(get_quiz_service)):
    return await quiz_service.list(current_user.id)


@quiz_router.get("/{quiz_id}/", response_model=QuizListSchema)
async def get_quiz(quiz_id: int, current_user=Depends(get_current_user), quiz_service=Depends(get_quiz_service)):
    return await quiz_service.get(quiz_id, current_user.id)


@quiz_router.delete("/{quiz_id}/")
async def delete_quiz(quiz_id: int, current_user=Depends(get_current_user), quiz_service=Depends(get_quiz_service)):
    return await quiz_service.delete(quiz_id, current_user.id)


@quiz_router.put("/{quiz_id}/", response_model=QuizListSchema)
async def update_quiz(quiz_id: int, update_data: QuizUpdateSchema, current_user=Depends(get_current_user),
                      quiz_service=Depends(get_quiz_service)):
    return await quiz_service.update(quiz_id, current_user.id, update_data.model_dump())


from typing import List
from fastapi import APIRouter, Depends
from fastapi_pagination import Page

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.quiz import QuizListSchema, QuizUpdateSchema, QuizDetailSchema
from app.services.quiz.quiz_service import get_quiz_service

teacher_quiz_router = APIRouter(prefix="",)


@teacher_quiz_router.get("/list/", response_model=Page[QuizListSchema])
async def list_quizzes(search: str = None, current_user: User = Depends(get_current_user),
                       service_layer=Depends(get_quiz_service)):
    return await service_layer.quiz_list(current_user.id, search=search)


@teacher_quiz_router.get("/{quiz_id}/", response_model=QuizDetailSchema)
async def get_quiz(quiz_id: int, current_user=Depends(get_current_user), service_layer=Depends(get_quiz_service)):
    return await service_layer.detail(current_user.id, quiz_id)


@teacher_quiz_router.delete("/{quiz_id}/")
async def delete_quiz(quiz_id: int, current_user=Depends(get_current_user), service_layer=Depends(get_quiz_service)):
    return await service_layer.delete(quiz_id, current_user.id)


@teacher_quiz_router.put("/{quiz_id}/", response_model=QuizListSchema)
async def update_quiz(quiz_id: int, update_data: QuizUpdateSchema, current_user=Depends(get_current_user),
                      service_layer=Depends(get_quiz_service)):
    return await service_layer.update(quiz_id, current_user.id, update_data.model_dump())



from fastapi import APIRouter, Depends
from fastapi_pagination import Page

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.api.v1.teacher.quiz.params.quiz_filter import TeacherQuizListFilterSchema
from app.models import User
from app.schemas.quiz.quiz import QuizListSchema, QuizUpdateSchema, QuizDetailSchema, TeacherQuizListItemSchema, \
    QuizStatisticsSchema
from app.services.quiz.quiz_service import get_quiz_service

teacher_quiz_router = APIRouter(prefix="", )


@teacher_quiz_router.get("/", response_model=Page[TeacherQuizListItemSchema])
async def list_quizzes(filters: TeacherQuizListFilterSchema = Depends(), current_user: User = Depends(get_current_user),
                       service_layer=Depends(get_quiz_service)):
    return await service_layer.get_teacher_quizzes(current_user.id, filters)


@teacher_quiz_router.get('/{quiz_id}/statistic', response_model=QuizStatisticsSchema)
async def get_quiz_statistic(quiz_id: int, current_user=Depends(get_current_user),
                             service_layer=Depends(get_quiz_service)):
    return await service_layer.get_quiz_statistics(quiz_id, current_user.id)


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

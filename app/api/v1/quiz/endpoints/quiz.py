from typing import List
from fastapi import APIRouter, Depends
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.quiz import QuizListSchema, QuizUpdateSchema, QuizDetailSchema, TopicStatisticResponse, \
    SubjectStatisticResponse, OverallStatisticCardsResponse
from app.services.quiz.quiz_service import get_quiz_service

quiz_router = APIRouter(prefix="", tags=["Quiz Management"])


@quiz_router.get("/list/", response_model=List[QuizListSchema])
async def list_quizzes(search: str = None, current_user: User = Depends(get_current_user),
                       service_layer=Depends(get_quiz_service)):
    return await service_layer.quiz_list(current_user.id, search=search)


@quiz_router.get("/{quiz_id}/", response_model=QuizDetailSchema)
async def get_quiz(quiz_id: int, current_user=Depends(get_current_user), service_layer=Depends(get_quiz_service)):
    return await service_layer.detail(current_user.id, quiz_id)


@quiz_router.delete("/{quiz_id}/")
async def delete_quiz(quiz_id: int, current_user=Depends(get_current_user), service_layer=Depends(get_quiz_service)):
    return await service_layer.delete(quiz_id, current_user.id)


@quiz_router.put("/{quiz_id}/", response_model=QuizListSchema)
async def update_quiz(quiz_id: int, update_data: QuizUpdateSchema, current_user=Depends(get_current_user),
                      service_layer=Depends(get_quiz_service)):
    return await service_layer.update(quiz_id, current_user.id, update_data.model_dump())


@quiz_router.get("/analytics/topic", response_model=List[TopicStatisticResponse])
async def topic_statistics(
        subject: str,
        search: str | None = None,
        current_user=Depends(get_current_user),
        service_layer=Depends(get_quiz_service)
):
    return await service_layer.topic_statistics(current_user.id, subject,search)


@quiz_router.get("/analytics/subjects", response_model=List[SubjectStatisticResponse], )
async def subject_statistics(current_user=Depends(get_current_user), service_layer=Depends(get_quiz_service)):
    return await service_layer.subject_statistics(current_user.id)

@quiz_router.get("/analytics/recommendation")
async def recommendation(current_user=Depends(get_current_user), service_layer=Depends(get_quiz_service)):
    return await service_layer.recommendation(current_user.id)

@quiz_router.get("/analytics/overall/cards", response_model=OverallStatisticCardsResponse | None,)
async def overall_statistic_cards(current_user=Depends(get_current_user), service_layer=Depends(get_quiz_service)):
    return await service_layer.overall_statistic_cards(current_user.id)


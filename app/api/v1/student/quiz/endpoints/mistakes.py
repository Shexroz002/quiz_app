from typing import List

from fastapi import APIRouter, Depends

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.mistake import (
    MistakeAnswerRequest,
    MistakeAnswerResponse,
    MistakeOverviewSchema,
    MistakeQuestionSchema,
)
from app.services.quiz.mistake_service import get_mistake_service

mistake_router = APIRouter(prefix="/mistakes", tags=["Mistake Bank"])


@mistake_router.get("/overview/", response_model=MistakeOverviewSchema)
async def mistakes_overview(
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_mistake_service),
):
    """Counts for the bank screen: what is open, what is due, per subject."""
    return await service_layer.overview(current_user.id)


@mistake_router.get("/review/", response_model=List[MistakeQuestionSchema])
async def mistakes_review(
    subject: str | None = None,
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_mistake_service),
):
    """Questions to review now. Empty when nothing is due yet."""
    return await service_layer.review_batch(current_user.id, subject=subject)


@mistake_router.post("/{question_id}/answer/", response_model=MistakeAnswerResponse)
async def mistakes_answer(
    question_id: int,
    payload: MistakeAnswerRequest,
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_mistake_service),
):
    """Records one review answer and reschedules the question."""
    return await service_layer.answer(current_user.id, question_id, payload.selected_option)

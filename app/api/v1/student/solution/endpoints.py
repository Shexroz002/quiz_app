from typing import List

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.solution.solution import (
    ExplanationResponse,
    FeedbackCreate,
    FeedbackResponse,
    RecognizeResponse,
    SolutionQuota,
    SolveCreate,
    SolveHistoryItem,
    SolveRequestResponse,
)
from app.services.solution.service import get_solution_service

solution_router = APIRouter(tags=["Solutions"])


@solution_router.get("/questions/{question_id}/explanation/", response_model=ExplanationResponse)
async def question_explanation(
    question_id: int,
    chosen: str | None = None,
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_solution_service),
):
    """Step-by-step solution of a bank question the student has finished.

    ``chosen`` is the option the student picked; when it is wrong, the reply
    carries a hint about how that option probably came about.
    """
    return await service_layer.explanation(current_user.id, question_id, chosen)


# Static paths before /solve/{request_id}/, so "quota" is never read as an id.
@solution_router.get("/solve/quota/", response_model=SolutionQuota)
async def solve_quota(
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_solution_service),
):
    """How many problems the student can still bring in today."""
    return await service_layer.quota(current_user.id)


@solution_router.get("/solve/history/", response_model=List[SolveHistoryItem])
async def solve_history(
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_solution_service),
):
    """The student's recent problems, newest first."""
    return await service_layer.history(current_user.id)


@solution_router.post("/solve/recognize/", response_model=RecognizeResponse)
async def solve_recognize(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_solution_service),
):
    """Reads a photographed problem. Nothing is solved until the text is confirmed."""
    return await service_layer.recognize(current_user.id, file)


@solution_router.post("/solve/", response_model=SolveRequestResponse)
async def solve_create(
    payload: SolveCreate,
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_solution_service),
):
    """Queues a problem: the confirmed text of a photo, or typed text."""
    return await service_layer.submit(current_user.id, payload)


@solution_router.get("/solve/{request_id}/", response_model=SolveRequestResponse)
async def solve_status(
    request_id: int,
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_solution_service),
):
    """The problem's status and, once done, its solution."""
    return await service_layer.request(current_user.id, request_id)


@solution_router.post("/solve/{request_id}/retry/", response_model=SolveRequestResponse)
async def solve_retry(
    request_id: int,
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_solution_service),
):
    """Sends a problem that failed for lack of the model again, at no extra cost."""
    return await service_layer.retry(current_user.id, request_id)


@solution_router.post("/solve/feedback/", response_model=FeedbackResponse)
async def solve_feedback(
    payload: FeedbackCreate,
    current_user: User = Depends(get_current_user),
    service_layer=Depends(get_solution_service),
):
    """"Was it clear?" on a bank solution or on the student's own problem."""
    return await service_layer.feedback(current_user.id, payload)

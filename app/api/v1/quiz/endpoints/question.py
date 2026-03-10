from fastapi import APIRouter, Depends, UploadFile, File
from starlette import status

from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.question import QuestionDetail
from app.services.quiz.question_service import get_question_service, QuestionService

question_router = APIRouter(prefix="/question", tags=["Question Management"])


@question_router.get("/detail/{question_id}", response_model=QuestionDetail)
async def question_detail(question_id:int,current_user: User = Depends(get_current_user), question_service=Depends(get_question_service)):
    return await question_service.detail(question_id, current_user.id)


@question_router.post(
    "/upload-image/{question_id}",
    status_code=status.HTTP_200_OK,
)
async def upload_image_to_question(
    question_id: int,
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    question_service: QuestionService = Depends(get_question_service),
):
    return await question_service.upload_image_to_question(
        question_id=question_id,
        user_id=current_user.id,
        image=image,
    )

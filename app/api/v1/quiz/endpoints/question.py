from fastapi import APIRouter, Depends
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.models import User
from app.schemas.quiz.question import QuestionDetail
from app.services.quiz.question_service import get_question_service

question_router = APIRouter(prefix="/question", tags=["Question Management"])


@question_router.get("/detail/{question_id}", response_model=QuestionDetail)
async def question_detail(question_id:int,current_user: User = Depends(get_current_user), question_service=Depends(get_question_service)):
    return await question_service.detail(question_id, current_user.id)

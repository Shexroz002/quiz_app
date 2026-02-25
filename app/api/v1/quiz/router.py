from fastapi import APIRouter


from app.api.v1.quiz.endpoints.quiz import quiz_router
from app.api.v1.quiz.endpoints.quiz_sesstion import quiz_session_router


base_quiz_router = APIRouter(prefix="/quiz", tags=["Quiz"])
base_quiz_router.include_router(quiz_router)
base_quiz_router.include_router(quiz_session_router)

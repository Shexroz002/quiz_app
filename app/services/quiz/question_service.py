from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.models.quiz import Question
from app.repositories.quiz.question_repo import QuestionRepository


class QuestionService:

    def __init__(self, db: AsyncSession):
        self.repo = QuestionRepository(db)

    async def detail(self, question_id:int,user_id:int) -> Question:
        return await self.repo.detail(question_id, user_id)


def get_question_service(db: AsyncSession = Depends(get_db)) -> QuestionService:
    return QuestionService(db)

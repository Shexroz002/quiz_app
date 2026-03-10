from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import QuestionImage
from app.models.quiz import Question
from app.repositories.base.base_repository import BaseRepository


class QuestionRepository(BaseRepository):
    def __init__(self, db: AsyncSession):
        super().__init__(Question, db)

    async def detail(self, question_id: int, user_id: int):
        stmt = (
            select(Question)
            .where(Question.id == question_id, Question.quiz.has(user_id=user_id))
            .options(
                selectinload(Question.options),
                selectinload(Question.images),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_with_details(self, quiz_id: int, user_id: int):
        stmt = (
            select(Question)
            .where(Question.quiz_id == quiz_id, Question.quiz.has(user_id=user_id))
            .options(
                selectinload(Question.options),
                selectinload(Question.images),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def list_quiz_session_questions(self, quiz_id: int):
        stmt = (
            select(Question)
            .where(Question.quiz_id == quiz_id)
            .options(
                selectinload(Question.options),
                selectinload(Question.images),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def upload_image_to_question(self, question_id: int, user_id: int, image_url: str):

        question = await self.detail(question_id, user_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")

        if len(question.images) >= 2:
            raise HTTPException(status_code=400, detail="Only one image can be uploaded")

        question_image = QuestionImage(question_id=question_id, image_url=image_url)
        self.db.add(question_image)
        await self.db.flush()
        return question_image

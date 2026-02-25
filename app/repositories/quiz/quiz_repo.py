from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Quiz, Option
from app.models.quiz import Question


class QuizRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, user_id: int):
        stmt = select(Quiz).where(Quiz.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get(self, quiz_id: int, user_id: int):
        stmt = select(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, quiz_id: int, user_id, update_data: dict):
        quiz = await self.get(quiz_id, user_id)

        if not quiz:
            return None

        for field, value in update_data.items():
            if hasattr(quiz, field):
                setattr(quiz, field, value)

        self.db.add(quiz)
        await self.db.commit()
        await self.db.refresh(quiz)
        return quiz

    async def delete(self, quiz_id: int, user_id: int):
        quiz = await self.get(quiz_id, user_id)

        if not quiz:
            return None

        await self.db.delete(quiz)
        await self.db.commit()
        return quiz

    async def get_quiz_full_info(self, quiz_id):
        stmt = (
            select(Quiz)
            .where(Quiz.id == quiz_id)
            .options(
                selectinload(Quiz.questions)
                .selectinload(Question.options),
                selectinload(Quiz.questions)
                .selectinload(Question.images),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def quiz_answer_by_id(self, quiz_id: int):
        stmt = (
            select(Question.id, Option.label)
            .join(Quiz.questions)
            .join(Question.options)
            .where(
                Quiz.id == quiz_id,
                Option.is_correct.is_(True)
            )
        )

        result = await self.db.execute(stmt)
        return result.mappings().all()
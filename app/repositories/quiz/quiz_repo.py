from fastapi import HTTPException
from sqlalchemy import select, and_, text, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import func

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

    async def quiz_list(self,user_id, **kwargs):
        """
        Get a list of all quizzes
        Searchable by title,subject
        returns like [
            {
                "id": 1,
                "title": "Quiz 1",
                "user_id": 1,
                "created_at": "2024-06-01T12:00:00",
                "question_count": 5,
                "description": "A sample quiz",
                "subject": "Math",
                "is_new": false if created_at is more than 7 days ago else true
            },
            ...
        
        """
        conditions = [Quiz.user_id == user_id]

        # optional search filter
        search = kwargs.get("search")
        if search:
            # Example: search in title/description (adjust to your needs)
            like = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Quiz.title.ilike(like),
                    Quiz.description.ilike(like),
                )
            )

        stmt = (
            select(
                Quiz.id,
                Quiz.title,
                Quiz.user_id,
                Quiz.created_at,
                Quiz.description,
                Quiz.subject,
                func.count(Question.id).label("question_count"),
                ((func.now() - Quiz.created_at) < text("interval '7 days'")).label("is_new"),
            )
            .select_from(Quiz)
            .outerjoin(Question, Question.quiz_id == Quiz.id) 
            .where(and_(*conditions))
            .group_by(
                Quiz.id,
                Quiz.title,
                Quiz.user_id,
                Quiz.created_at,
                Quiz.description,
                Quiz.subject,
            )
            .order_by(Quiz.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.mappings().all()

    async def detail(self, user_id,quiz_id):


        stmt = (
            select(Quiz)
            .options(selectinload(Quiz.questions))
            .where(Quiz.id == quiz_id)
        )

        quiz = (await self.db.execute(stmt)).scalars().first()
        if not quiz:
            raise HTTPException(404, "Quiz not found")

        return quiz
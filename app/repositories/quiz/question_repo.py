from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.quiz import Question
from app.repositories.base.base_repository import BaseRepository


class QuestionRepository(BaseRepository):
        def __init__(self, db: AsyncSession):
            super().__init__(Question, db)


        async def get_quiz_with_option(self,quiz_id):
            stmt = select(Question).where(Question.quiz_id == quiz_id).options(selectinload(Question.options))
            result = await self.db.execute(stmt)
            return result.scalars().all()

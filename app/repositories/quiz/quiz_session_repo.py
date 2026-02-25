from datetime import datetime, timedelta, UTC
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuizSession


class QuizSessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @asynccontextmanager
    async def transaction(self):
        async with self.db.begin():
            yield

    async def get(self, session_id: int, host_id) -> QuizSession:
        stmt = select(QuizSession).where(QuizSession.id == session_id, QuizSession.host_id == host_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, quiz_session_create_data: dict) -> QuizSession:
        quiz_session = QuizSession(**quiz_session_create_data)
        self.db.add(quiz_session)
        await self.db.flush()
        return quiz_session

    async def delete(self, quiz_session: QuizSession, host_id: int):
        if quiz_session.host_id != host_id:
            return None
        await self.db.delete(quiz_session)
        await self.db.commit()
        return quiz_session

    async def get_by_join_code(self, join_code: str) -> QuizSession:
        stmt = select(QuizSession).where(QuizSession.join_code == join_code)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def start_session(self, quiz_session: QuizSession, host_id: int):
        if quiz_session.host_id != host_id:
            return None
        if  self.check_session_status(quiz_session):
            return None

        now = datetime.now(UTC)

        quiz_session.status = "active"
        quiz_session.started_at = now
        quiz_session.finished_at = now + timedelta(
            minutes=quiz_session.duration_minutes
        )

        await self.db.commit()
        await self.db.refresh(quiz_session)

        return quiz_session

    @staticmethod
    async def check_session_status(quiz_session: QuizSession):
        if quiz_session.status != "waiting":
            return False

        return True

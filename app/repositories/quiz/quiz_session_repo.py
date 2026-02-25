from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuizSession


class QuizSessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_host(self, session_id: int, host_id: int) -> QuizSession | None:
        stmt = select(QuizSession).where(
            QuizSession.id == session_id,
            QuizSession.host_id == host_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, session_id: int) -> QuizSession | None:
        stmt = select(QuizSession).where(QuizSession.id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_join_code(self, join_code: str) -> QuizSession | None:
        stmt = select(QuizSession).where(QuizSession.join_code == join_code)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> QuizSession:
        quiz_session = QuizSession(**data)
        self.db.add(quiz_session)
        await self.db.flush()
        return quiz_session

    async def start_session(self, quiz_session: QuizSession) -> QuizSession:
        now = datetime.now(UTC)
        quiz_session.status = "running"
        quiz_session.started_at = now
        quiz_session.finished_at = now + timedelta(minutes=quiz_session.duration_minutes)
        await self.db.flush()
        return quiz_session

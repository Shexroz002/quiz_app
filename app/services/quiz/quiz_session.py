from contextlib import asynccontextmanager

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database.base import get_db
from app.models import User
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository
from app.repositories.quiz.session_participant import SessionParticipantRepository
from app.schemas.quiz.session_participant import SessionParticipantCreate
from app.schemas.quiz.quiz_session import QuizSessionCreate


def generate_join_code():
    import random
    import string
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


class QuizSessionService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = QuizSessionRepository(db)
        self.participant_repo = SessionParticipantRepository(db)

    async def get(self, session_id: int, host_id: int):
        return await self.repo.get(session_id, host_id)

    async def create(self, quiz_session_data: QuizSessionCreate, user: User):
        quiz_session = await self.repo.create({
            **quiz_session_data.model_dump(),
            "host_id": user.id,
            "join_code": generate_join_code(),
            "status": "waiting",
        })

        await self.participant_repo.create(
            SessionParticipantCreate(
                session_id=quiz_session.id,
                nickname=user.username,
                user_id=user.id,
                is_host=True,
            )
        )

        return quiz_session

    async def add_participant(self, session_code: str, user: User):
        quiz_session = await self.repo.get_by_join_code(session_code)

        if not quiz_session:
            return None

        participant_list = await  self.participant_repo.get_participant_list(quiz_session.id)
        if await self.participant_repo.is_participant(quiz_session.id, user.id):
            return participant_list

        await self.participant_repo.create(
            SessionParticipantCreate(
                session_id=quiz_session.id,
                nickname=user.username,
                user_id=user.id,
                is_host=False,
            )
        )

        return participant_list

    async def get_participant(self, session_id: int):
        return await self.participant_repo.get_participant_list(session_id)

    async def start_session(self, session_id: int, user: User):
        quiz_session = await self.repo.get(session_id, user.id)

        if not quiz_session:
            return None

        return await self.repo.start_session(quiz_session, user.id)


def get_quiz_session_service(db: AsyncSession = Depends(get_db)) -> QuizSessionService:
    return QuizSessionService(db)

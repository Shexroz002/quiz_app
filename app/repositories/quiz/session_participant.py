from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import SessionParticipant, User
from app.schemas.quiz.quiz_live import SessionParticipantCreate


class SessionParticipantRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, session_create_data: SessionParticipantCreate) -> SessionParticipant:
        session_participant = SessionParticipant(**session_create_data.model_dump())
        self.db.add(session_participant)
        await self.db.flush()
        await self.db.commit()
        return session_participant

    async def get_participant_by_session_id(self, session_id: int):
        stmt = (
            select(
                User.first_name,
                User.last_name,
                SessionParticipant.nickname,
                SessionParticipant.is_host,
            )
            .join(SessionParticipant,
                  SessionParticipant.user_id == User.id)
            .where(SessionParticipant.session_id == session_id)
        )

        result = await self.db.execute(stmt)
        return result.mappings().all()


    async def get_participant_list(self, quiz_id: int):
        stmt = (
            select(
                User.first_name,
                User.last_name,
                SessionParticipant.nickname,
                User.profile_image,
                SessionParticipant.is_host,
            )
            .join(SessionParticipant,
                  SessionParticipant.user_id == User.id)
            .where(SessionParticipant.session_id == quiz_id)
        )

        result = await self.db.execute(stmt)
        return result.mappings().all()

    async def is_participant(self, quiz_id: int, user_id: int):
        stmt = (
            select(SessionParticipant)
            .where(SessionParticipant.session_id == quiz_id, SessionParticipant.user_id == user_id)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None
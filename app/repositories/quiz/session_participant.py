from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SessionParticipant, User
from app.models.quiz.real_time_quiz.session_participant import ParticipantStatus


class SessionParticipantRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: dict) -> SessionParticipant:
        participant = SessionParticipant(**data)
        self.db.add(participant)
        await self.db.flush()
        return participant

    async def is_participant(self, session_id: int, user_id: int) -> bool:
        stmt = select(SessionParticipant.id).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_by_session_user(self, session_id: int, user_id: int) -> SessionParticipant | None:
        stmt = select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_session_id(self, session_id: int) -> list[SessionParticipant]:
        stmt = select(SessionParticipant).where(SessionParticipant.session_id == session_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_participant_list(self, session_id: int):
        stmt = (
            select(
                SessionParticipant.id.label("participant_id"),
                User.first_name,
                User.last_name,
                User.id.label("user_id"),
                SessionParticipant.nickname,
                User.profile_image,
                SessionParticipant.is_host,
                SessionParticipant.participant_status
            )
            .join(User, SessionParticipant.user_id == User.id)
            .where(SessionParticipant.session_id == session_id)
        )
        result = await self.db.execute(stmt)
        return result.mappings().all()

    async def disconnect_participant(self, participant_id: int) -> SessionParticipant | None:
        stmt = (
            update(SessionParticipant)
            .where(SessionParticipant.id == participant_id)
            .values(participant_status=ParticipantStatus.DISCONNECTED.value)
            .returning(SessionParticipant)
        )

        result = await self.db.execute(stmt)
        participant = result.scalar_one_or_none()

        if participant is not None:
            await self.db.flush()

        return participant

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis

from app.schemas.sessions.session_monitoring import ParticipantLiveStateSchema, ParticipantLiveStatus, ConnectionStatus


class SessionLiveStateService:
    def __init__(self, redis: Redis):
        self.redis = redis

    def _participant_key(self, session_id: int, participant_id: int) -> str:
        return f"quiz_session:{session_id}:participant:{participant_id}"

    def _participants_set_key(self, session_id: int) -> str:
        return f"quiz_session:{session_id}:participants"

    async def upsert_participant_state(
            self,
            session_id: int,
            state: ParticipantLiveStateSchema,
            ttl_seconds: int = 60 * 60 * 6,
    ) -> None:
        participant_key = self._participant_key(session_id, state.participant_id)
        participants_key = self._participants_set_key(session_id)

        pipe = self.redis.pipeline()
        await pipe.set(participant_key, state.model_dump_json(), ex=ttl_seconds)
        await pipe.sadd(participants_key, state.participant_id)
        await pipe.expire(participants_key, ttl_seconds)
        await pipe.execute()

    async def get_participant_state(
            self,
            session_id: int,
            participant_id: int,
    ) -> Optional[ParticipantLiveStateSchema]:
        raw = await self.redis.get(self._participant_key(session_id, participant_id))
        if not raw:
            return None
        return ParticipantLiveStateSchema.model_validate_json(raw)

    async def list_participants(
            self,
            session_id: int,
    ) -> list[ParticipantLiveStateSchema]:
        participant_ids = await self.redis.smembers(self._participants_set_key(session_id))
        if not participant_ids:
            return []

        keys = [
            self._participant_key(session_id, int(participant_id))
            for participant_id in participant_ids
        ]
        values = await self.redis.mget(keys)

        result: list[ParticipantLiveStateSchema] = []
        for raw in values:
            if raw:
                result.append(ParticipantLiveStateSchema.model_validate_json(raw))

        result.sort(key=lambda x: x.full_name.lower())
        return result

    async def create_or_get_initial_state(
            self,
            session_id: int,
            participant_id: int,
            user_id: int,
            full_name: str,
            nickname: str | None,
            profile_image: str | None,
            is_host: bool,
            total_questions: int,
            connection_status: ConnectionStatus = ConnectionStatus.OFFLINE,
    ) -> ParticipantLiveStateSchema:
        existing = await self.get_participant_state(session_id, participant_id)
        if existing:
            return existing

        now = datetime.now(timezone.utc)
        state = ParticipantLiveStateSchema(
            participant_id=participant_id,
            user_id=user_id,
            full_name=full_name,
            nickname=nickname,
            profile_image=profile_image,
            is_host=is_host,
            status=ParticipantLiveStatus.PREPARING,
            connection_status=connection_status,
            current_question=1 if total_questions > 0 else 0,
            answered_count=0,
            total_questions=total_questions,
            progress_percent=0,
            score=0,
            correct_count=0,
            wrong_count=0,
            started_at=now,
            finished_at=None,
            last_answer_at=None,
            last_seen_at=now,
        )
        await self.upsert_participant_state(session_id, state)
        return state

    async def mark_online(
            self,
            session_id: int,
            participant_id: int,
    ) -> ParticipantLiveStateSchema | None:
        state = await self.get_participant_state(session_id, participant_id)
        if not state:
            return None

        state.connection_status = ConnectionStatus.ONLINE
        state.last_seen_at = datetime.now(timezone.utc)
        if state.status in {ParticipantLiveStatus.WAITING, ParticipantLiveStatus.PREPARING}:
            state.status = ParticipantLiveStatus.IN_PROGRESS

        await self.upsert_participant_state(session_id, state)
        return state

    async def mark_offline(
            self,
            session_id: int,
            participant_id: int,
    ) -> ParticipantLiveStateSchema | None:
        state = await self.get_participant_state(session_id, participant_id)
        if not state:
            return None

        state.connection_status = ConnectionStatus.OFFLINE
        state.last_seen_at = datetime.now(timezone.utc)
        await self.upsert_participant_state(session_id, state)
        return state

    async def touch_heartbeat(
            self,
            session_id: int,
            participant_id: int,
    ) -> ParticipantLiveStateSchema | None:
        state = await self.get_participant_state(session_id, participant_id)
        if not state:
            return None

        state.connection_status = ConnectionStatus.ONLINE
        state.last_seen_at = datetime.now(timezone.utc)
        await self.upsert_participant_state(session_id, state)
        return state

    async def update_after_answer(
            self,
            session_id: int,
            participant_id: int,
            is_correct: bool,
            current_question_order: int,
            total_questions: int,
    ) -> ParticipantLiveStateSchema | None:
        state = await self.get_participant_state(session_id, participant_id)
        now = datetime.now(timezone.utc)

        if not state:
            return None

        # agar user shu savolga oldin javob bergan bo‘lsa, double count bo‘lib ketmasligi uchun
        # current_question_order answered_count dan katta bo‘lsa increment qilamiz
        if current_question_order > state.answered_count:
            state.answered_count = current_question_order

        state.current_question = min(current_question_order, total_questions)
        state.total_questions = total_questions
        state.status = ParticipantLiveStatus.IN_PROGRESS
        state.connection_status = ConnectionStatus.ONLINE
        state.last_answer_at = now
        state.last_seen_at = now
        state.question_answer_items[current_question_order] = is_correct
        state.correct_count = list(state.question_answer_items.values()).count(True)
        state.wrong_count = list(state.question_answer_items.values()).count(False)

        state.answered_count = len(state.question_answer_items.keys())

        if total_questions > 0:
            state.progress_percent = round((state.answered_count / total_questions) * 100, 2)

        state.score = float(state.correct_count)

        if state.answered_count >= total_questions:
            state.status = ParticipantLiveStatus.FINISHED
            state.finished_at = now
            state.current_question = total_questions

        await self.upsert_participant_state(session_id, state)
        return state


    async def change_current_question(
            self,
            session_id: int,
            participant_id: int,
            question_order_id: int,
    ) -> ParticipantLiveStateSchema | None:
        state = await self.get_participant_state(session_id, participant_id)
        if not state:
            return None

        state.current_question = question_order_id
        state.last_seen_at = datetime.now(timezone.utc)
        await self.upsert_participant_state(session_id, state)
        return state
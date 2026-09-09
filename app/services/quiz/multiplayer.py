from fastapi import HTTPException
from sqlalchemy import select

from app.models import AttemptAnswer
from app.models.quiz.real_time_quiz.quiz_session import SessionStatus, SessionType
from app.models.quiz.real_time_quiz.session_participant import ParticipantStatus
from app.services.quiz.quiz_session import QuizSessionService
from app.utils.datetime import utc_now


class MultiplayerQuizService(QuizSessionService):
    @staticmethod
    def participant_display_name(first_name, last_name, nickname=None):
        full_name = " ".join(
            part.strip()
            for part in (first_name, last_name)
            if part and part.strip()
        )
        return full_name or nickname or "Ishtirokchi"

    async def create_managed_session(
        self,
        *,
        quiz_id: int,
        duration_minutes: int,
        max_participants: int,
        user,
        commit: bool = True,
    ):
        quiz = await self.quiz_repo.get(quiz_id, user.id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Test topilmadi.")
        if not await self.quiz_repo.has_all_correct_options(quiz_id):
            raise HTTPException(
                status_code=400,
                detail="Ba'zi savollarda to'g'ri javob belgilanmagan.",
            )

        session = await self.session_repo.create(
            {
                "quiz_id": quiz_id,
                "host_id": user.id,
                "join_code": await self._generate_unique_join_code(),
                "status": SessionStatus.waiting,
                "session_type": SessionType.public,
                "duration_minutes": duration_minutes,
                "max_participants": max_participants,
            }
        )
        await self.participant_repo.create(
            {
                "session_id": session.id,
                "user_id": user.id,
                "nickname": user.username,
                "is_host": True,
                "participant_status": ParticipantStatus.READY,
            }
        )
        if commit:
            await self.db.commit()
            await self.db.refresh(session)
        return session

    async def lock_session(self, session_id: int):
        session = await self.session_repo.get_by_id_for_update(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Xona topilmadi.")
        return session

    async def join(self, session_id: int, user):
        session = await self.lock_session(session_id)
        participant = await self.participant_repo.get_by_session_user(session_id, user.id)
        if participant is None:
            participants = await self.participant_repo.get_all_by_session_id(session_id)
            if session.max_participants is not None and len(participants) >= session.max_participants:
                raise HTTPException(status_code=400, detail="Xona to'lgan.")
        return await self.join_quiz_session(session.join_code, user)

    async def participant(self, session_id: int, user_id: int):
        participant = await self.participant_repo.get_by_session_user(session_id, user_id)
        if participant is None:
            raise HTTPException(status_code=403, detail="Siz bu xona ishtirokchisi emassiz.")
        return participant

    async def start(self, session_id: int, user):
        session = await self.lock_session(session_id)
        if session.host_id != user.id:
            raise HTTPException(status_code=403, detail="Faqat xona egasi testni boshlashi mumkin.")
        if session.status != SessionStatus.waiting:
            raise HTTPException(status_code=400, detail="Xona kutish holatida emas.")

        participants = await self.participant_repo.get_all_by_session_id(session_id)
        if not participants:
            raise HTTPException(status_code=400, detail="Xonada ishtirokchilar yo'q.")
        await self.session_repo.start_session(session)
        for participant in participants:
            await self.attempt_repo.get_or_create(session_id, participant.id)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def finalize_quiz_session(self, session_id: int):
        session = await self.lock_session(session_id)
        if session.status != SessionStatus.running:
            return session
        if session.deadline_at is not None and utc_now() >= session.deadline_at:
            await self.finalize_session(session_id, "time_expired")
        elif await self.attempt_repo.all_session_attempts_finished(session_id):
            await self.finalize_session(session_id, "all_finished")
        return await self.session_repo.get_by_id(session_id)

    async def player_state(self, session_id: int, user_id: int):
        session = await self.finalize_quiz_session(session_id)
        participant = await self.participant(session_id, user_id)
        quiz = await self.quiz_repo.get_by_id(session.quiz_id)
        attempt = await self.attempt_repo.get_or_create(session_id, participant.id)
        answer_rows = await self.db.execute(
            select(AttemptAnswer.question_id, AttemptAnswer.selected_option).where(
                AttemptAnswer.attempt_id == attempt.id
            )
        )
        answers = {row.question_id: row.selected_option for row in answer_rows}
        result = None
        if session.status == SessionStatus.finished:
            result = await self._build_attempt_result(
                session_id,
                session.quiz_id,
                attempt,
                answered_before=session.deadline_at,
            )
        return {
            "session_id": session.id,
            "quiz_id": session.quiz_id,
            "quiz_name": quiz.title if quiz else None,
            "subject_name": quiz.subject if quiz else None,
            "status": session.status,
            "duration_minutes": session.duration_minutes,
            "started_at": session.started_at,
            "finished_at": session.deadline_at,
            "server_now": utc_now(),
            "answers": answers,
            "result": result,
        }

    async def questions(self, session_id: int, user_id: int):
        await self.participant(session_id, user_id)
        return await self.multiplayer_session_quiz_info(session_id, user_id)

    async def answer(self, session_id: int, user, payload):
        return await self.submit_answer(session_id, user, payload)

    async def finish(self, session_id: int, user_id: int):
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi.")
        return await self.finish_quiz(session_id, user)

    async def leaderboard(self, session):
        rows = await self.session_repo.get_session_leaderboard(session.id)
        participants = await self.participant_repo.get_all_by_session_id(session.id)
        nicknames = {participant.id: participant.nickname for participant in participants}
        leaderboard = []
        for row in rows:
            leaderboard.append(
                {
                    **dict(row),
                    "display_name": self.participant_display_name(
                        row["first_name"],
                        row["last_name"],
                        nicknames.get(row["participant_id"]),
                    ),
                    "correct_answers": int(row["score"] or 0),
                    "spend_time": int(row["spend_time_seconds"] or 0),
                }
            )
        return leaderboard

    @staticmethod
    async def now():
        return utc_now()

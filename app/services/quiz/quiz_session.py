import logging
import random
import string

from fastapi import Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.core.database.redis import get_redis_client
from app.models import User, NotificationActionType, NotificationType
from app.models.quiz.real_time_quiz.quiz_group import QuizSessionGroup
from app.models.quiz.real_time_quiz.quiz_session import SessionType, SessionStatus
from app.models.quiz.real_time_quiz.session_participant import ParticipantStatus
from app.repositories.account import UserRepository
from app.repositories.group.student_group_repository import StudentGroupRepository
from app.repositories.quiz.question_repo import QuestionRepository
from app.repositories.quiz.quiz_attempt_repo import QuizAttemptRepository
from app.repositories.quiz.quiz_repo import QuizRepository
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository
from app.repositories.quiz.session_participant import SessionParticipantRepository
from app.schemas.quiz.question import BASE_URL
from app.schemas.quiz.quiz_attempt import SubmitAnswerRequest, AnswerItem
from app.schemas.quiz.quiz_session import QuizSessionCreate, GroupQuizSessionCreate
from app.schemas.notification.notification import NotificationCreateSchema
from app.schemas.sessions.session_monitoring import ParticipantLiveStatus, ConnectionStatus
from app.schemas.statistic.teacher_statistics import WeakStudentsFilterParams
from app.services.notification.notification_service import NotificationService
from app.services.redis_service.realtime_events import publish_realtime_event
from app.services.redis_service.session_live import SessionLiveStateService
from app.utils.datetime import as_tashkent_datetime, utc_now
from app.websocket import session_ws_manager, session_monitoring_ws_manager


logger = logging.getLogger(__name__)
FINALIZATION_REASONS = {"all_finished", "time_expired", "host_finished"}


def generate_join_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


class QuizSessionService:
    def __init__(self, db: AsyncSession, redis_client: Redis = None):
        self.db = db
        self.user_repo = UserRepository(db)
        self.quiz_repo = QuizRepository(db)
        self.session_repo = QuizSessionRepository(db)
        self.question_repo = QuestionRepository(db)
        self.participant_repo = SessionParticipantRepository(db)
        self.attempt_repo = QuizAttemptRepository(db)
        self.group_repo = StudentGroupRepository(db)
        self.db = db
        self.redis = redis_client
        self.live_state_service = SessionLiveStateService(redis_client)

    async def _generate_unique_join_code(self) -> str:
        for _ in range(10):
            code = generate_join_code()
            session = await self.session_repo.get_by_join_code(code)
            if not session:
                return code
        raise HTTPException(status_code=500, detail="Could not generate unique join code")

    async def _build_attempt_result(
        self,
        session_id: int,
        quiz_id: int,
        attempt,
        answered_before=None,
    ):
        total_questions = await self.attempt_repo.get_total_questions(quiz_id)
        answered_questions = await self.attempt_repo.get_answer_count(attempt.id, answered_before)
        correct_answers = await self.attempt_repo.get_correct_answer_count(attempt.id, answered_before)
        wrong_answers = max(answered_questions - correct_answers, 0)
        topic_statistic = await self.attempt_repo.get_question_topic_statistic(
            quiz_id,
            attempt.id,
            answered_before,
        )
        attempt.score = correct_answers
        attempt.wrong_answers = wrong_answers
        attempt.total_questions = total_questions

        return {
            "session_id": session_id,
            "attempt_id": attempt.id,
            "total_questions": total_questions,
            "answered_questions": answered_questions,
            "correct_answers": correct_answers,
            "wrong_answers": wrong_answers,
            "score": attempt.score,
            "topic_statistic": topic_statistic,
            "finished": attempt.finished,
        }

    @staticmethod
    def _ordinal(rank: int) -> str:
        if 10 <= rank % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
        return f"{rank}{suffix}"

    async def finalize_session(self, session_id: int, reason: str):
        if reason not in FINALIZATION_REASONS:
            raise ValueError(f"Unsupported finalization reason: {reason}")

        session = await self.session_repo.get_by_id_for_update(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.status == SessionStatus.finished:
            return None
        if session.status != SessionStatus.running:
            return None

        now = utc_now()
        if reason == "time_expired" and session.deadline_at and now < session.deadline_at:
            return None
        attempt_finished_at = (
            session.deadline_at
            if reason == "time_expired" and session.deadline_at is not None
            else now
        )
        participants = await self.participant_repo.get_all_by_session_id(session_id)
        for participant in participants:
            attempt = await self.attempt_repo.get_or_create(session_id, participant.id)
            if not attempt.finished:
                attempt.finished = True
                attempt.finished_at = attempt_finished_at
            await self._build_attempt_result(
                session_id,
                session.quiz_id,
                attempt,
                answered_before=session.deadline_at if reason == "time_expired" else None,
            )

        session.status = SessionStatus.finished
        session.finished_at = now
        await self.db.flush()

        leaderboard = await self.session_repo.get_session_leaderboard(session_id)
        quiz = await self.quiz_repo.get_by_id(session.quiz_id)
        quiz_title = quiz.title if quiz else "Quiz"
        participants_count = len(leaderboard)
        notification_service = NotificationService(self.db, self.redis)
        notifications = []

        for rank, row in enumerate(leaderboard, start=1):
            score = int(row["score"] or 0)
            total_questions = int(row["total_questions"] or 0)
            wrong_answers = int(row["wrong_answers"] or 0)
            spend_time_seconds = int(row["spend_time_seconds"] or 0)
            payload = {
                "session_id": session.id,
                "quiz_id": session.quiz_id,
                "quiz_title": quiz_title,
                "rank": rank,
                "participants_count": participants_count,
                "score": score,
                "total_questions": total_questions,
                "score_percent": round(score * 100 / total_questions, 2) if total_questions else 0,
                "wrong_answers": wrong_answers,
                "spend_time_seconds": spend_time_seconds,
            }
            notification = await notification_service.create_notification(
                NotificationCreateSchema(
                    recipient_id=row["user_id"],
                    sender_id=session.host_id,
                    type=NotificationType.COMPETITION_RESULT,
                    action_type=NotificationActionType.OPEN_RESULT,
                    title="Competition result",
                    message=f'You finished {self._ordinal(rank)} in "{quiz_title}".',
                    payload=payload,
                ),
                commit=False,
                deliver=False,
            )
            notifications.append(notification)

        await self.db.commit()

        for notification in notifications:
            try:
                await notification_service.publish_notification(notification)
            except Exception:
                logger.exception("Failed to publish competition notification %s", notification.id)

        event_payload = {
            "session_id": session.id,
            "quiz_id": session.quiz_id,
            "reason": reason,
            "finished_at": session.finished_at.isoformat(),
        }
        if self.redis is not None:
            try:
                await publish_realtime_event(
                    self.redis,
                    {
                        "target": "session",
                        "session_id": session.id,
                        "event": "session_finished",
                        "payload": event_payload,
                    },
                )
            except Exception:
                logger.exception("Failed to publish session finalization event %s", session.id)
        else:
            await session_ws_manager.broadcast(session.id, "session_finished", event_payload)

        return leaderboard

    async def create(self, quiz_session_data: QuizSessionCreate, user: User,
                     session_type: SessionType = SessionType.individual):
        quiz = await self.quiz_repo.get(quiz_session_data.quiz_id, user.id)
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")

        if not await self.quiz_repo.has_all_correct_options(quiz_session_data.quiz_id):
            raise HTTPException(status_code=404, detail="Ba'zi savollarda to‘g‘ri javob belgilanmagan.")

        join_code = await self._generate_unique_join_code()

        quiz_session = await self.session_repo.create(
            {
                **quiz_session_data.model_dump(),
                "host_id": user.id,
                "join_code": join_code,
                "status": SessionStatus.waiting,
                "session_type": session_type,
            }
        )

        # Host is always the first participant.
        current_participant = await self.participant_repo.create(
            {
                "session_id": quiz_session.id,
                "nickname": user.username,
                "user_id": user.id,
                "is_host": True,
                "participant_status": ParticipantStatus.READY,
            }
        )

        await self.db.commit()
        await self.db.refresh(quiz_session)
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
        await self.live_state_service.create_or_get_initial_state(
            session_id=quiz_session.id,
            participant_id=current_participant.id,
            user_id=user.id,
            full_name=full_name,
            nickname=user.username,
            profile_image=f"{BASE_URL}/{user.profile_image}" if user.profile_image else None,
            is_host=True,
            total_questions=await self.quiz_repo.quiz_question_count(quiz_session.quiz_id),
            connection_status=ConnectionStatus.OFFLINE,
            status=ParticipantLiveStatus.READY,
        )
        result = {
            "session_id": quiz_session.id,
            "quiz_id": quiz_session.quiz_id,
            "host_id": quiz_session.host_id,
            "join_code": quiz_session.join_code,
            "status": quiz_session.status,
            "duration_minutes": quiz_session.duration_minutes,
            "questions_count": await self.quiz_repo.quiz_question_count(quiz_session.quiz_id),
            "started_at": quiz_session.started_at,
            "deadline_at": quiz_session.deadline_at,
            "finished_at": quiz_session.finished_at,
            "session_type": quiz_session.session_type,
            "current_participant_id":current_participant.id
        }
        return result

    async def running_sessions(self, host_id: int):
        sessions = await self.session_repo.get_running_sessions_by_host(host_id)
        return sessions

    async def finish_quiz_by_host(self, session_id: int, user_id: int):
        current_session = await self.session_repo.get_by_id(session_id)
        if not current_session:
            raise HTTPException(status_code=404, detail="Session not found")

        if current_session.host_id != user_id:
            raise HTTPException(status_code=403, detail="Faqat host foydalanuvchi sessiyani tugatishi mumkin!")

        await self.finalize_session(session_id, "host_finished")

    async def join_quiz_session(self, session_code: str, user: User):
        quiz_session = await self.session_repo.get_by_join_code(session_code)
        if not quiz_session:
            raise HTTPException(status_code=404, detail="Invalid session code")

        if quiz_session.status != "waiting":
            raise HTTPException(status_code=400, detail="Session already started")

        if quiz_session.session_type == SessionType.group:
            if not await self.session_repo.is_user_in_session_groups(quiz_session.id, user.id):
                raise HTTPException(status_code=403,
                                    detail="Bu faqat belgilangan guruh azolari uchun mo'ljallangan test!")

        participant = await self.participant_repo.get_by_session_user(quiz_session.id, user.id)
        if not participant:
            participant = await self.participant_repo.create(
                {
                    "session_id": quiz_session.id,
                    "nickname": user.username,
                    "user_id": user.id,
                    "is_host": False,
                    "joined_at": utc_now(),
                    "participant_status": ParticipantStatus.READY,
                }
            )
            await self.db.commit()
            await session_ws_manager.broadcast(
                session_id=quiz_session.id,
                event="participant_joined",
                payload={
                    "participant_id": participant.id,
                    "user_id": user.id,
                    "is_host": participant.is_host,
                    "nickname": user.username,
                    "profile_image": f"{BASE_URL}/{user.profile_image}" if user.profile_image else None,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "joined_at": participant.joined_at.isoformat() if participant.joined_at else None,
                    "status": ParticipantStatus.READY.value,
                    "participants_online": session_ws_manager.count(quiz_session.id),
                },
            )
        else:
            await self.participant_repo.mark_ready(participant)
            await self.db.commit()

        await session_ws_manager.broadcast(
            session_id=quiz_session.id,
            event="participant_reconnected",
            payload={
                "user_id": user.id,
                "status": ParticipantStatus.READY.value,
                "participants_online": session_ws_manager.count(quiz_session.id)},
        )
        return quiz_session

    async def get_participant(self, session_id: int, user: User):
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        is_participant = await self.participant_repo.is_participant(session_id, user.id)
        if not is_participant and session.host_id != user.id:
            raise HTTPException(status_code=403, detail="You are not a participant of this session")

        return await self.participant_repo.get_participant_list(session_id)

    async def start_session(self, session_id: int, user: User):
        quiz_session = await self.session_repo.get_for_host(session_id, user.id)
        if not quiz_session:
            raise HTTPException(status_code=404, detail="Session not found or access denied")

        if quiz_session.host_id != user.id:
            raise HTTPException(status_code=403, detail="Only host can start the session")

        if quiz_session.status != "waiting":
            raise HTTPException(status_code=400, detail="Session is not in waiting state")

        participants = await self.participant_repo.get_all_by_session_id(session_id)
        if not participants:
            raise HTTPException(status_code=400, detail="No participants in session")

        await self.session_repo.start_session(quiz_session)

        attempts_created = 0
        for participant in participants:
            user = await self.user_repo.get_by_id(participant.user_id)
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
            total_questions = await self.quiz_repo.quiz_question_count(quiz_session.quiz_id)
            await self.live_state_service.create_or_get_initial_state(
                session_id=session_id,
                participant_id=participant.id,
                user_id=user.id,
                full_name=full_name,
                nickname=user.username,
                profile_image=f"{BASE_URL}/{user.profile_image}" if user.profile_image else None,
                is_host=participant.is_host,
                total_questions=total_questions,
                connection_status=ConnectionStatus.OFFLINE
            )

            attempt = await self.attempt_repo.get_by_session_participant(session_id, participant.id)
            if not attempt:
                await self.attempt_repo.create(session_id=session_id, participant_id=participant.id)
                attempts_created += 1

        await self.db.commit()
        await self.db.refresh(quiz_session)
        try:
            from app.services.quiz.tasks.session_tasks import finalize_quiz_session

            finalize_quiz_session.apply_async(
                args=[quiz_session.id, "time_expired"],
                eta=quiz_session.deadline_at,
            )
        except Exception:
            logger.exception("Could not schedule deadline task for session %s", quiz_session.id)
        await session_ws_manager.broadcast(
            session_id=session_id,
            event="session_started",
            payload={
                "session_id": quiz_session.id,
                "quiz_id": quiz_session.quiz_id,
                "started_at": quiz_session.started_at.isoformat(),
                "deadline_at": quiz_session.deadline_at.isoformat(),
                "finished_at": None,
            },
        )
        return {
            "id": quiz_session.id,
            "status": quiz_session.status,
            "started_at": quiz_session.started_at,
            "deadline_at": quiz_session.deadline_at,
            "finished_at": quiz_session.finished_at,
            "participants_count": len(participants),
            "attempts_created": attempts_created,
        }

    async def submit_answer(self, session_id: int, user: User, payload: SubmitAnswerRequest):
        session = await self.session_repo.get_by_id_for_update(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status != "running":
            raise HTTPException(status_code=400, detail="Session is not running")
        if session.deadline_at and utc_now() >= session.deadline_at:
            await self.db.rollback()
            await self.finalize_session(session_id, "time_expired")
            raise HTTPException(status_code=400, detail="Quiz deadline has passed")

        participant = await self.participant_repo.get_by_session_user(session_id, user.id)
        if not participant:
            raise HTTPException(status_code=403, detail="User is not a participant of this session")

        in_quiz = await self.attempt_repo.is_question_in_quiz(
            question_id=payload.question_id,
            quiz_id=session.quiz_id,
        )
        if not in_quiz:
            raise HTTPException(status_code=400, detail="Question does not belong to this quiz session")

        attempt = await self.attempt_repo.get_or_create(
            session_id=session_id,
            participant_id=participant.id,
        )

        if attempt.finished:
            raise HTTPException(status_code=400, detail="Session already finished")

        selected_option = await self.attempt_repo.get_option_for_question(
            question_id=payload.question_id,
            selected_option=payload.selected_option,
        )
        if not selected_option:
            raise HTTPException(status_code=400, detail="Invalid option for question.")

        answer = await self.attempt_repo.upsert_answer(
            attempt_id=attempt.id,
            question_id=payload.question_id,
            selected_option=payload.selected_option,
            is_correct=selected_option.is_correct,
        )

        await self.db.commit()

        return {
            "question_id": answer.question_id,
            "selected_option": answer.selected_option,
        }

    async def finish_quiz(self, session_id: int, user: User):
        session = await self.session_repo.get_by_id_for_update(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        participant = await self.participant_repo.get_by_session_user(session_id, user.id)
        if not participant:
            raise HTTPException(status_code=403, detail="User is not a participant of this session")

        attempt = await self.attempt_repo.get_or_create(
            session_id=session_id,
            participant_id=participant.id,
        )
        if session.status == SessionStatus.finished:
            return await self._build_attempt_result(session_id, session.quiz_id, attempt)
        if session.deadline_at and utc_now() >= session.deadline_at:
            quiz_id = session.quiz_id
            deadline_at = session.deadline_at
            participant_id = participant.id
            await self.db.rollback()
            await self.finalize_session(session_id, "time_expired")
            attempt = await self.attempt_repo.get_by_session_participant(session_id, participant_id)
            return await self._build_attempt_result(
                session_id,
                quiz_id,
                attempt,
                answered_before=deadline_at,
            )

        attempt.finished = True
        now = utc_now()
        attempt.finished_at = now
        result = await self._build_attempt_result(
            session_id=session_id,
            quiz_id=session.quiz_id,
            attempt=attempt,
        )
        result["finished"] = True

        await self.db.flush()
        if await self.attempt_repo.all_session_attempts_finished(session_id):
            await self.finalize_session(session_id, "all_finished")
        else:
            await self.db.commit()
        return result

    async def get_all_participant_results(self, session_id: int, user: User):
        session = await self.session_repo.get_for_host(session_id, user.id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or access denied")

        participants = await self.participant_repo.get_all_by_session_id(session_id)
        participant_rows = await self.participant_repo.get_participant_list(session_id, pagination=False)
        rows_by_id = {int(row["participant_id"]): row for row in participant_rows}

        results = []
        for participant in participants:
            attempt = await self.attempt_repo.get_or_create(
                session_id=session_id,
                participant_id=participant.id,
            )
            stats = await self._build_attempt_result(
                session_id=session_id,
                quiz_id=session.quiz_id,
                attempt=attempt,
            )

            row = rows_by_id.get(participant.id, {})
            results.append(
                {
                    "participant_id": participant.id,
                    "user_id": participant.user_id,
                    "nickname": participant.nickname,
                    "is_host": participant.is_host,
                    "first_name": row.get("first_name"),
                    "last_name": row.get("last_name"),
                    "total_questions": stats["total_questions"],
                    "answered_questions": stats["answered_questions"],
                    "correct_answers": stats["correct_answers"],
                    "wrong_answers": stats["wrong_answers"],
                    "score": attempt.score,
                    "finished": attempt.finished,
                }
            )

        await self.db.commit()

        results.sort(
            key=lambda x: (x["score"], -x["wrong_answers"], -x["answered_questions"]),
            reverse=True,
        )
        return results

    async def topic_statistic(self, session_id: int, user: User):
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        participant = await self.participant_repo.get_by_session_user(session_id, user.id)
        if not participant:
            raise HTTPException(status_code=403, detail="User is not a participant of this session")

        attempt = await self.attempt_repo.get_or_create(
            session_id=session_id,
            participant_id=participant.id,
        )

        topic_rows = await self.attempt_repo.get_question_topic_statistic(
            quiz_id=session.quiz_id,
            attempt_id=attempt.id,
        )

        formatted = []
        for row in topic_rows:
            topic_name = row["topic_name"] or "Unknown"
            formatted.append(
                {
                    topic_name: {
                        "total_topic_quession": int(row["total_topic_question"]),
                        "correct_answer": int(row["correct_answer"]),
                    }
                }
            )

        return formatted

    async def start_single_player_quiz(self, quiz_id: int, user: User, duration_minute: int = 30):
        # create session
        quiz_session = await self.session_repo.create(
            {
                "quiz_id": quiz_id,
                "host_id": user.id,
                "join_code": await self._generate_unique_join_code(),
                "status": "waiting",
                "duration_minutes": duration_minute,
            }
        )
        # create participant
        await self.participant_repo.create(
            {
                "session_id": quiz_session.id,
                "nickname": user.username,
                "user_id": user.id,
                "is_host": True,
            }
        )
        # start session
        await self.session_repo.start_session(quiz_session)

        await self.db.commit()
        await self.db.refresh(quiz_session)
        questions = await self.question_repo.list_with_details(quiz_id, user.id)
        return {
            "session_id": quiz_session.id,
            "quiz_id": quiz_id,
            "questions_count": len(questions),
            "status": quiz_session.status,
            "started_at": quiz_session.started_at,
            "deadline_at": quiz_session.deadline_at,
            "finished_at": quiz_session.finished_at,
            "questions": questions,
        }

    async def multiplayer_session_quiz_info(self, session_id: int, user_id: int):
        is_session_user = await self.participant_repo.get_by_session_user(session_id, user_id)
        if not is_session_user:
            raise HTTPException(status_code=403, detail="User is not a participant of this session")

        quiz_session = await self.session_repo.get_single_player_session(session_id)
        if quiz_session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        questions = await self.question_repo.list_quiz_session_questions(quiz_id=quiz_session.quiz_id)
        return {
            "session_id": quiz_session.id,
            "quiz_id": quiz_session.quiz_id,
            "questions_count": len(questions),
            "status": quiz_session.status,
            "started_at": quiz_session.started_at,
            "deadline_at": quiz_session.deadline_at,
            "finished_at": quiz_session.finished_at,
            "questions": questions,
        }

    async def get_single_player_quiz_info(self, session_id: int, user_id: int, is_question=True, status="running"):
        quiz_session = await self.session_repo.get_single_player_session(session_id, host_id=None)
        if not quiz_session:
            raise HTTPException(status_code=404, detail="Session not found")

        questions = await self.question_repo.list_with_details(quiz_session.quiz_id, user_id)
        current_participant = await self.participant_repo.get_by_session_user(session_id, user_id)
        result = {
            "session_id": quiz_session.id,
            "quiz_id": quiz_session.quiz_id,
            "quiz_name": quiz_session.quiz_name,
            "subject_name": quiz_session.subject_name,
            "duration_minutes": quiz_session.duration_minutes,
            "join_code": quiz_session.join_code,
            "host_id": quiz_session.host_id,
            "session_type": quiz_session.session_type,
            "questions_count": len(questions),
            "status": quiz_session.status,
            "started_at": quiz_session.started_at,
            "deadline_at": quiz_session.deadline_at,
            "finished_at": quiz_session.finished_at,
            "current_participant_id": current_participant.id if current_participant else None,
        }
        if is_question:
            result["questions"] = questions
        return result

    async def finish_single_player_quiz(
            self,
            session_id: int,
            user_id: int,
            answers: list[AnswerItem]
    ):
        quiz_session = await self.session_repo.player_session(session_id)
        if not quiz_session:
            raise HTTPException(status_code=404, detail="Session not found")

        participant = await self.participant_repo.get_by_session_user(session_id, user_id)
        if not participant:
            raise HTTPException(status_code=403, detail="User is not a participant of this session")

        attempt = await self.attempt_repo.get_or_create(
            session_id=session_id,
            participant_id=participant.id,

        )

        for answer in answers:
            selected_option = await self.attempt_repo.get_option_for_question(
                question_id=answer.question_id,
                selected_option=answer.selected_option,
            )
            if selected_option:
                await self.attempt_repo.upsert_answer(
                    attempt_id=attempt.id,
                    question_id=answer.question_id,
                    selected_option=answer.selected_option,
                    is_correct=selected_option.is_correct,
                )

        now = utc_now()

        attempt.finished = True
        attempt.finished_at = now
        # quiz_session.status = "finished"
        quiz_session.finished_at = now

        await self.db.flush()

        result = await self._build_attempt_result(
            session_id=session_id,
            quiz_id=quiz_session.quiz_id,
            attempt=attempt,
        )
        result["finished"] = True

        # spend_time return in seconds
        if quiz_session.started_at and quiz_session.finished_at:
            started_at = as_tashkent_datetime(quiz_session.started_at)
            finished_at = as_tashkent_datetime(quiz_session.finished_at)
            result["spend_time"] = int(
                (finished_at - started_at).total_seconds()
            )
        else:
            result["spend_time"] = 0

        await self.db.commit()
        return result

    async def get_finished_single_player_result(self, session_id: int, user_id: int):
        quiz_session = await self.session_repo.player_session(session_id)
        if not quiz_session:
            raise HTTPException(status_code=404, detail="Session not found")
        if quiz_session.session_type != SessionType.individual:
            raise HTTPException(status_code=400, detail="Session is not single-player")

        participant = await self.participant_repo.get_by_session_user(session_id, user_id)
        if not participant:
            raise HTTPException(status_code=403, detail="User is not a participant of this session")

        attempt = await self.attempt_repo.get_by_session_participant(session_id, participant.id)
        if not attempt or not attempt.finished:
            raise HTTPException(status_code=409, detail="Quiz attempt is not finished")

        result = await self._build_attempt_result(session_id, quiz_session.quiz_id, attempt)
        quiz = await self.quiz_repo.get_by_id(quiz_session.quiz_id)
        spend_time = 0
        if quiz_session.started_at and attempt.finished_at:
            spend_time = max(
                0,
                int(
                    (
                        as_tashkent_datetime(attempt.finished_at)
                        - as_tashkent_datetime(quiz_session.started_at)
                    ).total_seconds()
                ),
            )

        total_questions = result["total_questions"]
        return {
            **result,
            "quiz_title": quiz.title if quiz else "Test",
            "subject": quiz.subject if quiz else None,
            "percentage": round(result["correct_answers"] * 100 / total_questions, 2)
            if total_questions
            else 0,
            "spend_time": spend_time,
        }

    async def single_player_error_analysis(self, session_id: int, user_id: int):
        quiz_session = await self.session_repo.get_session_questions_with_answers(session_id, user_id)
        if not quiz_session:
            raise HTTPException(status_code=404, detail="Session not found")
        return quiz_session

    async def personal_quiz_session_history(self, user_id: int, search: str):
        session_history = await self.session_repo.get_personal_quiz_session_history(user_id, search)
        return session_history

    async def session_participant_rank_list(self, session_id: int, user_id: int):
        rank_list = await self.session_repo.get_session_participant_rank_list(session_id, user_id)
        return rank_list

    async def disconnect_participant(self, session_id, participant_id: int) -> None:
        updated_participant = await self.participant_repo.disconnect_participant(participant_id)
        await self.db.commit()
        await session_ws_manager.broadcast(
            session_id=session_id,
            event="participant_disconnected",
            payload={
                "user_id": updated_participant.user_id,
                "status": ParticipantStatus.DISCONNECTED.value,
            },
        )

    async def groups_add_to_quiz(self, session_id: int, user_id: int, group_ids: list[int]):
        quiz_session = await self.session_repo.get_for_host(session_id, user_id)
        if quiz_session is None or quiz_session.status != 'waiting':
            raise HTTPException(status_code=404, detail="Session not found")

        for group_id in group_ids:
            self.db.add(
                QuizSessionGroup(
                    group_id=group_id,
                    session_id=session_id
                )
            )

    async def create_group_session(self, quiz_session_data: GroupQuizSessionCreate, user: User):
        quiz = await self.quiz_repo.get(quiz_session_data.quiz_id, user.id)
        if not quiz:
            raise HTTPException(status_code=404, detail="Test topilmadi!s")

        if not await self.quiz_repo.has_all_correct_options(quiz_session_data.quiz_id):
            raise HTTPException(status_code=404, detail="Ba'zi savollarda to‘g‘ri javob belgilanmagan.")

        join_code = await self._generate_unique_join_code()
        quiz_session = await self.session_repo.create(
            {
                "quiz_id": quiz.id,
                "max_participants": quiz_session_data.max_participants,
                "duration_minutes": quiz_session_data.duration_minutes,
                "host_id": user.id,
                "join_code": join_code,
                "status": SessionStatus.waiting,
                "session_type": quiz_session_data.session_type,
            }
        )

        if quiz_session_data.session_type == SessionType.group and quiz_session_data.group_ids:
            """
             if group ids are provided, validate that the groups belong to the teacher and add them to the quiz session
             if group ids are not provided, the quiz session will be open to all students of the teacher
            """
            validate_group_ids = await self.group_repo.validate_groups(teacher_id=user.id,
                                                                       group_ids=quiz_session_data.group_ids)
            if validate_group_ids != quiz_session_data.group_ids:
                raise HTTPException(status_code=400, detail="Group ids do not match")

            await self.groups_add_to_quiz(session_id=quiz_session.id, user_id=user.id,
                                          group_ids=quiz_session_data.group_ids)

        await self.db.commit()
        await self.db.refresh(quiz_session)

        if quiz_session_data.session_type == SessionType.group and quiz_session_data.group_ids:
            notification_ser = NotificationService(self.db, self.redis)
            group_members = await self.group_repo.student_list_by_group_ids(quiz_session_data.group_ids)
            await notification_ser.send_notification_to_group_by_teacher(
                current_user=user,
                session_code=quiz_session.join_code,
                user_ids=group_members
            )

        result = {
            "session_id": quiz_session.id,
            "quiz_id": quiz_session.quiz_id,
            "host_id": quiz_session.host_id,
            "join_code": quiz_session.join_code,
            "status": quiz_session.status,
            "duration_minutes": quiz_session.duration_minutes,
            "questions_count": await self.quiz_repo.quiz_question_count(quiz_session.quiz_id),
            "started_at": quiz_session.started_at,
            "deadline_at": quiz_session.deadline_at,
            "finished_at": quiz_session.finished_at,
            "session_type": quiz_session.session_type,
        }
        return result

    async def submit_answer_v2(self, session_id: int, user: User, payload: SubmitAnswerRequest):
        session = await self.session_repo.get_by_id_for_update(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status != "running":
            raise HTTPException(status_code=400, detail="Session is not running")
        if session.deadline_at and utc_now() >= session.deadline_at:
            await self.db.rollback()
            await self.finalize_session(session_id, "time_expired")
            raise HTTPException(status_code=400, detail="Quiz deadline has passed")

        participant = await self.participant_repo.get_by_session_user(session_id, user.id)
        if not participant:
            raise HTTPException(status_code=403, detail="User is not a participant of this session")

        in_quiz = await self.attempt_repo.is_question_in_quiz(
            question_id=payload.question_id,
            quiz_id=session.quiz_id,
        )
        if not in_quiz:
            raise HTTPException(status_code=400, detail="Question does not belong to this quiz session")

        attempt = await self.attempt_repo.get_or_create(
            session_id=session_id,
            participant_id=participant.id,
        )

        if attempt.finished:
            raise HTTPException(status_code=400, detail="Session already finished")

        selected_option = await self.attempt_repo.get_option_for_question(
            question_id=payload.question_id,
            selected_option=payload.selected_option,
        )
        if not selected_option:
            raise HTTPException(status_code=400, detail="Invalid option for question.")

        question_order = await self.attempt_repo.get_question_order_in_quiz(
            quiz_id=session.quiz_id,
            question_id=payload.question_id,
        )
        if question_order is None:
            raise HTTPException(status_code=400, detail="Question order not found")

        total_questions = await self.attempt_repo.get_total_questions_count(quiz_id=session.quiz_id)

        answer = await self.attempt_repo.upsert_answer(
            attempt_id=attempt.id,
            question_id=payload.question_id,
            selected_option=payload.selected_option,
            is_correct=selected_option.is_correct,
        )
        await self.db.commit()

        # Redis state yangilash
        live_state = await self.live_state_service.get_participant_state(session_id, participant.id)

        if not live_state:
            full_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username
            await self.live_state_service.create_or_get_initial_state(
                session_id=session_id,
                participant_id=participant.id,
                user_id=user.id,
                full_name=full_name,
                nickname=user.username,
                profile_image=user.profile_image,
                is_host=participant.is_host,
                total_questions=total_questions,
            )

        updated_state = await self.live_state_service.update_after_answer(
            session_id=session_id,
            participant_id=participant.id,
            is_correct=selected_option.is_correct,
            current_question_order=question_order,
            total_questions=total_questions,
        )

        if updated_state:
            await session_monitoring_ws_manager.broadcast(
                session_id=session_id,
                event="participant_monitoring_updated",
                payload={
                    "session_id": session_id,
                    "participant": updated_state.model_dump(mode="json"),
                },
            )

            if updated_state.status == ParticipantLiveStatus.FINISHED:
                await session_monitoring_ws_manager.broadcast(
                    session_id=session_id,
                    event="participant_finished",
                    payload={
                        "session_id": session_id,
                        "participant": updated_state.model_dump(mode="json"),
                    },
                )

        return {
            "question_id": answer.question_id,
            "selected_option": answer.selected_option,
        }

    async def change_current_question(self, session_id: int, participant_id: int, question_order_id: int):
        updated_state = await self.live_state_service.change_current_question(
            session_id=session_id,
            participant_id=participant_id,
            question_order_id=question_order_id
        )

        if updated_state:
            await session_monitoring_ws_manager.broadcast(
                session_id=session_id,
                event="participant_monitoring_updated",
                payload={
                    "session_id": session_id,
                    "participant": updated_state.model_dump(mode="json"),
                },
            )

    async def teacher_session_results(self, teacher_id: int):
        return await self.session_repo.teacher_session_results(teacher_id)

    async def teacher_session_result_details(self, session_id: int, host_id: int, ):
        return await self.session_repo.get_teacher_session_results_detail(
            session_id=session_id,
            host_id=host_id,
        )

    async def get_session_question_accuracy(
            self,
            session_id: int,
            host_id: int,
    ):
        return await self.session_repo.get_session_question_accuracy(
            session_id=session_id,
            host_id=host_id,
        )

    async def student_session_result_details(self, session_id: int, group_id: int, member_id: int):
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.session_type != SessionType.group:
            raise HTTPException(status_code=404, detail="Session not found")

        is_member = await self.group_repo.is_group_member(group_id, member_id)
        if not is_member:
            raise HTTPException(status_code=404, detail="Member not found")

        return await self.session_repo.get_teacher_session_results_detail(
            session_id=session_id,
            host_id=session.host_id,
        )

    async def student_session_question_accuracy(self, session_id: int, group_id, member_id: int):
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.session_type != SessionType.group:
            raise HTTPException(status_code=404, detail="Session not found")

        is_member = await self.group_repo.is_group_member(group_id, member_id)
        if not is_member:
            raise HTTPException(status_code=404, detail="Member not found")

        return await self.session_repo.get_session_question_accuracy(
            session_id=session_id,
            host_id=session.host_id,
        )

    async def student_session_participant_rank_list(self, session_id: int, group_id, member_id: int):
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.session_type != SessionType.group:
            raise HTTPException(status_code=404, detail="Session not found")

        is_member = await self.group_repo.is_group_member(group_id, member_id)
        if not is_member:
            raise HTTPException(status_code=404, detail="Member not found")
        rank_list = await self.session_repo.get_session_participant_rank_list(session_id, session.host_id)
        return rank_list

    async def get_teacher_overview_cards(self, teacher_id: int):
        return await self.session_repo.teacher_overview_cards(teacher_id)

    async def get_teacher_activity_chart(self, teacher_id: int):
        return await self.session_repo.teacher_activity_chart(teacher_id)

    async def get_teacher_analytics_overview(self, teacher_id: int):
        return await self.session_repo.teacher_analytics_overview(teacher_id)

    async def get_teacher_group_results(self, teacher_id: int):
        return await self.session_repo.teacher_group_results(teacher_id)

    async def get_teacher_weak_topics(self, teacher_id: int):
        return await self.session_repo.teacher_weak_topics(teacher_id)

    async def get_teacher_weak_students(self, teacher_id: int, filters: WeakStudentsFilterParams, ):
        return await self.session_repo.teacher_weak_students(teacher_id, filters)


def get_quiz_session_service(db: AsyncSession = Depends(get_db),
                             redis_client: Redis = Depends(get_redis_client)) -> QuizSessionService:
    return QuizSessionService(db, redis_client)

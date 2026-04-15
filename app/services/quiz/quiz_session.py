import random
import string
from datetime import datetime
from fastapi import Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.core.database.redis import get_redis_client
from app.models import User
from app.models.quiz.real_time_quiz.quiz_group import QuizSessionGroup
from app.models.quiz.real_time_quiz.quiz_session import SessionType, SessionStatus
from app.models.quiz.real_time_quiz.session_participant import ParticipantStatus
from app.repositories.account import UserRepository
from app.repositories.group.student_group_repository import StudentGroupRepository
from app.repositories.quiz.question_repo import QuestionRepository
from app.repositories.quiz.quiz_attempt_repo import QuizAttemptRepository
from app.repositories.quiz.quiz_repo import QuizRepository
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository, UZT
from app.repositories.quiz.session_participant import SessionParticipantRepository
from app.schemas.quiz.question import BASE_URL
from app.schemas.quiz.quiz_attempt import SubmitAnswerRequest, AnswerItem
from app.schemas.quiz.quiz_session import QuizSessionCreate, GroupQuizSessionCreate
from app.schemas.sessions.session_monitoring import ParticipantLiveStatus, ConnectionStatus
from app.schemas.statistic.teacher_statistics import WeakStudentsFilterParams
from app.services.notification.notification_service import get_notification_service
from app.services.redis_service.session_live import SessionLiveStateService
from app.websocket import session_ws_manager, session_monitoring_ws_manager


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

    async def _build_attempt_result(self, session_id: int, quiz_id: int, attempt):
        total_questions = await self.attempt_repo.get_total_questions(quiz_id)
        answered_questions = await self.attempt_repo.get_answer_count(attempt.id)
        correct_answers = await self.attempt_repo.get_correct_answer_count(attempt.id)
        wrong_answers = max(answered_questions - correct_answers, 0)
        topic_statistic = await self.attempt_repo.get_question_topic_statistic(quiz_id, attempt.id)
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
        await self.participant_repo.create(
            {
                "session_id": quiz_session.id,
                "nickname": user.username,
                "user_id": user.id,
                "is_host": True,
            }
        )

        await self.db.commit()
        await self.db.refresh(quiz_session)
        result = {
            "session_id": quiz_session.id,
            "quiz_id": quiz_session.quiz_id,
            "host_id": quiz_session.host_id,
            "join_code": quiz_session.join_code,
            "status": quiz_session.status,
            "duration_minutes": quiz_session.duration_minutes,
            "questions_count": 30,  # TODO: get real question count for quiz
            "started_at": quiz_session.started_at,
            "finished_at": quiz_session.finished_at,
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

        await self.session_repo.finish_session(current_session)
        await self.db.commit()
        await session_ws_manager.broadcast(
            session_id=session_id,
            event="session_finished",
            payload={
                "message":"Sessiya host tomonidan tugatildi!",
            }
        )
        await self.db.refresh(current_session)



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

        is_participant = await self.participant_repo.is_participant(quiz_session.id, user.id)
        if not is_participant:
            now = datetime.now(UZT).replace(tzinfo=None)
            joined_at = now
            is_participant = await self.participant_repo.create(
                {
                    "session_id": quiz_session.id,
                    "nickname": user.username,
                    "user_id": user.id,
                    "is_host": False,
                    "joined_at":joined_at
                }
            )
            await self.db.commit()
            await session_ws_manager.broadcast(
                session_id=quiz_session.id,
                event="participant_joined",
                payload={
                    "participant_id": is_participant.id,
                    "user_id": user.id,
                    "is_host": is_participant.is_host,
                    "nickname": user.username,
                    "profile_image": f"{BASE_URL}/{user.profile_image}" if user.profile_image else None,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "joined_at": is_participant.joined_at.isoformat() if is_participant.joined_at else None,
                    "status": ParticipantStatus.PREPARING.value,
                    "participants_online": session_ws_manager.count(quiz_session.id)},
            )
        await session_ws_manager.broadcast(
            session_id=quiz_session.id,
            event="participant_reconnected",
            payload={
                "user_id": user.id,
                "status": ParticipantStatus.PREPARING.value,
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
            total_questions = await self.quiz_repo.quiz_question_count(quiz_session.id)
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
        await session_ws_manager.broadcast(
            session_id=session_id,
            event="session_started",
            payload={
                "session_id": quiz_session.id,
                "quiz_id": quiz_session.quiz_id,
                "started_at": quiz_session.started_at.isoformat(),
                "finished_at": quiz_session.finished_at.isoformat(),
            },
        )
        return {
            "id": quiz_session.id,
            "status": quiz_session.status,
            "started_at": quiz_session.started_at,
            "finished_at": quiz_session.finished_at,
            "participants_count": len(participants),
            "attempts_created": attempts_created,
        }

    async def submit_answer(self, session_id: int, user: User, payload: SubmitAnswerRequest):
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status != "running":
            raise HTTPException(status_code=400, detail="Session is not running")

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

        attempt.finished = True
        now = datetime.now(UZT).replace(tzinfo=None)
        attempt.finished_at = now
        result = await self._build_attempt_result(
            session_id=session_id,
            quiz_id=session.quiz_id,
            attempt=attempt,
        )
        result["finished"] = True

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

        now = datetime.now()

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
            result["spend_time"] = int(
                (quiz_session.finished_at - quiz_session.started_at).total_seconds()
            )
        else:
            result["spend_time"] = 0

        await self.db.commit()
        return result

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
            notification_ser = await get_notification_service(db=self.db)
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
            "questions_count": 30,  # TODO: get real question count for quiz
            "started_at": quiz_session.started_at,
            "finished_at": quiz_session.finished_at,
            "session_type": quiz_session.session_type,
        }
        return result

    async def submit_answer_v2(self, session_id: int, user: User, payload: SubmitAnswerRequest):
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.status != "running":
            raise HTTPException(status_code=400, detail="Session is not running")

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
            "question_id": selected_option.question_id,
            "selected_option": selected_option.label,
            "is_correct": selected_option.is_correct,
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

    async def get_teacher_weak_students(self, teacher_id: int,filters: WeakStudentsFilterParams,):
        return await self.session_repo.teacher_weak_students(teacher_id,filters)



def get_quiz_session_service(db: AsyncSession = Depends(get_db),
                             redis_client: Redis = Depends(get_redis_client)) -> QuizSessionService:
    return QuizSessionService(db, redis_client)

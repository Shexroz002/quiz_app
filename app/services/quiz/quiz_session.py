import random
import string
from datetime import datetime

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.models import User
from app.repositories.quiz.question_repo import QuestionRepository
from app.repositories.quiz.quiz_attempt_repo import QuizAttemptRepository
from app.repositories.quiz.quiz_repo import QuizRepository
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository
from app.repositories.quiz.session_participant import SessionParticipantRepository
from app.schemas.quiz.quiz_attempt import SubmitAnswerRequest
from app.schemas.quiz.quiz_session import QuizSessionCreate
from app.websocket import session_ws_manager


def generate_join_code() -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


class QuizSessionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.quiz_repo = QuizRepository(db)
        self.session_repo = QuizSessionRepository(db)
        self.question_repo = QuestionRepository(db)
        self.participant_repo = SessionParticipantRepository(db)
        self.attempt_repo = QuizAttemptRepository(db)

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

    async def create(self, quiz_session_data: QuizSessionCreate, user: User):
        quiz = await self.quiz_repo.get(quiz_session_data.quiz_id, user.id)
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")

        join_code = await self._generate_unique_join_code()

        quiz_session = await self.session_repo.create(
            {
                **quiz_session_data.model_dump(),
                "host_id": user.id,
                "join_code": join_code,
                "status": "waiting",
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

    async def add_participant(self, session_code: str, user: User):
        quiz_session = await self.session_repo.get_by_join_code(session_code)
        if not quiz_session:
            raise HTTPException(status_code=404, detail="Invalid session code")

        if quiz_session.status != "waiting":
            raise HTTPException(status_code=400, detail="Session already started")

        is_participant = await self.participant_repo.is_participant(quiz_session.id, user.id)
        if not is_participant:
            await self.participant_repo.create(
                {
                    "session_id": quiz_session.id,
                    "nickname": user.username,
                    "user_id": user.id,
                    "is_host": False,
                }
            )
            await self.db.commit()

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

        if quiz_session.status != "waiting":
            raise HTTPException(status_code=400, detail="Session is not in waiting state")

        participants = await self.participant_repo.get_all_by_session_id(session_id)
        if not participants:
            raise HTTPException(status_code=400, detail="No participants in session")

        await self.session_repo.start_session(quiz_session)

        attempts_created = 0
        for participant in participants:
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
            option_label=payload.selected_option,
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
        participant_rows = await self.participant_repo.get_participant_list(session_id)
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

        quiz_session = await self.session_repo.get_single_player_session(session_id, status="running")
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
        quiz_session = await self.session_repo.get_single_player_session(session_id, status=status)
        if not quiz_session:
            raise HTTPException(status_code=404, detail="Session not found")

        questions = await self.question_repo.list_with_details(quiz_session.quiz_id, user_id)
        result = {
            "session_id": quiz_session.id,
            "quiz_id": quiz_session.quiz_id,
            "duration_minutes": quiz_session.duration_minutes,
            "join_code": quiz_session.join_code,
            "host_id": quiz_session.host_id,
            "questions_count": len(questions),
            "status": quiz_session.status,
            "started_at": quiz_session.started_at,
            "finished_at": quiz_session.finished_at,
        }
        if is_question:
            result["questions"] = questions
        return result

    async def finish_single_player_quiz(self, session_id: int, user_id: int, answers: list[SubmitAnswerRequest]):
        quiz_session = await self.session_repo.get_single_player_session(session_id)
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
                option_label=answer.selected_option,
            )
            if selected_option:
                await self.attempt_repo.upsert_answer(
                    attempt_id=attempt.id,
                    question_id=answer.question_id,
                    selected_option=answer.selected_option,
                    is_correct=selected_option.is_correct,
                )

        attempt.finished = True
        attempt.finished_at = datetime.now()
        quiz_session.status = "finished"
        quiz_session.finished_at = datetime.now()
        result = await self._build_attempt_result(
            session_id=session_id,
            quiz_id=quiz_session.quiz_id,
            attempt=attempt,
        )
        result["finished"] = True
        # spend_time return in seconds
        result["spend_time"] = int((quiz_session.finished_at - quiz_session.started_at).total_seconds())

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


def get_quiz_session_service(db: AsyncSession = Depends(get_db)) -> QuizSessionService:
    return QuizSessionService(db)

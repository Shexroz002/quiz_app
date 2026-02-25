from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AttemptAnswer, Option, Question, QuizAttempt, SessionParticipant


class QuizAttemptRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_session_participant(self, session_id: int, participant_id: int) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(
            QuizAttempt.session_id == session_id,
            QuizAttempt.participant_id == participant_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session_and_user(self, session_id: int, user_id: int) -> QuizAttempt | None:
        stmt = (
            select(QuizAttempt)
            .join(SessionParticipant, QuizAttempt.participant_id == SessionParticipant.id)
            .where(
                QuizAttempt.session_id == session_id,
                SessionParticipant.user_id == user_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, session_id: int, participant_id: int) -> QuizAttempt:
        attempt = QuizAttempt(
            session_id=session_id,
            participant_id=participant_id,
            score=0,
            current_question=1,
            finished=False,
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def get_or_create(self, session_id: int, participant_id: int) -> QuizAttempt:
        attempt = await self.get_by_session_participant(session_id, participant_id)
        if attempt:
            return attempt
        return await self.create(session_id=session_id, participant_id=participant_id)

    async def get_answer(self, attempt_id: int, question_id: int) -> AttemptAnswer | None:
        stmt = select(AttemptAnswer).where(
            AttemptAnswer.attempt_id == attempt_id,
            AttemptAnswer.question_id == question_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_answer(
        self,
        attempt_id: int,
        question_id: int,
        selected_option: str,
        is_correct: bool,
    ) -> AttemptAnswer:
        answer = await self.get_answer(attempt_id=attempt_id, question_id=question_id)
        if answer:
            answer.selected_option = selected_option
            answer.is_correct = is_correct
            await self.db.flush()
            return answer

        answer = AttemptAnswer(
            attempt_id=attempt_id,
            question_id=question_id,
            selected_option=selected_option,
            is_correct=is_correct,
        )
        self.db.add(answer)
        await self.db.flush()
        return answer

    async def get_option_for_question(self, question_id: int, option_label: str) -> Option | None:
        stmt = select(Option).where(
            Option.question_id == question_id,
            Option.label == option_label,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def is_question_in_quiz(self, question_id: int, quiz_id: int) -> bool:
        stmt = select(Question.id).where(
            Question.id == question_id,
            Question.quiz_id == quiz_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_total_questions(self, quiz_id: int) -> int:
        stmt = select(func.count(Question.id)).where(Question.quiz_id == quiz_id)
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_answer_count(self, attempt_id: int) -> int:
        stmt = select(func.count(AttemptAnswer.id)).where(AttemptAnswer.attempt_id == attempt_id)
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def get_correct_answer_count(self, attempt_id: int) -> int:
        stmt = select(func.count(AttemptAnswer.id)).where(
            AttemptAnswer.attempt_id == attempt_id,
            AttemptAnswer.is_correct.is_(True),
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

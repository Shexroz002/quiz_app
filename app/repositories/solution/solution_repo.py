from datetime import datetime

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AttemptAnswer,
    ExplanationFeedback,
    MistakeReview,
    Question,
    QuestionExplanation,
    QuizAttempt,
    SessionParticipant,
    SolveRequest,
)
from app.models.solution import ExplanationStatus


class SolutionRepository:
    """Reads and writes the three solution tables, and reads questions.

    Questions, options and answers are only ever read here.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # -- bank questions ---------------------------------------------------

    async def question_with_options(self, question_id: int) -> Question | None:
        stmt = (
            select(Question)
            .options(selectinload(Question.options), selectinload(Question.images))
            .where(Question.id == question_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def user_may_see(self, user_id: int, question_id: int) -> bool:
        """True once the student has finished a test containing the question.

        A solution names the right option. Shown mid-test it would be an answer
        key, so an unfinished attempt does not count; the mistake bank does,
        because only finished attempts feed it.
        """
        answered = (
            select(AttemptAnswer.id)
            .join(QuizAttempt, AttemptAnswer.attempt_id == QuizAttempt.id)
            .join(SessionParticipant, QuizAttempt.participant_id == SessionParticipant.id)
            .where(
                SessionParticipant.user_id == user_id,
                AttemptAnswer.question_id == question_id,
                QuizAttempt.finished.is_(True),
            )
        )
        in_bank = select(MistakeReview.id).where(
            MistakeReview.user_id == user_id, MistakeReview.question_id == question_id
        )
        result = await self.db.execute(select(exists(answered) | exists(in_bank)))
        return bool(result.scalar())

    async def explanation_for(self, question_id: int) -> QuestionExplanation | None:
        result = await self.db.execute(
            select(QuestionExplanation).where(QuestionExplanation.question_id == question_id)
        )
        return result.scalar_one_or_none()

    async def explanation(self, explanation_id: int) -> QuestionExplanation | None:
        return await self.db.get(QuestionExplanation, explanation_id)

    async def ensure_explanation(self, question_id: int) -> tuple[QuestionExplanation, bool]:
        """The row for a question and whether this call created it.

        Two students opening the same question at once must not both start a
        generation: the insert is ON CONFLICT DO NOTHING, and only the caller
        whose insert returned a row goes on to queue the task.
        """
        result = await self.db.execute(
            insert(QuestionExplanation)
            .values(question_id=question_id, status=ExplanationStatus.pending)
            .on_conflict_do_nothing(index_elements=["question_id"])
            .returning(QuestionExplanation.id)
        )
        created = result.scalar_one_or_none() is not None
        row = await self.explanation_for(question_id)
        assert row is not None
        return row, created

    # -- students' own problems --------------------------------------------

    async def add_request(self, request: SolveRequest) -> SolveRequest:
        self.db.add(request)
        await self.db.flush()
        return request

    async def request(self, request_id: int) -> SolveRequest | None:
        return await self.db.get(SolveRequest, request_id)

    async def requests_since(self, user_id: int, since: datetime) -> int:
        result = await self.db.execute(
            select(func.count(SolveRequest.id)).where(
                SolveRequest.user_id == user_id, SolveRequest.created_at >= since
            )
        )
        return int(result.scalar() or 0)

    async def history(self, user_id: int, limit: int) -> list[SolveRequest]:
        result = await self.db.execute(
            select(SolveRequest)
            .where(SolveRequest.user_id == user_id, SolveRequest.input_text != "")
            .order_by(SolveRequest.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # -- feedback ------------------------------------------------------------

    async def feedback_for(
        self, user_id: int, *, explanation_id: int | None, solve_request_id: int | None
    ) -> ExplanationFeedback | None:
        stmt = select(ExplanationFeedback).where(ExplanationFeedback.user_id == user_id)
        if explanation_id is not None:
            stmt = stmt.where(ExplanationFeedback.explanation_id == explanation_id)
        else:
            stmt = stmt.where(ExplanationFeedback.solve_request_id == solve_request_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_feedback(self, feedback: ExplanationFeedback) -> None:
        self.db.add(feedback)
        await self.db.flush()

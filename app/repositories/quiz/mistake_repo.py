from datetime import datetime, timedelta

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    AttemptAnswer,
    MistakeReview,
    Option,
    Question,
    QuizAttempt,
    SessionParticipant,
)


class MistakeRepository:
    """Reads and writes the mistake bank.

    The bank is derived data: the authoritative record of a wrong answer is the
    row in `attempt_answers`. `mistake_reviews` only carries the schedule, so
    `missing_question_ids` can top it up from a student's whole history — on the
    first read as well as after any gap.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _answerable() -> Select:
        """Question ids that have exactly one option marked correct.

        87 of the questions in the database have no correct option and a few
        have several. A review can never be answered right, so such a question
        would sit in the bank forever: it is kept out of the bank entirely.
        """
        return (
            select(Option.question_id)
            .group_by(Option.question_id)
            .having(func.count().filter(Option.is_correct.is_(True)) == 1)
        )

    def _mine(self) -> Select:
        """Answers that belong to one student, joined back to the session."""
        return (
            select(AttemptAnswer.question_id)
            .join(QuizAttempt, AttemptAnswer.attempt_id == QuizAttempt.id)
            .join(SessionParticipant, QuizAttempt.participant_id == SessionParticipant.id)
        )

    async def missing_question_ids(self, user_id: int) -> list[int]:
        """Questions the student answered wrongly that have no review row yet.

        Covers competition answers too: a mistake is a mistake wherever it was
        made (owner decision).
        """
        already = select(MistakeReview.question_id).where(MistakeReview.user_id == user_id)
        stmt = (
            self._mine()
            .where(
                SessionParticipant.user_id == user_id,
                AttemptAnswer.is_correct.is_(False),
                AttemptAnswer.question_id.notin_(already),
                AttemptAnswer.question_id.in_(self._answerable()),
            )
            .group_by(AttemptAnswer.question_id)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def add_many(self, user_id: int, question_ids: list[int], due_at: datetime) -> None:
        for question_id in question_ids:
            self.db.add(
                MistakeReview(
                    user_id=user_id,
                    question_id=question_id,
                    due_at=due_at,
                    streak=0,
                    wrong_count=1,
                )
            )
        await self.db.flush()

    async def get(self, user_id: int, question_id: int) -> MistakeReview | None:
        stmt = select(MistakeReview).where(
            MistakeReview.user_id == user_id,
            MistakeReview.question_id == question_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def open_rows(self, user_id: int) -> list[MistakeReview]:
        """Every question still in the bank, with its question loaded."""
        stmt = (
            select(MistakeReview)
            .options(selectinload(MistakeReview.question))
            .where(
                MistakeReview.user_id == user_id,
                MistakeReview.cleared_at.is_(None),
                # Rows stored before the filter existed stay hidden.
                MistakeReview.question_id.in_(self._answerable()),
            )
            .order_by(MistakeReview.due_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def due_rows(
        self,
        user_id: int,
        now: datetime,
        limit: int,
        subject: str | None = None,
    ) -> list[MistakeReview]:
        """Questions ready to review, with everything the batch schema reads.

        The images are eager-loaded on purpose: reaching them lazily inside the
        async service raises MissingGreenlet instead of returning a question.

        A subject narrows the query rather than the result, so a full batch is
        still a full batch; it is matched case-folded because the same subject
        is stored under several spellings.
        """
        stmt = (
            select(MistakeReview)
            .join(MistakeReview.question)
            .options(
                selectinload(MistakeReview.question).selectinload(Question.images)
            )
            .where(
                MistakeReview.user_id == user_id,
                MistakeReview.cleared_at.is_(None),
                MistakeReview.due_at <= now,
                MistakeReview.question_id.in_(self._answerable()),
            )
            .order_by(MistakeReview.due_at)
            .limit(limit)
        )
        if subject:
            stmt = stmt.where(
                func.lower(func.trim(Question.subject)) == subject.strip().lower()
            )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def due_count(self, user_id: int, now: datetime) -> int:
        stmt = select(func.count(MistakeReview.id)).where(
            MistakeReview.user_id == user_id,
            MistakeReview.cleared_at.is_(None),
            MistakeReview.due_at <= now,
            MistakeReview.question_id.in_(self._answerable()),
        )
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def cleared_since(self, user_id: int, since: datetime) -> int:
        stmt = select(func.count(MistakeReview.id)).where(
            MistakeReview.user_id == user_id,
            MistakeReview.cleared_at.is_not(None),
            MistakeReview.cleared_at >= since,
        )
        result = await self.db.execute(stmt)
        return int(result.scalar() or 0)

    async def options_for(self, question_ids: list[int]) -> dict[int, list[Option]]:
        if not question_ids:
            return {}
        stmt = select(Option).where(Option.question_id.in_(question_ids)).order_by(Option.label)
        result = await self.db.execute(stmt)
        grouped: dict[int, list[Option]] = {}
        for option in result.scalars().all():
            grouped.setdefault(option.question_id, []).append(option)
        return grouped

    async def users_with_due(self, now: datetime) -> list[int]:
        """Students who have something waiting. Used by the daily reminder."""
        stmt = (
            select(MistakeReview.user_id)
            .where(
                MistakeReview.cleared_at.is_(None),
                MistakeReview.due_at <= now,
                MistakeReview.question_id.in_(self._answerable()),
            )
            .group_by(MistakeReview.user_id)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

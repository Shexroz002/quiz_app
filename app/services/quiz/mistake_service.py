from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.models import MistakeReview
from app.repositories.quiz.mistake_repo import MistakeRepository
from app.schemas.quiz.mistake import (
    MistakeAnswerResponse,
    MistakeOptionSchema,
    MistakeOverviewSchema,
    MistakeQuestionSchema,
    MistakeSubjectSchema,
)
from app.utils.datetime import utc_now

#: Days until a question comes back, indexed by how many correct answers in a
#: row it has. A wrong answer resets to index 0. Deliberately short and
#: explainable — the app tells the student the rule.
REVIEW_INTERVALS_DAYS = (1, 3, 7)

#: Correct answers in a row that clear a question.
CLEAR_STREAK = 2

#: Questions served in one review. Enough for a short sitting.
REVIEW_BATCH = 20

#: Window behind "closed in the last 30 days".
CLEARED_WINDOW_DAYS = 30


class MistakeService:
    """The mistake bank: what is due, what to serve, and what an answer does.

    The bank is filled from `attempt_answers` rather than written as the student
    plays. One sync on read keeps the logic in a single place, survives any gap,
    and — because it looks at the whole history — a student who has been using
    the app for months gets a full bank the first time they open it.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = MistakeRepository(db)

    async def _sync(self, user_id: int, now: datetime) -> None:
        """Adds review rows for wrong answers that do not have one yet.

        Committed here on purpose: `get_db` hands out a session and never
        commits, so rows only flushed would vanish with the request — the bank
        would look right on screen and then be empty when an answer arrived.
        """
        missing = await self.repo.missing_question_ids(user_id)
        if not missing:
            return
        # Straight into the queue: these are mistakes already made, so there is
        # nothing to wait for.
        await self.repo.add_many(user_id, missing, due_at=now)
        await self.db.commit()

    @staticmethod
    def _next_due(streak: int, now: datetime) -> datetime:
        index = min(streak, len(REVIEW_INTERVALS_DAYS) - 1)
        return now + timedelta(days=REVIEW_INTERVALS_DAYS[index])

    async def overview(self, user_id: int) -> MistakeOverviewSchema:
        now = utc_now()
        await self._sync(user_id, now)
        rows = await self.repo.open_rows(user_id)

        by_subject: dict[str, dict] = {}
        due_total = 0
        next_due: datetime | None = None

        for row in rows:
            question = row.question
            subject = (question.subject or "").strip() or "Boshqa"
            # The same subject is stored under several spellings ("fizika" and
            # "Fizika"), which would otherwise split one subject into two rows.
            # The first spelling seen wins as the label.
            key = subject.casefold()
            bucket = by_subject.setdefault(
                key, {"label": subject, "total": 0, "due": 0, "next_due_at": None}
            )
            bucket["total"] += 1

            if row.due_at <= now:
                bucket["due"] += 1
                due_total += 1
            else:
                if bucket["next_due_at"] is None or row.due_at < bucket["next_due_at"]:
                    bucket["next_due_at"] = row.due_at
                if next_due is None or row.due_at < next_due:
                    next_due = row.due_at

        subjects = [
            MistakeSubjectSchema(
                subject=data["label"],
                total=data["total"],
                due=data["due"],
                next_due_at=data["next_due_at"],
            )
            # Most to review first, so the busiest subject leads the list.
            for data in sorted(
                by_subject.values(), key=lambda data: (-data["due"], -data["total"])
            )
        ]

        cleared = await self.repo.cleared_since(
            user_id, now - timedelta(days=CLEARED_WINDOW_DAYS)
        )

        return MistakeOverviewSchema(
            total=len(rows),
            due=due_total,
            next_due_at=None if due_total else next_due,
            cleared_last_30_days=cleared,
            subjects=subjects,
        )

    async def review_batch(
        self, user_id: int, subject: str | None = None
    ) -> list[MistakeQuestionSchema]:
        """Questions to review now. Empty when nothing is due.

        There is no practising ahead of schedule (owner decision): waiting out
        the interval is what makes the interval work.
        """
        now = utc_now()
        await self._sync(user_id, now)
        rows = await self.repo.due_rows(
            user_id, now, limit=REVIEW_BATCH, subject=subject
        )

        options = await self.repo.options_for([row.question_id for row in rows])
        batch: list[MistakeQuestionSchema] = []
        for row in rows:
            question = row.question
            choices = options.get(row.question_id, [])
            correct = next((o.label for o in choices if o.is_correct), None)
            batch.append(
                MistakeQuestionSchema(
                    question_id=row.question_id,
                    question_text=question.question_text,
                    subject=question.subject,
                    topic=question.topic,
                    table_markdown=question.table_markdown,
                    image_urls=[image.image_url for image in (question.images or [])],
                    options=[MistakeOptionSchema.model_validate(o) for o in choices],
                    correct_option=correct,
                    wrong_count=row.wrong_count,
                )
            )
        return batch

    async def answer(
        self, user_id: int, question_id: int, selected_option: str
    ) -> MistakeAnswerResponse:
        now = utc_now()
        row = await self.repo.get(user_id, question_id)
        if row is None or row.cleared_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bu savol xatolar bankida yo‘q.",
            )

        options = (await self.repo.options_for([question_id])).get(question_id, [])
        correct = next((o.label for o in options if o.is_correct), None)
        is_correct = correct is not None and selected_option.strip().upper() == correct.upper()

        if is_correct:
            row.streak += 1
        else:
            # A miss sends the question back to the start of the ladder.
            row.streak = 0
            row.wrong_count += 1

        row.last_reviewed_at = now
        cleared = is_correct and row.streak >= CLEAR_STREAK
        if cleared:
            row.cleared_at = now
        else:
            row.due_at = self._next_due(row.streak, now)

        await self.db.flush()
        await self.db.commit()

        remaining = await self.repo.due_count(user_id, now)
        return MistakeAnswerResponse(
            question_id=question_id,
            is_correct=is_correct,
            correct_option=correct,
            streak=row.streak,
            cleared=cleared,
            next_due_at=None if cleared else row.due_at,
            remaining_due=remaining,
        )


async def get_mistake_service(db: AsyncSession = Depends(get_db)) -> MistakeService:
    return MistakeService(db)

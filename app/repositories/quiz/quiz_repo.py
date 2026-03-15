from fastapi import HTTPException
from sqlalchemy import select, and_, text, or_, cast, Numeric
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import func

from app.models import Quiz, Option, AttemptAnswer, QuizSession, SessionParticipant, QuizAttempt
from app.models.quiz import Question


class QuizRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, user_id: int):
        stmt = select(Quiz).where(Quiz.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get(self, quiz_id: int, user_id: int):
        stmt = select(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, quiz_id: int, user_id, update_data: dict):
        quiz = await self.get(quiz_id, user_id)

        if not quiz:
            return None

        for field, value in update_data.items():
            if hasattr(quiz, field):
                setattr(quiz, field, value)

        self.db.add(quiz)
        await self.db.commit()
        await self.db.refresh(quiz)
        return quiz

    async def delete(self, quiz_id: int, user_id: int):
        quiz = await self.get(quiz_id, user_id)

        if not quiz:
            return None

        await self.db.delete(quiz)
        await self.db.commit()
        return quiz

    async def get_quiz_full_info(self, quiz_id):
        stmt = (
            select(Quiz)
            .where(Quiz.id == quiz_id)
            .options(
                selectinload(Quiz.questions)
                .selectinload(Question.options),
                selectinload(Quiz.questions)
                .selectinload(Question.images),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def quiz_answer_by_id(self, quiz_id: int):
        stmt = (
            select(Question.id, Option.label)
            .join(Quiz.questions)
            .join(Question.options)
            .where(
                Quiz.id == quiz_id,
                Option.is_correct.is_(True)
            )
        )

        result = await self.db.execute(stmt)
        return result.mappings().all()

    async def quiz_list(self, user_id, **kwargs):

        conditions = [Quiz.user_id == user_id]

        # optional search filter
        search = kwargs.get("search")
        if search:
            # Example: search in title/description (adjust to your needs)
            like = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Quiz.title.ilike(like),
                    Quiz.description.ilike(like),
                )
            )

        stmt = (
            select(
                Quiz.id,
                Quiz.title,
                Quiz.user_id,
                Quiz.created_at,
                Quiz.description,
                Quiz.subject,
                func.count(Question.id).label("question_count"),
                ((func.now() - Quiz.created_at) < text("interval '7 days'")).label("is_new"),
            )
            .select_from(Quiz)
            .outerjoin(Question, Question.quiz_id == Quiz.id)
            .where(and_(*conditions))
            .group_by(
                Quiz.id,
                Quiz.title,
                Quiz.user_id,
                Quiz.created_at,
                Quiz.description,
                Quiz.subject,
            )
            .order_by(Quiz.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.mappings().all()

    async def detail(self, user_id, quiz_id):

        stmt = (
            select(Quiz)
            .options(selectinload(Quiz.questions))
            .where(Quiz.id == quiz_id, Quiz.user_id == user_id)
        )

        quiz = await self.db.execute(stmt)
        quiz = quiz.scalar_one_or_none()
        if not quiz:
            raise HTTPException(404, "Quiz not found")

        return quiz

    async def get_topic_statistics(self, user_id: int, subject: str, search: str | None = None):
        correct_count = func.count(Question.id).filter(AttemptAnswer.is_correct.is_(True))
        wrong_count = func.count(Question.id).filter(AttemptAnswer.is_correct.is_(False))
        total_count = func.count(Question.id)

        first_test_date = func.min(func.date(QuizSession.created_at)).label("first_test_date")
        last_test_date = func.max(func.date(QuizSession.created_at)).label("last_test_date")

        percentage_expr = func.round(
            cast(
                (100 * correct_count) / func.nullif(total_count, 0),
                Numeric(5, 2)
            ),
            2
        )
        filters = [
            func.lower(Question.subject) == subject.lower(),
            SessionParticipant.user_id == user_id,
        ]

        # 🔎 optional topic search
        if search:
            filters.append(
                func.lower(Question.topic).like(f"%{search.lower()}%")
            )

        stmt = (
            select(
                Question.subject.label("subject_name"),
                Question.topic.label("topic_name"),
                correct_count.label("correct_answer"),
                wrong_count.label("wrong_answer"),
                total_count.label("total_answer"),
                percentage_expr.label("percentage"),
                first_test_date.label("first_test_date"),
                last_test_date.label("last_test_date"),
            )
            .select_from(QuizSession)
            .join(
                SessionParticipant,
                QuizSession.id == SessionParticipant.session_id,
                isouter=True,
            )
            .join(
                QuizAttempt,
                and_(
                    QuizAttempt.session_id == QuizSession.id,
                    QuizAttempt.participant_id == SessionParticipant.id,
                ),
                isouter=True,
            )
            .join(
                AttemptAnswer,
                AttemptAnswer.attempt_id == QuizAttempt.id,
                isouter=True,
            )
            .join(
                Question,
                AttemptAnswer.question_id == Question.id,
                isouter=True,
            )
            .where(
                *filters
            )
            .group_by(Question.subject, Question.topic).order_by(percentage_expr.desc(), total_count.desc(),
                                                                 correct_count.desc())
        )

        result = await self.db.execute(stmt)
        return result.mappings().all()

    async def get_subject_statistics(self, user_id: int):
        """
        Get statistics for each subject the user has attempted questions in, including:
            - subject_name: The name of the subject.
            - correct_answer: The total number of correct answers for that subject.
            - wrong_answer: The total number of wrong answers for that subject.
            - total_answer: The total number of answers (correct + wrong) for that subject.
            - percentage: The percentage of correct answers out of total answers for that subject,
        """

        correct_count = func.count(Question.id).filter(
            AttemptAnswer.is_correct.is_(True)
        )
        wrong_count = func.count(Question.id).filter(
            AttemptAnswer.is_correct.is_(False)
        )
        total_count = func.count(Question.id)
        first_attempt_date = func.min(func.date(QuizSession.created_at)).label("first_attempt_date")
        last_attempt_date = func.max(func.date(QuizSession.created_at)).label("last_attempt_date")

        percentage_expr = func.round(
            cast(
                (100 * correct_count) / func.nullif(total_count, 0),
                Numeric(10, 2),
            ),
            2,
        ).label("percentage")

        stmt = (
            select(
                Question.subject.label("subject_name"),
                correct_count.label("correct_answer"),
                wrong_count.label("wrong_answer"),
                total_count.label("total_answer"),
                percentage_expr,
                first_attempt_date,
                last_attempt_date,
            )
            .select_from(QuizSession)
            .join(
                SessionParticipant,
                QuizSession.id == SessionParticipant.session_id,
                isouter=True,
            )
            .join(
                QuizAttempt,
                and_(
                    QuizAttempt.session_id == QuizSession.id,
                    QuizAttempt.participant_id == SessionParticipant.id,
                ),
                isouter=True,
            )
            .join(
                AttemptAnswer,
                AttemptAnswer.attempt_id == QuizAttempt.id,
                isouter=True,
            )
            .join(
                Question,
                AttemptAnswer.question_id == Question.id,
                isouter=True,
            )
            .where(
                SessionParticipant.user_id == user_id,
                Question.subject.is_not(None),
            )
            .group_by(Question.subject)
            .order_by(
                percentage_expr.desc(),
                correct_count.desc(),
                total_count.desc(),
            )
        )

        result = await self.db.execute(stmt)
        return result.mappings().all()

    async def get_overall_statistic_cards(
            self,
            user_id: int,
    ):
        total_quiz_expr = func.count(func.distinct(SessionParticipant.session_id))
        correct_answer_expr = func.count(AttemptAnswer.question_id).filter(
            AttemptAnswer.is_correct.is_(True)
        )
        total_answer_expr = func.count(Question.id)

        average_expr = func.round(
            cast(
                (100 * correct_answer_expr) / func.nullif(total_answer_expr, 0),
                Numeric(10, 2),
            ),
            2,
        ).label("average")

        stmt = (
            select(
                total_quiz_expr.label("total_quiz_session"),
                correct_answer_expr.label("correct_answer"),
                average_expr,
            )
            .select_from(QuizSession)
            .join(
                SessionParticipant,
                QuizSession.id == SessionParticipant.session_id,
                isouter=True,
            )
            .join(
                QuizAttempt,
                and_(
                    QuizAttempt.session_id == QuizSession.id,
                    QuizAttempt.participant_id == SessionParticipant.id,
                ),
                isouter=True,
            )
            .join(
                AttemptAnswer,
                AttemptAnswer.attempt_id == QuizAttempt.id,
                isouter=True,
            )
            .join(
                Question,
                AttemptAnswer.question_id == Question.id,
                isouter=True,
            )
            .where(SessionParticipant.user_id == user_id)
            .group_by(SessionParticipant.user_id)
        )

        result = await self.db.execute(stmt)
        return result.mappings().first()

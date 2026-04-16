from fastapi import HTTPException
from fastapi_pagination import paginate
from sqlalchemy import select, and_, text, or_, cast, Numeric, literal, case, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import func

from app.api.v1.teacher.quiz.params.quiz_filter import TeacherQuizListFilterSchema
from app.models import Quiz, Option, AttemptAnswer, QuizSession, SessionParticipant, QuizAttempt
from app.models.quiz import Question


class QuizRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, user_id: int):
        stmt = select(Quiz).where(Quiz.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def quiz_question_count(self,quiz_id: int):
        stmt = (
            select(func.count(Question.id))
            .where(Question.quiz_id == quiz_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

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
                Quiz.id.label('quiz_id'),
                Quiz.title,
                Quiz.user_id,
                Quiz.created_at,
                Quiz.description,
                Quiz.subject,
                Quiz.quiz_generate_type,
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
        return paginate(result.mappings().all())

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

    async def get_overall_statistic_cards(self, user_id: int):
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
        result_data = result.mappings().first()
        if result_data is None:
            return {
                "total_quiz_session": 0,
                "correct_answer": 0,
                "average": 0.0,
            }
        return result_data

    async def get_teacher_quizzes(self, user_id: int, filters: TeacherQuizListFilterSchema):
        q_count_subquery = (
            select(
                Question.quiz_id.label("quiz_id"),
                func.count(Question.id).label("question_count"),
            )
            .group_by(Question.quiz_id)
            .subquery()
        )

        attempts_subquery = (
            select(
                QuizSession.quiz_id.label("quiz_id"),
                func.count(QuizAttempt.id).label("attempts"),
            )
            .join(QuizAttempt, QuizAttempt.session_id == QuizSession.id)
            .group_by(QuizSession.quiz_id)
            .subquery()
        )

        avg_score_subq = (
            select(
                QuizSession.quiz_id.label("quiz_id"),
                cast(
                    func.avg(
                        (QuizAttempt.score * literal(100.0)) /
                        func.nullif(QuizAttempt.total_questions, 0)
                    ),
                    Numeric(10, 2)
                ).label("average_score"),
            )
            .join(QuizAttempt, QuizAttempt.session_id == QuizSession.id)
            .where(QuizAttempt.total_questions > 0)
            .group_by(QuizSession.quiz_id)
            .subquery()
        )

        stmt = (
            select(
                Quiz.id,
                Quiz.title,
                Quiz.subject,
                Quiz.quiz_generate_type,
                Quiz.created_at,
                func.coalesce(q_count_subquery.c.question_count, 0).label("question_count"),
                func.coalesce(attempts_subquery.c.attempts, 0).label("attempts"),
                cast(
                    func.coalesce(avg_score_subq.c.average_score, 0),
                    Numeric(10, 2)
                ).label("average_score"),
            )
            .outerjoin(q_count_subquery, q_count_subquery.c.quiz_id == Quiz.id)
            .outerjoin(attempts_subquery, attempts_subquery.c.quiz_id == Quiz.id)
            .outerjoin(avg_score_subq, avg_score_subq.c.quiz_id == Quiz.id)
            .where(Quiz.user_id == user_id)
            .order_by(Quiz.created_at.desc())
        )

        if filters.search:
            stmt = stmt.where(Quiz.title.ilike(f"%{filters.search.strip()}%"))

        if filters.quiz_generate_type:
            stmt = stmt.where(Quiz.quiz_generate_type == filters.quiz_generate_type)

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())

    async def get_quiz_statistics(self, quiz_id: int):
        percentage_expr = case(
            (
                QuizAttempt.total_questions > 0,
                100.0 * QuizAttempt.score / QuizAttempt.total_questions,
            ),
            else_=None,
        )

        total_attempts_expr = func.count(QuizAttempt.id).label("total_attempts")

        average_score_expr = func.coalesce(
            func.round(
                cast(
                    func.avg(percentage_expr).filter(QuizAttempt.finished.is_(True)),
                    Numeric(10, 2),
                ),
                2,
            ),
            0,
        ).label("average_score")

        completion_rate_expr = func.coalesce(
            func.round(
                cast(
                    100.0
                    * func.count(QuizAttempt.id).filter(QuizAttempt.finished.is_(True))
                    / func.nullif(func.count(QuizAttempt.id), 0),
                    Numeric(10, 2),
                ),
                2,
            ),
            0,
        ).label("completion_rate")

        success_rate_expr = func.coalesce(
            func.round(
                cast(
                    100.0
                    * func.count(QuizAttempt.id).filter(
                        QuizAttempt.finished.is_(True),
                        percentage_expr >= 60,
                    )
                    / func.nullif(
                        func.count(QuizAttempt.id).filter(QuizAttempt.finished.is_(True)),
                        0,
                    ),
                    Numeric(10, 2),
                ),
                2,
            ),
            0,
        ).label("success_rate")

        highest_score_expr = func.coalesce(
            func.round(
                cast(
                    func.max(percentage_expr).filter(QuizAttempt.finished.is_(True)),
                    Numeric(10, 2),
                ),
                2,
            ),
            0,
        ).label("highest_score")

        champions_count_expr = func.count(QuizAttempt.id).filter(
            QuizAttempt.finished.is_(True),
            percentage_expr >= 86,
        ).label("champions_count")

        stmt = (
            select(
                total_attempts_expr,
                average_score_expr,
                completion_rate_expr,
                success_rate_expr,
                highest_score_expr,
                champions_count_expr,
            )
            .select_from(QuizSession)
            .join(QuizAttempt, QuizAttempt.session_id == QuizSession.id)
            .where(QuizSession.quiz_id == quiz_id)
        )

        result = await self.db.execute(stmt)
        row = result.mappings().first()

        if not row:
            return {
                "total_attempts": 0,
                "average_score": 0.0,
                "completion_rate": 0.0,
                "success_rate": 0.0,
                "highest_score": 0.0,
                "champions_count": 0,
            }

        return {
            "total_attempts": int(row["total_attempts"] or 0),
            "average_score": float(row["average_score"] or 0),
            "completion_rate": float(row["completion_rate"] or 0),
            "success_rate": float(row["success_rate"] or 0),
            "highest_score": float(row["highest_score"] or 0),
            "champions_count": int(row["champions_count"] or 0),
        }

    async def has_all_correct_options(self, quiz_id: int) -> bool:
        """
        Check if every question in the quiz has at least one correct option.

        Returns:
            True  -> if all questions have at least one correct option
            False -> if at least one question has no correct option
        """
        total_questions_stmt = (
            select(func.count(Question.id))
            .where(Question.quiz_id == quiz_id)
        )

        questions_with_correct_option_stmt = (
            select(func.count(distinct(Question.id)))
            .select_from(Question)
            .join(Option, Option.question_id == Question.id)
            .where(
                Question.quiz_id == quiz_id,
                Option.is_correct.is_(True),
            )
        )

        total_questions = (await self.db.execute(total_questions_stmt)).scalar() or 0
        questions_with_correct_option = (
                                            await self.db.execute(questions_with_correct_option_stmt)
                                        ).scalar() or 0

        if total_questions == 0:
            return False

        return total_questions == questions_with_correct_option
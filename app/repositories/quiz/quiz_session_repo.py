from datetime import UTC, datetime, timedelta

from fastapi_pagination import paginate
from sqlalchemy import func, cast, literal, JSON, and_, Numeric, case, String
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuizSession, QuizAttempt, SessionParticipant, Option, Question, AttemptAnswer, QuestionImage, \
    Quiz, User, Subject
from app.models.quiz.real_time_quiz.quiz_session import SessionType, SessionStatus


class QuizSessionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_host(self, session_id: int, host_id: int) -> QuizSession | None:
        stmt = select(QuizSession).where(
            QuizSession.id == session_id,
            QuizSession.host_id == host_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, session_id: int) -> QuizSession | None:
        stmt = select(QuizSession).where(QuizSession.id == session_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_join_code(self, join_code: str) -> QuizSession | None:
        stmt = select(QuizSession).where(QuizSession.join_code == join_code)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict) -> QuizSession:
        quiz_session = QuizSession(**data)
        self.db.add(quiz_session)
        await self.db.flush()
        return quiz_session

    async def get_running_sessions_by_host(self,host_id:int):

        stmt = (
            select(
                QuizSession.id.label("session_id"),
                Quiz.title.label("title"),
                Quiz.subject.label("subject"),
                func.count(SessionParticipant.id).label("participants_count"),
                QuizSession.duration_minutes.label("duration_minutes"),
                func.to_char(QuizSession.started_at, "HH24:MI").label("started_at"),
                QuizSession.join_code.label("join_code"),
                QuizSession.session_type
            )
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .outerjoin(SessionParticipant, SessionParticipant.session_id == QuizSession.id)
            .where(
                QuizSession.host_id == host_id,
                QuizSession.status == SessionStatus.running,
            )
            .group_by(QuizSession.id, Quiz.title, Quiz.subject)
        )

        result = await self.db.execute(stmt)
        return result.mappings().all()

    async def start_session(self, quiz_session: QuizSession) -> QuizSession:
        now = datetime.now(UTC)
        quiz_session.status = SessionStatus.running
        quiz_session.started_at = now
        quiz_session.finished_at = now + timedelta(minutes=quiz_session.duration_minutes)
        await self.db.flush()
        return quiz_session

    async def get_single_player_session(
            self,
            session_id: int,
            host_id: int | None = None,
            status=SessionStatus.running,
    ):
        stmt = (
            select(
                QuizSession.id,
                QuizSession.status,
                QuizSession.host_id,
                QuizSession.duration_minutes,
                QuizSession.join_code,
                QuizSession.started_at,
                QuizSession.finished_at,
                Quiz.id.label("quiz_id"),
                Quiz.title.label("quiz_name"),
                Quiz.subject.label("subject_name"),
                QuizSession.session_type
            )
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizSession.id == session_id
            )
        )

        if host_id:
            stmt = stmt.where(QuizSession.host_id == host_id)

        result = await self.db.execute(stmt)
        return result.mappings().first()

    async def player_session(
            self,
            session_id: int,
            host_id: int | None = None,
            status=SessionStatus.running,
    ):
        stmt = (
            select(QuizSession)
            .where(
                QuizSession.id == session_id,
                QuizSession.status == status,
            )
        )

        if host_id:
            stmt = stmt.where(QuizSession.host_id == host_id)

        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_session_questions_with_answers(
            self,
            session_id: int,
            host_id: int,
    ):

        sp_id_sq = (
            select(SessionParticipant.id)
            .where(SessionParticipant.session_id == QuizSession.id)
            .order_by(SessionParticipant.id.asc())
            .limit(1)
            .correlate(QuizSession)
            .scalar_subquery()
        )

        qa_id_sq = (
            select(QuizAttempt.id)
            .where(
                QuizAttempt.session_id == QuizSession.id,
                QuizAttempt.participant_id == sp_id_sq,
            )
            .order_by(QuizAttempt.id.desc())
            .limit(1)
            .correlate(QuizSession)
            .scalar_subquery()
        )

        options_sq = (
            select(
                func.coalesce(
                    func.json_agg(
                        aggregate_order_by(
                            func.json_build_object(
                                "id", Option.id,
                                "label", Option.label,
                                "text", Option.text,
                                "is_correct", Option.is_correct,
                            ),
                            Option.id.asc(),
                        )
                    ),
                    cast(literal("[]"), JSON),  # fallback = []
                )
            )
            .where(Option.question_id == Question.id)
            .correlate(Question)
            .scalar_subquery()
        )
        images_sq = (
            select(
                func.coalesce(
                    func.json_agg(
                        aggregate_order_by(
                            func.json_build_object(
                                "id", QuestionImage.id,
                                "image_url", QuestionImage.image_url,
                            ),
                            QuestionImage.id.asc(),
                        )
                    ),
                    cast(literal("[]"), JSON),
                )
            )
            .where(QuestionImage.question_id == Question.id)
            .correlate(Question)
            .scalar_subquery()
        )

        stmt = (
            select(
                Question.id.label("id"),
                Question.quiz_id.label("question_id"),
                Question.difficulty.label("difficulty"),
                Question.question_text.label("question_text"),
                Question.subject.label("subject"),
                Question.table_markdown.label("table_markdown"),
                Question.topic.label("topic"),
                images_sq.label("images"),
                options_sq.label("options"),
                AttemptAnswer.selected_option.label("user_select_option"),
                AttemptAnswer.is_correct.label("user_select_option_is_correct"),
            )
            .select_from(QuizSession)
            .join(Question, Question.quiz_id == QuizSession.quiz_id)
            .outerjoin(
                AttemptAnswer,
                (AttemptAnswer.attempt_id == qa_id_sq)
                & (AttemptAnswer.question_id == Question.id),
            )
            .where(
                QuizSession.id == session_id
            )
            .order_by(Question.id.asc())
        )

        res = await self.db.execute(stmt)
        return res.mappings().all()

    async def get_personal_quiz_session_history(self, user_id: int, search: str):
        participants_subq = (
            select(
                SessionParticipant.session_id.label("session_id"),
                func.count(SessionParticipant.id).label("participant_count"),
            )
            .group_by(SessionParticipant.session_id)
            .subquery()
        )

        base_cte = (
            select(
                QuizSession.id.label("session_id"),
                SessionParticipant.user_id.label("user_id"),
                Quiz.title.label("title"),
                Quiz.subject.label("subject"),
                func.dense_rank()
                .over(
                    partition_by=QuizSession.id,
                    order_by=QuizAttempt.score.desc(),
                )
                .label("rank"),
                participants_subq.c.participant_count.label("participant_count"),
                QuizAttempt.score.label("correct_answers"),
                QuizAttempt.wrong_answers.label("wrong_answers"),
                QuizAttempt.total_questions.label("total_questions"),
                QuizAttempt.finished_at.label("finished_at"),
                QuizSession.created_at.label("created_at"),
            )
            .select_from(QuizSession)
            .outerjoin(Quiz, Quiz.id == QuizSession.quiz_id)
            .join(SessionParticipant, SessionParticipant.session_id == QuizSession.id)
            .outerjoin(
                QuizAttempt,
                and_(
                    QuizAttempt.session_id == QuizSession.id,
                    QuizAttempt.participant_id == SessionParticipant.id,
                ),
            )
            .outerjoin(
                participants_subq,
                participants_subq.c.session_id == QuizSession.id,
            )
            .cte("base")
        )

        if search:
            stmt = (
                select(base_cte)
                .where(
                    base_cte.c.user_id == user_id,
                    base_cte.c.title.ilike(f"%{search}%"),
                )
                .order_by(base_cte.c.session_id.desc())
            )
        else:
            stmt = (
                select(base_cte)
                .where(base_cte.c.user_id == user_id)
                .order_by(base_cte.c.session_id.desc())
            )

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())

    async def get_session_participant_rank_list(self, session_id: int, user_id: int):
        stmt = (
            select(
                SessionParticipant.user_id.label("user_id"),
                User.first_name.label("first_name"),
                User.last_name.label("last_name"),
                User.profile_image.label("profile_image"),
                QuizAttempt.score.label("score"),
                QuizAttempt.wrong_answers.label("wrong_answers"),
                QuizAttempt.total_questions.label("total_questions"),
                func.extract(
                    "epoch",
                    QuizAttempt.finished_at - QuizSession.started_at,
                ).label("spend_time_seconds")
            )
            .select_from(QuizSession)
            .join(SessionParticipant, SessionParticipant.session_id == QuizSession.id)
            .join(User, User.id == SessionParticipant.user_id)
            .outerjoin(
                QuizAttempt,
                and_(
                    QuizAttempt.session_id == QuizSession.id,
                    QuizAttempt.participant_id == SessionParticipant.id,
                ),
            )
            .where(QuizSession.id == session_id)
            .order_by(QuizAttempt.score.desc(), QuizAttempt.finished_at.asc())
        )

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())

    async def teacher_session_results(self, teacher_id: int):
        participants_subq = (
            select(
                SessionParticipant.session_id.label("session_id"),
                func.count(func.distinct(SessionParticipant.user_id)).label("participants_count"),
            )
            .group_by(SessionParticipant.session_id)
            .subquery()
        )

        average_score_subq = (
            select(
                QuizAttempt.session_id.label("session_id"),
                func.coalesce(
                    func.round(
                        cast(
                            func.avg(
                                case(
                                    (
                                        QuizAttempt.total_questions > 0,
                                        100.0 * QuizAttempt.score / QuizAttempt.total_questions,
                                    ),
                                    else_=None,
                                )
                            ),
                            Numeric(10, 2),
                        ),
                        2,
                    ),
                    0,
                ).label("average_score"),
            )
            .where(QuizAttempt.finished.is_(True))
            .group_by(QuizAttempt.session_id)
            .subquery()
        )

        stmt = (
            select(
                QuizSession.id.label("session_id"),
                Quiz.id.label("quiz_id"),
                Quiz.title.label("quiz_name"),
                Quiz.subject.label("subject_name"),
                QuizSession.created_at.label("session_date"),
                func.coalesce(participants_subq.c.participants_count, 0).label("participants_count"),
                func.coalesce(average_score_subq.c.average_score, 0).label("average_score"),
            )
            .select_from(QuizSession)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .outerjoin(
                participants_subq,
                participants_subq.c.session_id == QuizSession.id,
            )
            .outerjoin(
                average_score_subq,
                average_score_subq.c.session_id == QuizSession.id,
            )
            .where(QuizSession.host_id == teacher_id)
            .order_by(QuizSession.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())

    async def get_teacher_session_results_detail(
            self,
            session_id: int,
            host_id: int | None = None,
    ):
        attempt_percentage_expr = case(
            (
                QuizAttempt.total_questions > 0,
                100.0 * QuizAttempt.score / QuizAttempt.total_questions,
            ),
            else_=None,
        )

        participants_subq = (
            select(
                SessionParticipant.session_id.label("session_id"),
                func.count(func.distinct(SessionParticipant.user_id)).label("participants_count"),
            )
            .group_by(SessionParticipant.session_id)
            .subquery()
        )

        score_stats_subq = (
            select(
                QuizAttempt.session_id.label("session_id"),
                func.coalesce(
                    func.round(
                        cast(
                            func.avg(attempt_percentage_expr).filter(QuizAttempt.finished.is_(True)),
                            Numeric(10, 2),
                        ),
                        2,
                    ),
                    0,
                ).label("average_score"),
                func.coalesce(
                    func.round(
                        cast(
                            func.max(attempt_percentage_expr).filter(QuizAttempt.finished.is_(True)),
                            Numeric(10, 2),
                        ),
                        2,
                    ),
                    0,
                ).label("highest_score"),
                func.coalesce(
                    func.round(
                        cast(
                            func.min(attempt_percentage_expr).filter(QuizAttempt.finished.is_(True)),
                            Numeric(10, 2),
                        ),
                        2,
                    ),
                    0,
                ).label("lowest_score"),
            )
            .group_by(QuizAttempt.session_id)
            .subquery()
        )

        question_order_subq = (
            select(
                Question.id.label("question_id"),
                Question.quiz_id.label("quiz_id"),
                func.row_number()
                .over(
                    partition_by=Question.quiz_id,
                    order_by=Question.id.asc(),
                )
                .label("question_number"),
            )
            .subquery()
        )

        question_accuracy_subq = (
            select(
                QuizAttempt.session_id.label("session_id"),
                AttemptAnswer.question_id.label("question_id"),
                func.coalesce(
                    func.round(
                        cast(
                            100.0
                            * func.count(AttemptAnswer.id).filter(AttemptAnswer.is_correct.is_(True))
                            / func.nullif(func.count(AttemptAnswer.id), 0),
                            Numeric(10, 2),
                        ),
                        2,
                    ),
                    0,
                ).label("question_accuracy"),
            )
            .select_from(QuizAttempt)
            .join(AttemptAnswer, AttemptAnswer.attempt_id == QuizAttempt.id)
            .where(QuizAttempt.finished.is_(True))
            .group_by(QuizAttempt.session_id, AttemptAnswer.question_id)
            .subquery()
        )

        hardest_question_ranked_subq = (
            select(
                question_accuracy_subq.c.session_id,
                question_accuracy_subq.c.question_id,
                question_accuracy_subq.c.question_accuracy,
                func.row_number()
                .over(
                    partition_by=question_accuracy_subq.c.session_id,
                    order_by=(
                        question_accuracy_subq.c.question_accuracy.asc(),
                        question_accuracy_subq.c.question_id.asc(),
                    ),
                )
                .label("rn"),
            )
            .subquery()
        )

        hardest_question_subq = (
            select(
                hardest_question_ranked_subq.c.session_id.label("session_id"),
                hardest_question_ranked_subq.c.question_id.label("question_id"),
                hardest_question_ranked_subq.c.question_accuracy.label("question_accuracy"),
            )
            .where(hardest_question_ranked_subq.c.rn == 1)
            .subquery()
        )

        stmt = (
            select(
                QuizSession.id.label("session_id"),
                Quiz.id.label("quiz_id"),
                Quiz.title.label("quiz_name"),
                Quiz.subject.label("subject_name"),
                cast(QuizSession.status, String).label("status"),
                QuizSession.created_at.label("session_date"),
                func.coalesce(participants_subq.c.participants_count, 0).label("participants_count"),
                QuizSession.duration_minutes.label("duration_minutes"),
                func.coalesce(score_stats_subq.c.average_score, 0).label("average_score"),
                func.coalesce(score_stats_subq.c.highest_score, 0).label("highest_score"),
                func.coalesce(score_stats_subq.c.lowest_score, 0).label("lowest_score"),
                question_order_subq.c.question_number.label("hardest_question_number"),
                func.coalesce(hardest_question_subq.c.question_accuracy, 0).label("hardest_question_accuracy"),
            )
            .select_from(QuizSession)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .outerjoin(
                participants_subq,
                participants_subq.c.session_id == QuizSession.id,
            )
            .outerjoin(
                score_stats_subq,
                score_stats_subq.c.session_id == QuizSession.id,
            )
            .outerjoin(
                hardest_question_subq,
                hardest_question_subq.c.session_id == QuizSession.id,
            )
            .outerjoin(
                question_order_subq,
                and_(
                    question_order_subq.c.question_id == hardest_question_subq.c.question_id,
                    question_order_subq.c.quiz_id == QuizSession.quiz_id,
                ),
            )
            .where(QuizSession.id == session_id)
        )

        if host_id is not None:
            stmt = stmt.where(QuizSession.host_id == host_id)

        result = await self.db.execute(stmt)
        row = result.mappings().first()

        if not row:
            return None

        return {
            "session_id": row["session_id"],
            "quiz_id": row["quiz_id"],
            "quiz_name": row["quiz_name"],
            "subject_name": row["subject_name"],
            "status": row["status"],
            "session_date": row["session_date"],
            "participants_count": int(row["participants_count"] or 0),
            "duration_minutes": int(row["duration_minutes"] or 0),
            "average_score": float(row["average_score"] or 0),
            "highest_score": float(row["highest_score"] or 0),
            "lowest_score": float(row["lowest_score"] or 0),
            "hardest_question_number": row["hardest_question_number"],
            "hardest_question_accuracy": float(row["hardest_question_accuracy"] or 0),
            "hardest_question_label": (
                f"Q{row['hardest_question_number']}"
                if row["hardest_question_number"] is not None
                else None
            ),
        }

    async def get_session_question_accuracy(
            self,
            session_id: int,
            host_id: int | None = None,
    ):
        question_order_subq = (
            select(
                Question.id.label("question_id"),
                Question.quiz_id.label("quiz_id"),
                func.row_number()
                .over(
                    partition_by=Question.quiz_id,
                    order_by=Question.id.asc(),
                )
                .label("question_number"),
            )
            .subquery()
        )

        accuracy_expr = func.coalesce(
            func.round(
                cast(
                    100.0
                    * func.count(AttemptAnswer.id).filter(AttemptAnswer.is_correct.is_(True))
                    / func.nullif(func.count(AttemptAnswer.id), 0),
                    Numeric(10, 2),
                ),
                2,
            ),
            0,
        )

        stmt = (
            select(
                AttemptAnswer.question_id.label("question_id"),
                question_order_subq.c.question_number.label("question_number"),
                func.concat("Q", question_order_subq.c.question_number).label("label"),

                func.count(AttemptAnswer.id).label("total_answers"),
                func.count(AttemptAnswer.id)
                .filter(AttemptAnswer.is_correct.is_(True))
                .label("correct_answers"),

                accuracy_expr.label("accuracy_percent"),

                case(
                    (accuracy_expr >= 75, "easy"),
                    (accuracy_expr >= 50, "medium"),
                    else_="hard",
                ).label("level"),
            )
            .select_from(QuizSession)
            .join(QuizAttempt, QuizAttempt.session_id == QuizSession.id)
            .join(AttemptAnswer, AttemptAnswer.attempt_id == QuizAttempt.id)
            .join(
                question_order_subq,
                and_(
                    question_order_subq.c.question_id == AttemptAnswer.question_id,
                    question_order_subq.c.quiz_id == QuizSession.quiz_id,
                ),
            )
            .where(
                QuizSession.id == session_id,
                QuizAttempt.finished.is_(True),
            )
            .group_by(
                AttemptAnswer.question_id,
                question_order_subq.c.question_number,
            )
            .order_by(question_order_subq.c.question_number.asc())
        )

        if host_id is not None:
            stmt = stmt.where(QuizSession.host_id == host_id)

        result = await self.db.execute(stmt)
        rows = result.mappings().all()

        return [
            {
                "question_id": row["question_id"],
                "question_number": int(row["question_number"]),
                "label": row["label"],
                "total_answers": int(row["total_answers"] or 0),
                "correct_answers": int(row["correct_answers"] or 0),
                "accuracy_percent": float(row["accuracy_percent"] or 0),
                "level": row["level"],
            }
            for row in rows
        ]
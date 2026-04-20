from datetime import datetime, timedelta, timezone, UTC

from fastapi_pagination import paginate
from sqlalchemy import func, cast, literal, JSON, and_, Numeric, case, String, exists, distinct, or_
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuizSession, QuizAttempt, SessionParticipant, Option, Question, AttemptAnswer, QuestionImage, \
    Quiz, User, StudentGroupMember, StudentGroup
from app.models.quiz.real_time_quiz import QuizSessionGroup
from app.models.quiz.real_time_quiz.quiz_session import SessionStatus
from app.schemas.statistic.teacher_statistics import WeakStudentsFilterParams

UZT = timezone(timedelta(hours=5))


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

    async def finish_session(self, quiz_session: QuizSession) -> QuizSession:
        now = datetime.now(UZT).replace(tzinfo=None)
        quiz_session.status = SessionStatus.finished
        quiz_session.finished_at = now
        await self.db.flush()

        return quiz_session

    async def get_running_sessions_by_host(self, host_id: int):

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
        now = datetime.now(UZT).replace(tzinfo=None)
        quiz_session.status = SessionStatus.running
        quiz_session.started_at = now
        quiz_session.finished_at = now + timedelta(minutes=quiz_session.duration_minutes)
        await self.db.flush()
        return quiz_session

    async def get_single_player_session(self, session_id: int, host_id: int | None = None):
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

    async def player_session(self, session_id: int, host_id: int | None = None, status=SessionStatus.running):
        stmt = (
            select(QuizSession)
            .where(
                QuizSession.id == session_id
            )
        )

        if host_id:
            stmt = stmt.where(QuizSession.host_id == host_id)

        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_session_questions_with_answers(self, session_id: int, host_id: int):

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

    async def get_personal_quiz_session_history(self, user_id: int, search: str | None):
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
                func.abs(
                    func.extract(
                        "epoch",
                        QuizAttempt.finished_at - QuizSession.started_at,
                    )
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

    async def get_teacher_session_results_detail(self, session_id: int, host_id: int | None = None):
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

    async def get_session_question_accuracy(self, session_id: int, host_id: int | None = None):
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

    async def is_user_in_session_groups(self, session_id: int, user_id: int) -> bool:
        stmt = select(
            exists().where(
                and_(
                    QuizSessionGroup.session_id == session_id,
                    QuizSessionGroup.group_id == StudentGroupMember.group_id,
                    StudentGroupMember.student_id == user_id,
                )
            )
        )

        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def teacher_overview_cards(self, teacher_id: int):
        now = datetime.utcnow()

        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_start

        teacher_groups_sq = (
            select(StudentGroup.id.label("group_id"))
            .where(StudentGroup.teacher_id == teacher_id)
            .subquery()
        )

        # 2) teacher group-laridagi studentlar
        teacher_students_sq = (
            select(distinct(StudentGroupMember.student_id).label("student_id"))
            .select_from(StudentGroupMember)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == StudentGroupMember.group_id,
            )
            .subquery()
        )

        # 3) teacher group-lariga biriktirilgan sessionlar
        teacher_sessions_sq = (
            select(distinct(QuizSessionGroup.session_id).label("session_id"))
            .select_from(QuizSessionGroup)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == QuizSessionGroup.group_id,
            )
            .subquery()
        )

        # 4) teacher scope ichidagi participantlar
        participants_sq = (
            select(
                SessionParticipant.id.label("participant_id"),
                SessionParticipant.user_id.label("student_id"),
                SessionParticipant.session_id.label("session_id"),
                SessionParticipant.joined_at.label("joined_at"),
            )
            .select_from(SessionParticipant)
            .where(
                SessionParticipant.user_id.in_(select(teacher_students_sq.c.student_id)),
                SessionParticipant.session_id.in_(select(teacher_sessions_sq.c.session_id)),
            )
            .subquery()
        )

        # 5) attemptlar shu scope bo'yicha
        attempts_sq = (
            select(
                QuizAttempt.id.label("attempt_id"),
                QuizAttempt.participant_id.label("participant_id"),
                QuizAttempt.session_id.label("session_id"),
                QuizAttempt.score.label("score"),
                QuizAttempt.total_questions.label("total_questions"),
                QuizAttempt.finished.label("finished"),
                QuizAttempt.finished_at.label("finished_at"),
            )
            .select_from(QuizAttempt)
            .join(
                participants_sq,
                participants_sq.c.participant_id == QuizAttempt.participant_id,
            )
            .where(
                QuizAttempt.session_id.in_(select(teacher_sessions_sq.c.session_id))
            )
            .subquery()
        )

        # jami studentlar
        total_students_stmt = select(
            func.count(distinct(teacher_students_sq.c.student_id))
        )

        total_students = (await self.db.execute(total_students_stmt)).scalar() or 0

        # oldingi haftadagi jami studentlar bilan solishtirish uchun
        # bu yerda group member count odatda statik bo'ladi, lekin rasmga mos trend uchun
        # "hafta ichida teacher scope sessionlarida qatnashgan unique studentlar" ni olish foydaliroq
        current_students_stmt = select(
            func.count(distinct(participants_sq.c.student_id))
        ).where(
            participants_sq.c.joined_at >= week_start
        )

        prev_students_stmt = select(
            func.count(distinct(participants_sq.c.student_id))
        ).where(
            participants_sq.c.joined_at >= prev_week_start,
            participants_sq.c.joined_at < prev_week_end,
        )

        current_students = (await self.db.execute(current_students_stmt)).scalar() or 0
        prev_students = (await self.db.execute(prev_students_stmt)).scalar() or 0

        # bu hafta yakunlangan testlar
        current_completed_tests_stmt = select(
            func.count(attempts_sq.c.attempt_id)
        ).where(
            attempts_sq.c.finished.is_(True),
            attempts_sq.c.finished_at >= week_start,
        )

        prev_completed_tests_stmt = select(
            func.count(attempts_sq.c.attempt_id)
        ).where(
            attempts_sq.c.finished.is_(True),
            attempts_sq.c.finished_at >= prev_week_start,
            attempts_sq.c.finished_at < prev_week_end,
        )

        current_completed_tests = (
                                      await self.db.execute(current_completed_tests_stmt)
                                  ).scalar() or 0

        prev_completed_tests = (
                                   await self.db.execute(prev_completed_tests_stmt)
                               ).scalar() or 0

        # bu hafta o'rtacha ball
        score_expr = case(
            (
                and_(
                    attempts_sq.c.finished.is_(True),
                    attempts_sq.c.total_questions > 0,
                ),
                100.0 * attempts_sq.c.score / attempts_sq.c.total_questions,
            ),
            else_=None,
        )

        current_avg_score_stmt = select(
            func.avg(score_expr)
        ).where(
            attempts_sq.c.finished.is_(True),
            attempts_sq.c.finished_at >= week_start,
        )

        prev_avg_score_stmt = select(
            func.avg(score_expr)
        ).where(
            attempts_sq.c.finished.is_(True),
            attempts_sq.c.finished_at >= prev_week_start,
            attempts_sq.c.finished_at < prev_week_end,
        )

        current_avg_score = (
                                await self.db.execute(current_avg_score_stmt)
                            ).scalar() or 0.0

        prev_avg_score = (
                             await self.db.execute(prev_avg_score_stmt)
                         ).scalar() or 0.0

        # faol o'quvchilar: bu hafta kamida 1 ta sessionga kirgan yoki test tugatgan unique studentlar
        current_active_students_stmt = select(
            func.count(distinct(participants_sq.c.student_id))
        ).where(
            participants_sq.c.joined_at >= week_start
        )

        prev_active_students_stmt = select(
            func.count(distinct(participants_sq.c.student_id))
        ).where(
            participants_sq.c.joined_at >= prev_week_start,
            participants_sq.c.joined_at < prev_week_end,
        )

        current_active_students = (
                                      await self.db.execute(current_active_students_stmt)
                                  ).scalar() or 0

        prev_active_students = (
                                   await self.db.execute(prev_active_students_stmt)
                               ).scalar() or 0

        def calc_change(current: float | int, previous: float | int) -> tuple[int, str]:
            if previous in (0, None):
                if current > 0:
                    return 100, "up"
                return 0, "same"

            diff = ((current - previous) / previous) * 100

            if diff > 0:
                return round(diff), "up"
            if diff < 0:
                return round(diff), "down"
            return 0, "same"

        total_students_change, total_students_trend = calc_change(current_students, prev_students)
        completed_tests_change, completed_tests_trend = calc_change(
            current_completed_tests, prev_completed_tests
        )
        avg_score_change, avg_score_trend = calc_change(
            current_avg_score, prev_avg_score
        )
        active_students_change, active_students_trend = calc_change(
            current_active_students, prev_active_students
        )

        return {
            "total_students": {
                "value": total_students,
                "change_percent": total_students_change,
                "trend": total_students_trend,
                "label": "Jami o'quvchilar",
            },
            "completed_tests_this_week": {
                "value": current_completed_tests,
                "change_percent": completed_tests_change,
                "trend": completed_tests_trend,
                "label": "Bu hafta yakunlangan testlar",
            },
            "average_score_this_week": {
                "value": float(current_avg_score or 0),
                "change_percent": avg_score_change,
                "trend": avg_score_trend,
                "label": "O'rtacha ball",
            },
            "active_students_this_week": {
                "value": current_active_students,
                "change_percent": active_students_change,
                "trend": active_students_trend,
                "label": "Faol o'quvchilar",
            },
        }

    async def teacher_activity_chart(self, teacher_id: int):
        now = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
        start_date = (now - timedelta(days=6)).date()
        prev_start_date = start_date - timedelta(days=7)
        prev_end_date = start_date - timedelta(days=1)

        # 1) Teacher group-lari
        teacher_groups_sq = (
            select(StudentGroup.id.label("group_id"))
            .where(StudentGroup.teacher_id == teacher_id)
            .subquery()
        )

        # 2) Teacher group-lariga biriktirilgan sessionlar
        teacher_sessions_sq = (
            select(distinct(QuizSessionGroup.session_id).label("session_id"))
            .select_from(QuizSessionGroup)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == QuizSessionGroup.group_id,
            )
            .subquery()
        )

        # 3) Teacher scope ichidagi participantlar
        participants_sq = (
            select(
                SessionParticipant.id.label("participant_id"),
                SessionParticipant.user_id.label("student_id"),
                SessionParticipant.session_id.label("session_id"),
                SessionParticipant.joined_at.label("joined_at"),
            )
            .select_from(SessionParticipant)
            .where(
                SessionParticipant.session_id.in_(
                    select(teacher_sessions_sq.c.session_id)
                )
            )
            .subquery()
        )

        # 4) Teacher scope ichidagi finished attemptlar
        # Chart uchun kunni finished_at bo‘yicha olamiz
        score_percent_expr = case(
            (
                and_(
                    QuizAttempt.finished.is_(True),
                    QuizAttempt.total_questions > 0,
                ),
                100.0 * QuizAttempt.score / QuizAttempt.total_questions,
            ),
            else_=None,
        )

        daily_stmt = (
            select(
                func.date(QuizAttempt.finished_at).label("activity_date"),
                func.count(QuizAttempt.id).label("submitted_tests"),
                func.coalesce(func.avg(score_percent_expr), 0.0).label("average_score"),
                func.count(distinct(participants_sq.c.student_id)).label("participated_students"),
            )
            .select_from(QuizAttempt)
            .join(
                participants_sq,
                participants_sq.c.participant_id == QuizAttempt.participant_id,
            )
            .where(
                QuizAttempt.finished.is_(True),
                QuizAttempt.finished_at.is_not(None),
                func.date(QuizAttempt.finished_at) >= start_date,
                func.date(QuizAttempt.finished_at) <= now.date(),
                QuizAttempt.session_id.in_(select(teacher_sessions_sq.c.session_id)),
            )
            .group_by(func.date(QuizAttempt.finished_at))
            .order_by(func.date(QuizAttempt.finished_at))
        )

        result = await self.db.execute(daily_stmt)
        rows = result.mappings().all()

        row_map = {
            row["activity_date"]: {
                "submitted_tests": row["submitted_tests"] or 0,
                "average_score": float(row["average_score"] or 0),
                "participated_students": row["participated_students"] or 0,
            }
            for row in rows
        }

        day_labels = {
            0: "Du",
            1: "Se",
            2: "Ch",
            3: "Pa",
            4: "Ju",
            5: "Sh",
            6: "Ya",
        }

        items = []
        current_total_tests = 0

        for i in range(7):
            current_day = start_date + timedelta(days=i)
            payload = row_map.get(
                current_day,
                {
                    "submitted_tests": 0,
                    "average_score": 0.0,
                    "participated_students": 0,
                },
            )

            current_total_tests += payload["submitted_tests"]

            items.append(
                {
                    "day_key": day_labels[current_day.weekday()],
                    "date": current_day,
                    "submitted_tests": payload["submitted_tests"],
                    "average_score": payload["average_score"],
                    "participated_students": payload["participated_students"],
                }
            )

        # 5) Trend: oxirgi 7 kunlik submitted_tests vs undan oldingi 7 kun
        prev_tests_stmt = (
            select(func.count(QuizAttempt.id))
            .select_from(QuizAttempt)
            .join(
                participants_sq,
                participants_sq.c.participant_id == QuizAttempt.participant_id,
            )
            .where(
                QuizAttempt.finished.is_(True),
                QuizAttempt.finished_at.is_not(None),
                func.date(QuizAttempt.finished_at) >= prev_start_date,
                func.date(QuizAttempt.finished_at) <= prev_end_date,
                QuizAttempt.session_id.in_(select(teacher_sessions_sq.c.session_id)),
            )
        )

        prev_total_tests = (await self.db.execute(prev_tests_stmt)).scalar() or 0

        def calc_change(current: int, previous: int) -> int:
            if previous == 0:
                return 100 if current > 0 else 0
            return round(((current - previous) / previous) * 100)

        trend_percent = calc_change(current_total_tests, prev_total_tests)
        return {
            "trend_percent": trend_percent,
            "trend_label": "bu hafta",
            "items": items,
        }

    async def teacher_analytics_overview(self, teacher_id: int):
        now = datetime.utcnow()

        week_start = now - timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        prev_week_start = week_start - timedelta(days=7)
        prev_week_end = week_start

        # 1) Teacher group-lari
        teacher_groups_sq = (
            select(StudentGroup.id.label("group_id"))
            .where(StudentGroup.teacher_id == teacher_id)
            .subquery()
        )

        # 2) Teacher group-laridagi studentlar
        teacher_students_sq = (
            select(distinct(StudentGroupMember.student_id).label("student_id"))
            .select_from(StudentGroupMember)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == StudentGroupMember.group_id,
            )
            .subquery()
        )

        # 3) Teacher group-lariga biriktirilgan sessionlar
        teacher_sessions_sq = (
            select(distinct(QuizSessionGroup.session_id).label("session_id"))
            .select_from(QuizSessionGroup)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == QuizSessionGroup.group_id,
            )
            .subquery()
        )

        # 4) Teacher scope ichidagi participantlar
        participants_sq = (
            select(
                SessionParticipant.id.label("participant_id"),
                SessionParticipant.user_id.label("student_id"),
                SessionParticipant.session_id.label("session_id"),
                SessionParticipant.joined_at.label("joined_at"),
            )
            .select_from(SessionParticipant)
            .where(
                SessionParticipant.user_id.in_(select(teacher_students_sq.c.student_id)),
                SessionParticipant.session_id.in_(select(teacher_sessions_sq.c.session_id)),
            )
            .subquery()
        )

        # 5) Teacher scope ichidagi attemptlar
        attempts_sq = (
            select(
                QuizAttempt.id.label("attempt_id"),
                QuizAttempt.participant_id.label("participant_id"),
                QuizAttempt.session_id.label("session_id"),
                QuizAttempt.score.label("score"),
                QuizAttempt.total_questions.label("total_questions"),
                QuizAttempt.finished.label("finished"),
                QuizAttempt.finished_at.label("finished_at"),
            )
            .select_from(QuizAttempt)
            .join(
                participants_sq,
                participants_sq.c.participant_id == QuizAttempt.participant_id,
            )
            .where(
                QuizAttempt.session_id.in_(select(teacher_sessions_sq.c.session_id))
            )
            .subquery()
        )

        score_percent_expr = case(
            (
                and_(
                    attempts_sq.c.finished.is_(True),
                    attempts_sq.c.total_questions > 0,
                ),
                100.0 * attempts_sq.c.score / attempts_sq.c.total_questions,
            ),
            else_=None,
        )

        # -----------------------------
        # CURRENT WEEK
        # -----------------------------
        current_avg_score_stmt = (
            select(func.coalesce(func.avg(score_percent_expr), 0.0))
            .where(
                attempts_sq.c.finished.is_(True),
                attempts_sq.c.finished_at >= week_start,
            )
        )

        current_completed_tests_stmt = (
            select(func.count(attempts_sq.c.attempt_id))
            .where(
                attempts_sq.c.finished.is_(True),
                attempts_sq.c.finished_at >= week_start,
            )
        )

        current_active_students_stmt = (
            select(func.count(distinct(participants_sq.c.student_id)))
            .where(
                participants_sq.c.joined_at >= week_start,
            )
        )

        # -----------------------------
        # PREVIOUS WEEK
        # -----------------------------
        prev_avg_score_stmt = (
            select(func.coalesce(func.avg(score_percent_expr), 0.0))
            .where(
                attempts_sq.c.finished.is_(True),
                attempts_sq.c.finished_at >= prev_week_start,
                attempts_sq.c.finished_at < prev_week_end,
            )
        )

        prev_completed_tests_stmt = (
            select(func.count(attempts_sq.c.attempt_id))
            .where(
                attempts_sq.c.finished.is_(True),
                attempts_sq.c.finished_at >= prev_week_start,
                attempts_sq.c.finished_at < prev_week_end,
            )
        )

        prev_active_students_stmt = (
            select(func.count(distinct(participants_sq.c.student_id)))
            .where(
                participants_sq.c.joined_at >= prev_week_start,
                participants_sq.c.joined_at < prev_week_end,
            )
        )

        current_avg_score = (await self.db.execute(current_avg_score_stmt)).scalar() or 0.0
        current_completed_tests = (await self.db.execute(current_completed_tests_stmt)).scalar() or 0
        current_active_students = (await self.db.execute(current_active_students_stmt)).scalar() or 0

        prev_avg_score = (await self.db.execute(prev_avg_score_stmt)).scalar() or 0.0
        prev_completed_tests = (await self.db.execute(prev_completed_tests_stmt)).scalar() or 0
        prev_active_students = (await self.db.execute(prev_active_students_stmt)).scalar() or 0

        # -----------------------------
        # WEAK TOPICS (avg < 50)
        # faqat teacher scope ichidagi answerlar
        # -----------------------------
        topic_avg_expr = func.avg(
            case(
                (AttemptAnswer.is_correct.is_(True), 100.0),
                else_=0.0,
            )
        )

        weak_topics_stmt = (
            select(func.count())
            .select_from(
                select(
                    Question.topic.label("topic_name")
                )
                .select_from(AttemptAnswer)
                .join(
                    attempts_sq,
                    attempts_sq.c.attempt_id == AttemptAnswer.attempt_id,
                )
                .join(
                    Question,
                    Question.id == AttemptAnswer.question_id,
                )
                .where(
                    attempts_sq.c.finished.is_(True),
                    Question.topic.is_not(None),
                )
                .group_by(Question.topic)
                .having(topic_avg_expr < 50)
                .subquery()
            )
        )

        weak_topics_count = (await self.db.execute(weak_topics_stmt)).scalar() or 0

        # -----------------------------
        # TREND CALCULATOR
        # -----------------------------
        def calc_change(current: float | int, previous: float | int) -> tuple[int, str]:
            if previous in (0, None):
                if current > 0:
                    return 100, "up"
                return 0, "same"

            diff = ((current - previous) / previous) * 100

            if diff > 0:
                return round(diff), "up"
            if diff < 0:
                return abs(round(diff)), "down"
            return 0, "same"

        avg_score_change, avg_score_trend = calc_change(current_avg_score, prev_avg_score)
        completed_tests_change, completed_tests_trend = calc_change(
            current_completed_tests, prev_completed_tests
        )
        active_students_change, active_students_trend = calc_change(
            current_active_students, prev_active_students
        )

        return {
            "average_score": {
                "value": float(current_avg_score),
                "change_percent": avg_score_change,
                "trend": avg_score_trend,
                "label": "O'rtacha ball",
            },
            "completed_tests": {
                "value": current_completed_tests,
                "change_percent": completed_tests_change,
                "trend": completed_tests_trend,
                "label": "Yakunlangan testlar",
            },
            "active_students": {
                "value": current_active_students,
                "change_percent": active_students_change,
                "trend": active_students_trend,
                "label": "Faol o'quvchilar",
            },
            "weak_topics": {
                "value": weak_topics_count,
                "change_percent": 0,
                "trend": "warning",
                "label": "Zaif mavzular",
                "sub_label": "Diqqat talab etadi",
            },
        }

    async def teacher_group_results(self, teacher_id: int):
        # 1) Teacherning group-lari
        teacher_groups_sq = (
            select(
                StudentGroup.id.label("group_id"),
                StudentGroup.name.label("group_name"),
            )
            .where(StudentGroup.teacher_id == teacher_id)
            .subquery()
        )

        # 2) Har groupdagi jami studentlar soni
        group_students_count_sq = (
            select(
                StudentGroupMember.group_id.label("group_id"),
                func.count(distinct(StudentGroupMember.student_id)).label("student_count"),
            )
            .select_from(StudentGroupMember)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == StudentGroupMember.group_id,
            )
            .group_by(StudentGroupMember.group_id)
            .subquery()
        )

        # 3) Har groupga biriktirilgan sessionlar
        group_sessions_sq = (
            select(
                QuizSessionGroup.group_id.label("group_id"),
                QuizSessionGroup.session_id.label("session_id"),
            )
            .select_from(QuizSessionGroup)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == QuizSessionGroup.group_id,
            )
            .subquery()
        )

        # 4) Groupdagi student o‘sha group sessionida qatnashgan participantlar
        # Muhim: student shu group a'zosi bo‘lishi va session ham shu groupga biriktirilgan bo‘lishi kerak
        group_participants_sq = (
            select(
                group_sessions_sq.c.group_id.label("group_id"),
                SessionParticipant.id.label("participant_id"),
                SessionParticipant.user_id.label("student_id"),
                SessionParticipant.session_id.label("session_id"),
            )
            .select_from(group_sessions_sq)
            .join(
                SessionParticipant,
                SessionParticipant.session_id == group_sessions_sq.c.session_id,
            )
            .join(
                StudentGroupMember,
                and_(
                    StudentGroupMember.group_id == group_sessions_sq.c.group_id,
                    StudentGroupMember.student_id == SessionParticipant.user_id,
                ),
            )
            .subquery()
        )

        # 5) Finished attemptlar
        average_score_expr = func.coalesce(
            func.round(
                cast(
                    func.avg(
                        case(
                            (
                                and_(
                                    QuizAttempt.finished.is_(True),
                                    QuizAttempt.total_questions > 0,
                                ),
                                100.0 * QuizAttempt.score / QuizAttempt.total_questions,
                            ),
                            else_=None,
                        )
                    ),
                    Numeric(10, 2),
                ),
                2,
            ),
            0.0,
        ).label("average_score")

        tests_count_expr = func.coalesce(
            func.count(distinct(QuizAttempt.id)).filter(
                QuizAttempt.finished.is_(True)
            ),
            0,
        ).label("tests_count")

        performance_level_expr = case(
            (average_score_expr >= 80, literal("high")),
            (average_score_expr >= 70, literal("good")),
            (average_score_expr >= 50, literal("medium")),
            else_=literal("low"),
        ).label("performance_level")

        performance_color_expr = case(
            (average_score_expr >= 75, literal("green")),
            (average_score_expr >= 50, literal("orange")),
            else_=literal("red"),
        ).label("performance_color")

        base_cte = (
            select(
                teacher_groups_sq.c.group_id,
                teacher_groups_sq.c.group_name,
                func.coalesce(group_students_count_sq.c.student_count, 0).label("student_count"),
                tests_count_expr,
                average_score_expr,
                average_score_expr.label("progress_percent"),
                performance_level_expr,
                performance_color_expr,
            )
            .select_from(teacher_groups_sq)
            .outerjoin(
                group_students_count_sq,
                group_students_count_sq.c.group_id == teacher_groups_sq.c.group_id,
            )
            .outerjoin(
                group_participants_sq,
                group_participants_sq.c.group_id == teacher_groups_sq.c.group_id,
            )
            .outerjoin(
                QuizAttempt,
                and_(
                    QuizAttempt.participant_id == group_participants_sq.c.participant_id,
                    QuizAttempt.session_id == group_participants_sq.c.session_id,
                ),
            )
            .group_by(
                teacher_groups_sq.c.group_id,
                teacher_groups_sq.c.group_name,
                group_students_count_sq.c.student_count,
            )
            .cte("group_stats")
        )

        rank_expr = func.dense_rank().over(
            order_by=(
                base_cte.c.average_score.desc(),
                base_cte.c.tests_count.desc(),
                base_cte.c.student_count.desc(),
                base_cte.c.group_id.asc(),
            )
        ).label("rank")

        stmt = (
            select(
                rank_expr,
                base_cte.c.group_id,
                base_cte.c.group_name,
                base_cte.c.student_count,
                base_cte.c.tests_count,
                base_cte.c.average_score,
                base_cte.c.progress_percent,
                base_cte.c.performance_level,
                base_cte.c.performance_color,
            )
            .order_by(rank_expr.asc(), base_cte.c.group_name.asc())
        )

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())

    async def teacher_weak_topics(self, teacher_id: int):
        # 1) Teacher group-lari
        teacher_groups_sq = (
            select(StudentGroup.id.label("group_id"))
            .where(StudentGroup.teacher_id == teacher_id)
            .subquery()
        )

        # 2) Teacher group-laridagi studentlar
        teacher_students_sq = (
            select(distinct(StudentGroupMember.student_id).label("student_id"))
            .select_from(StudentGroupMember)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == StudentGroupMember.group_id,
            )
            .subquery()
        )

        # 3) Teacher group-lariga biriktirilgan sessionlar
        teacher_sessions_sq = (
            select(distinct(QuizSessionGroup.session_id).label("session_id"))
            .select_from(QuizSessionGroup)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == QuizSessionGroup.group_id,
            )
            .subquery()
        )

        # 4) Teacher scope participantlar
        participants_sq = (
            select(
                SessionParticipant.id.label("participant_id"),
                SessionParticipant.user_id.label("student_id"),
                SessionParticipant.session_id.label("session_id"),
            )
            .select_from(SessionParticipant)
            .where(
                SessionParticipant.user_id.in_(select(teacher_students_sq.c.student_id)),
                SessionParticipant.session_id.in_(select(teacher_sessions_sq.c.session_id)),
            )
            .subquery()
        )

        # 5) Teacher scope finished attemptlar
        attempts_sq = (
            select(
                QuizAttempt.id.label("attempt_id"),
                QuizAttempt.participant_id.label("participant_id"),
                QuizAttempt.session_id.label("session_id"),
                QuizAttempt.finished.label("finished"),
            )
            .select_from(QuizAttempt)
            .join(
                participants_sq,
                participants_sq.c.participant_id == QuizAttempt.participant_id,
            )
            .where(
                QuizAttempt.session_id.in_(select(teacher_sessions_sq.c.session_id)),
                QuizAttempt.finished.is_(True),
            )
            .subquery()
        )

        average_percent_expr = func.avg(
            case(
                (AttemptAnswer.is_correct.is_(True), 100.0),
                else_=0.0,
            )
        )

        wrong_count_expr = func.count(AttemptAnswer.id).filter(
            AttemptAnswer.is_correct.is_(False)
        )

        severity_expr = case(
            (average_percent_expr < 25, literal("critical")),
            else_=literal("warning"),
        ).label("severity")

        color_expr = case(
            (average_percent_expr < 40, literal("red")),
            (average_percent_expr < 60, literal("orange")),
            else_=literal("green"),
        ).label("color")

        base_cte = (
            select(
                Question.topic.label("topic_name"),
                # Agar senda Question.subject bo'lsa shuni ishlat
                Question.subject.label("subject_name"),
                func.coalesce(wrong_count_expr, 0).label("wrong_count"),
                func.coalesce(
                    func.round(
                        cast(average_percent_expr, Numeric(10, 2)),
                        2,
                    ),
                    0.0,
                ).label("average_percent"),
                severity_expr,
                color_expr,
            )
            .select_from(AttemptAnswer)
            .join(
                attempts_sq,
                attempts_sq.c.attempt_id == AttemptAnswer.attempt_id,
            )
            .join(
                Question,
                Question.id == AttemptAnswer.question_id,
            )
            .where(
                Question.topic.is_not(None),
            )
            .group_by(
                Question.topic,
                Question.subject,
            )
            .having(average_percent_expr < 40)
            .cte("weak_topics")
        )

        rank_expr = func.dense_rank().over(
            order_by=(
                base_cte.c.wrong_count.desc(),
                base_cte.c.average_percent.asc(),
                base_cte.c.topic_name.asc(),
            )
        ).label("rank")

        stmt = (
            select(
                rank_expr,
                base_cte.c.topic_name,
                base_cte.c.subject_name,
                base_cte.c.wrong_count,
                base_cte.c.average_percent,
                base_cte.c.average_percent.label("progress_percent"),
                base_cte.c.severity,
                base_cte.c.color,
            )
            .order_by(
                rank_expr.asc(),
                base_cte.c.topic_name.asc(),
            )
        )

        result = await self.db.execute(stmt)
        rows = result.mappings().all()
        return paginate(rows)

    async def teacher_weak_students(self, teacher_id: int, filters: WeakStudentsFilterParams, ):
        # 1) Teacher group-lari
        teacher_groups_stmt = (
            select(
                StudentGroup.id.label("group_id"),
                StudentGroup.name.label("group_name"),
            )
            .where(StudentGroup.teacher_id == teacher_id)
        )

        if filters.group_id:
            teacher_groups_stmt = teacher_groups_stmt.where(
                StudentGroup.id == filters.group_id
            )

        teacher_groups_sq = teacher_groups_stmt.subquery()

        # 2) Teacher group-laridagi studentlar
        teacher_students_sq = (
            select(
                StudentGroupMember.student_id.label("student_id"),
                func.array_agg(
                    distinct(teacher_groups_sq.c.group_name)
                ).label("group_names"),
            )
            .select_from(StudentGroupMember)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == StudentGroupMember.group_id,
            )
            .group_by(StudentGroupMember.student_id)
            .subquery()
        )

        # 3) Teacher group-lariga biriktirilgan sessionlar
        teacher_sessions_sq = (
            select(
                distinct(QuizSessionGroup.session_id).label("session_id")
            )
            .select_from(QuizSessionGroup)
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.group_id == QuizSessionGroup.group_id,
            )
            .subquery()
        )

        full_name_search_expr = func.trim(
            func.concat(
                func.coalesce(User.first_name, ""),
                literal(" "),
                func.coalesce(User.last_name, ""),
            )
        )
        full_name_expr = full_name_search_expr.label("full_name")

        average_score_raw = func.avg(
            case(
                (
                    and_(
                        QuizAttempt.finished.is_(True),
                        QuizAttempt.total_questions > 0,
                    ),
                    100.0 * QuizAttempt.score / QuizAttempt.total_questions,
                ),
                else_=None,
            )
        )

        average_score_expr = func.coalesce(
            func.round(
                cast(average_score_raw, Numeric(10, 2)),
                2,
            ),
            0.0,
        ).label("average_score")

        tests_count_expr = func.coalesce(
            func.count(distinct(QuizAttempt.id)).filter(
                QuizAttempt.finished.is_(True)
            ),
            0,
        ).label("tests_count")

        last_activity_expr = func.max(
            func.coalesce(
                QuizAttempt.finished_at,
                QuizSession.created_at,
                SessionParticipant.joined_at,
            )
        ).label("last_activity")

        performance_color_expr = case(
            (average_score_expr < 50, literal("red")),
            (average_score_expr < 75, literal("orange")),
            else_=literal("yellow"),
        ).label("performance_color")

        stmt = (
            select(
                User.id.label("student_id"),
                User.profile_image,
                full_name_expr,
                User.username.label("username"),
                teacher_students_sq.c.group_names.label("group_names"),
                average_score_expr,
                tests_count_expr,
                last_activity_expr,
                performance_color_expr,
            )
            .select_from(teacher_students_sq)
            .join(User, User.id == teacher_students_sq.c.student_id)
            .outerjoin(
                SessionParticipant,
                and_(
                    SessionParticipant.user_id == User.id,
                    SessionParticipant.session_id.in_(
                        select(teacher_sessions_sq.c.session_id)
                    ),
                ),
            )
            .outerjoin(
                QuizSession,
                QuizSession.id == SessionParticipant.session_id,
            )
            .outerjoin(
                QuizAttempt,
                and_(
                    QuizAttempt.participant_id == SessionParticipant.id,
                    QuizAttempt.session_id == QuizSession.id,
                ),
            )
            .group_by(
                User.id,
                User.first_name,
                User.last_name,
                User.username,
                teacher_students_sq.c.group_names,
            )
        )

        if filters.search:
            search = f"%{filters.search}%"
            stmt = stmt.where(
                or_(
                    User.first_name.ilike(search),
                    User.last_name.ilike(search),
                    User.username.ilike(search),
                    full_name_search_expr.ilike(search),
                )
            )

        if filters.min_score is not None:
            stmt = stmt.having(average_score_expr >= filters.min_score)

        if filters.max_score is not None:
            stmt = stmt.having(average_score_expr <= filters.max_score)

        stmt = stmt.order_by(
            average_score_expr.asc(),
            tests_count_expr.asc(),
            last_activity_expr.asc().nulls_last(),
            full_name_expr.asc(),
        )

        result = await self.db.execute(stmt)
        rows = result.mappings().all()
        return paginate(rows)

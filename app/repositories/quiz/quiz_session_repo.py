from datetime import UTC, datetime, timedelta
from sqlalchemy import func, cast, literal, JSON,and_
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuizSession, QuizAttempt, SessionParticipant, Option, Question, AttemptAnswer, QuestionImage,Quiz,User


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

    async def start_session(self, quiz_session: QuizSession) -> QuizSession:
        now = datetime.now(UTC)
        quiz_session.status = "running"
        quiz_session.started_at = now
        quiz_session.finished_at = now + timedelta(minutes=quiz_session.duration_minutes)
        await self.db.flush()
        return quiz_session

    async def get_single_player_session(self, session_id: int, host_id: int,status="running") -> QuizSession | None:
        stmt = select(QuizSession).where(
            QuizSession.id == session_id,
            QuizSession.host_id == host_id,
            QuizSession.status == status
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

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
                QuizSession.id == session_id,
                QuizSession.host_id == host_id,
            )
            .order_by(Question.id.asc())
        )

        res = await self.db.execute(stmt)
        return res.mappings().all()

    async def get_personal_quiz_session_history(self, user_id: int,search: str):
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
                func.count()
                .over(partition_by=QuizSession.id)
                .label("participant_count"),
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
        return result.mappings().all()

    async def get_session_participant_rank_list(self, session_id: int,user_id:int):
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
            .order_by(QuizAttempt.score.desc(),  QuizAttempt.finished_at.asc())
        )

        result = await self.db.execute(stmt)
        return result.mappings().all()

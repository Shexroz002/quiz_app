from typing import Any, Sequence
from fastapi_pagination import Page, add_pagination, paginate
from sqlalchemy import select, func, case, literal, and_, or_, cast, Numeric, text, String, distinct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.teacher.my_student.params.student_filter import StudentFilterParams
from app.models import Contact, User, QuizAttempt, QuizSession, SessionParticipant, StudentGroup, AttemptAnswer, \
    Question, Quiz, StudentGroupMember
from app.models.quiz.real_time_quiz import QuizSessionGroup
from app.repositories.base.base_repository import BaseRepository
from app.schemas.account.users import StudentStatus, TeacherStudentListParams
from sqlalchemy.dialects.postgresql import ARRAY, array


class ContactRepository(BaseRepository[Contact]):

    def __init__(self, db: AsyncSession):
        super().__init__(Contact, db)

    async def create_contact(self, user_id: int, friend_id: int, name: str):
        stmt = select(Contact).where(Contact.user_id == user_id, Contact.friend_id == friend_id)
        result = await self.db.execute(stmt)
        existing_contact = result.scalar_one_or_none()
        if existing_contact:
            return existing_contact

        contact = Contact(user_id=user_id, friend_id=friend_id, name=name)
        self.db.add(contact)
        return contact

    async def contact_list(self, contact_user_id: int) -> Sequence[Contact]:
        stmt = select(Contact).options(selectinload(Contact.friend)).where(Contact.user_id == contact_user_id)
        result = await self.db.execute(stmt)
        return paginate(result.scalars().all())

    async def _contact_list(self, contact_user_id: int) -> Sequence[Contact]:
        stmt = select(Contact).where(Contact.user_id == contact_user_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def contact_suggestions(self, contact_user_id: int, search: str | None = None) -> Sequence[User]:
        contacts = await self._contact_list(contact_user_id)
        contact_ids = {contact.friend_id for contact in contacts}
        stmt = select(User).where(~User.id.in_(contact_ids.union({contact_user_id})))
        if search:
            search_term = f"%{search}%"

            stmt = stmt.where(
                or_(
                    User.username.ilike(search_term),
                    User.first_name.ilike(search_term),
                    User.last_name.ilike(search_term),
                    func.concat(User.first_name, " ", User.last_name).ilike(search_term)
                )
            )

        stmt = stmt.limit(10)
        result = await self.db.execute(stmt)
        return paginate(result.scalars().all())

    async def get_contact_by_id(self, friend_id: int, contact_user_id: int) -> Contact | None:
        stmt = select(Contact).where(Contact.user_id == contact_user_id, Contact.friend_id == friend_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def my_student_list(self, teacher_id: int, filters: StudentFilterParams):
        teacher_groups_sq = (
            select(StudentGroup.id, StudentGroup.name)
            .where(StudentGroup.teacher_id == teacher_id)
            .subquery()
        )

        # 2) Teacher grouplariga biriktirilgan sessionlar
        teacher_sessions_sq = (
            select(distinct(QuizSessionGroup.session_id).label("session_id"))
            .join(
                teacher_groups_sq,
                teacher_groups_sq.c.id == QuizSessionGroup.group_id,
            )
            .subquery()
        )

        # 3) Studentning teacher group-lari ro'yxati
        # Eslatma: StudentGroupMember -> o'zingdagi membership model bilan almashtir
        student_groups_sq = (
            select(
                StudentGroupMember.student_id.label("student_id"),
                func.array_agg(
                    distinct(StudentGroup.name)
                ).label("group_names"),
            )
            .select_from(StudentGroupMember)
            .join(
                StudentGroup,
                StudentGroup.id == StudentGroupMember.group_id,
            )
            .where(StudentGroup.teacher_id == teacher_id)
            .group_by(StudentGroupMember.student_id)
            .subquery()
        )

        full_name_expr = func.trim(
            func.concat(
                func.coalesce(User.first_name, ""),
                literal(" "),
                func.coalesce(User.last_name, ""),
            )
        ).label("full_name")

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

        status_expr = case(
            (
                last_activity_expr >= func.now() - text("INTERVAL '3 days'"),
                literal(StudentStatus.ACTIVE.value),
            ),
            else_=literal(StudentStatus.INACTIVE.value),
        ).label("status")

        stmt = (
            select(
                User.id.label("student_id"),
                User.username.label("username"),
                User.profile_image.label("profile_image"),
                full_name_expr,

                # oldingi class_name o'rniga list
                func.coalesce(
                    student_groups_sq.c.group_names,
                    cast(array([]), ARRAY(String)),
                ).label("group_names"),

                average_score_expr,
                tests_count_expr,
                last_activity_expr,
                status_expr,
            )
            .select_from(Contact)
            .join(User, User.id == Contact.friend_id)

            # studentning teacher group listi
            .outerjoin(
                student_groups_sq,
                student_groups_sq.c.student_id == User.id,
            )

            # faqat teacher group sessionlari ichidagi participant
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
            .where(Contact.user_id == teacher_id)
            .group_by(
                User.id,
                User.username,
                User.profile_image,
                User.first_name,
                User.last_name,
                student_groups_sq.c.group_names,
            )
        )

        if filters.search:
            search = f"%{filters.search}%"
            stmt = stmt.where(
                or_(
                    User.first_name.ilike(search),
                    User.last_name.ilike(search),
                    full_name_expr.ilike(search),
                )
            )

        # endi class_name emas, group bo'yicha filter kerak bo'lsa keyin alohida qilinadi
        # eski education_level filter saqlamoqchi bo'lsang, alohida maydon sifatida responsega qaytar

        if filters.min_score is not None:
            stmt = stmt.having(average_score_expr >= filters.min_score)

        if filters.max_score is not None:
            stmt = stmt.having(average_score_expr <= filters.max_score)

        if filters.status:
            stmt = stmt.having(status_expr == filters.status)

        ordering_map = {
            "average_score": average_score_expr.desc(),
            "-average_score": average_score_expr.asc(),
            "tests_count": tests_count_expr.desc(),
            "-tests_count": tests_count_expr.asc(),
            "last_activity": last_activity_expr.desc(),
            "-last_activity": last_activity_expr.asc(),
            "full_name": full_name_expr.asc(),
            "-full_name": full_name_expr.desc(),
        }

        stmt = stmt.order_by(
            ordering_map.get(filters.ordering, last_activity_expr.desc())
        )

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())

    async def is_my_contact(self, teacher_id: int, student_id: int) -> bool:
        stmt = select(Contact).where(Contact.user_id == teacher_id, Contact.friend_id == student_id)
        result = await self.db.execute(stmt)
        existing_contact = result.scalar_one_or_none()
        return True if existing_contact else False

    async def student_dashboard_stats(self, teacher_id: int, student_id: int):
        full_name_expr = func.trim(
            func.concat(
                func.coalesce(User.first_name, ""),
                cast(" ", String),
                func.coalesce(User.last_name, ""),
            )
        )

        stmt = (
            select(
                User.id.label("student_id"),
                User.profile_image,
                User.username,
                full_name_expr.label("full_name"),

                func.array_agg(
                    func.distinct(StudentGroup.name)
                ).label("group_names"),

                func.count(QuizAttempt.id).label("total_tests"),
                func.avg(QuizAttempt.score).label("average_score"),
                func.max(QuizAttempt.finished_at).label("last_activity"),
            )
            .select_from(StudentGroup)
            .join(
                QuizSessionGroup,
                QuizSessionGroup.group_id == StudentGroup.id,
            )
            .join(
                QuizSession,
                QuizSession.id == QuizSessionGroup.session_id,
            )
            .join(
                SessionParticipant,
                (SessionParticipant.session_id == QuizSession.id)
                & (SessionParticipant.user_id == student_id),
            )
            .join(
                QuizAttempt,
                QuizAttempt.participant_id == SessionParticipant.id,
            )
            .join(
                User,
                User.id == SessionParticipant.user_id,
            )
            .where(
                StudentGroup.teacher_id == teacher_id,
            )
            .group_by(
                User.id,
                User.first_name,
                User.last_name,
            )
        )

        result = await self.db.execute(stmt)
        dashboard_data = result.mappings().first()
        if dashboard_data is None:
            student = select(User.id.label("student_id"), User.profile_image, User.username,
                             full_name_expr.label("full_name")).where(User.id == student_id)
            result = await self.db.execute(student)
            dashboard_data = result.mappings().first()

        return dashboard_data

    async def student_weak_topics(self, teacher_id: int, student_id: int):
        # 1) Teacher group-lariga tegishli sessionlarni olish
        teacher_session_ids_sq = (
            select(QuizSessionGroup.session_id)
            .join(
                StudentGroup,
                StudentGroup.id == QuizSessionGroup.group_id,
            )
            .where(StudentGroup.teacher_id == teacher_id)
            .distinct()
            .subquery()
        )

        # 2) Correct answer -> 100, wrong -> 0
        percent_expr = func.avg(
            case(
                (AttemptAnswer.is_correct.is_(True), 100.0),
                else_=0.0,
            )
        )

        # 3) Level label
        level_expr = case(
            (percent_expr < 40, literal("Juda past daraja")),
            else_=literal("Past daraja"),
        )

        stmt = (
            select(
                # Agar senda Question.subject bo'lsa shuni ishlatasan
                # bo'lmasa Quiz.subject yoki Subject.name bilan almashtirasan
                Question.subject.label("subject_name"),
                Question.topic.label("topic_name"),
                func.round(
                    cast(percent_expr, Numeric),
                    2
                ).label("average_percent"),
                level_expr.label("level"),
            )
            .select_from(SessionParticipant)
            .join(
                QuizAttempt,
                QuizAttempt.participant_id == SessionParticipant.id,
            )
            .join(
                AttemptAnswer,
                AttemptAnswer.attempt_id == QuizAttempt.id,
            )
            .join(
                Question,
                Question.id == AttemptAnswer.question_id,
            )
            .where(
                SessionParticipant.user_id == student_id,
                SessionParticipant.session_id.in_(
                    select(teacher_session_ids_sq.c.session_id)
                ),
                Question.topic.is_not(None),
            )
            .group_by(
                Question.subject,
                Question.topic,
            )
            .having(percent_expr < 50)
            .order_by(percent_expr.asc())
        )

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())

    async def student_subject_stats(self, teacher_id: int, student_id: int):
        teacher_session_ids_sq = (
            select(QuizSessionGroup.session_id)
            .join(
                StudentGroup,
                StudentGroup.id == QuizSessionGroup.group_id,
            )
            .where(StudentGroup.teacher_id == teacher_id)
            .distinct()
            .subquery()
        )

        # 2️⃣ percent (100 / 0)
        percent_expr = func.avg(
            case(
                (AttemptAnswer.is_correct.is_(True), 100.0),
                else_=0.0,
            )
        )

        stmt = (
            select(
                Question.subject.label("subject_name"),
                percent_expr.label("average_percent"),
            )
            .select_from(SessionParticipant)
            .join(
                QuizAttempt,
                QuizAttempt.participant_id == SessionParticipant.id,
            )
            .join(
                AttemptAnswer,
                AttemptAnswer.attempt_id == QuizAttempt.id,
            )
            .join(
                Question,
                Question.id == AttemptAnswer.question_id,
            )
            .where(
                SessionParticipant.user_id == student_id,
                SessionParticipant.session_id.in_(
                    select(teacher_session_ids_sq.c.session_id)
                ),
                Question.subject.is_not(None),
            )
            .group_by(Question.subject)
            .order_by(Question.subject)
        )

        result = await self.db.execute(stmt)
        rows = result.mappings().all()

        overall = 0
        if rows:
            overall = round(
                sum(r["average_percent"] for r in rows) / len(rows), 2
            )

        return rows, overall

    async def student_quiz_session_history(self, user_id: int, teacher_id: int, search: str | None):
        teacher_session_ids_sq = (
            select(QuizSessionGroup.session_id)
            .join(
                StudentGroup,
                StudentGroup.id == QuizSessionGroup.group_id,
            )
            .where(StudentGroup.teacher_id == teacher_id)
            .distinct()
            .subquery()
        )

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

            .join(
                SessionParticipant,
                SessionParticipant.session_id == QuizSession.id,
            )

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

            .where(
                QuizSession.id.in_(
                    select(teacher_session_ids_sq.c.session_id)
                )
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

    async def teacher_students_leaderboard(self, teacher_id: int, filters: TeacherStudentListParams):
        teacher_groups_sq = (
            select(
                StudentGroup.id.label("group_id"),
                StudentGroup.name.label("group_name"),
            )
            .where(StudentGroup.teacher_id == teacher_id)
            .subquery()
        )
        student_groups_sq = (
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

        teacher_sessions_sq = (
            select(
                distinct(QuizSessionGroup.session_id).label("session_id")
            )
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

        # oddiy streak logika: oxirgi faollikdan necha kun bo'ldi
        streak_days_expr = cast(
            func.coalesce(
                func.extract(
                    "day",
                    func.now() - func.max(
                        func.coalesce(
                            QuizAttempt.finished_at,
                            QuizSession.created_at,
                            SessionParticipant.joined_at,
                        )
                    ),
                ),
                0,
            ),
            Numeric,
        ).label("streak_days")

        status_expr = case(
            (
                last_activity_expr >= func.now() - text("INTERVAL '3 days'"),
                literal("active"),
            ),
            else_=literal("inactive"),
        ).label("status")

        base_stmt = (
            select(
                User.id.label("student_id"),
                User.username.label("username"),
                User.first_name.label("first_name"),
                User.last_name.label("last_name"),
                User.profile_image.label("profile_image"),
                full_name_expr,
                student_groups_sq.c.group_names.label("group_names"),
                average_score_expr,
                tests_count_expr,
                last_activity_expr,
                cast(streak_days_expr, Numeric(10, 0)).label("streak_days"),
                status_expr,
            )
            .select_from(student_groups_sq)
            .join(User, User.id == student_groups_sq.c.student_id)
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
                User.username,
                User.first_name,
                User.last_name,
                User.profile_image,
                student_groups_sq.c.group_names,
            )
        )

        if filters.search:
            search = f"%{filters.search}%"
            base_stmt = base_stmt.where(
                or_(
                    User.first_name.ilike(search),
                    User.last_name.ilike(search),
                    full_name_search_expr.ilike(search),
                    User.username.ilike(search),
                )
            )

        if filters.min_score is not None:
            base_stmt = base_stmt.having(average_score_expr >= filters.min_score)

        if filters.max_score is not None:
            base_stmt = base_stmt.having(average_score_expr <= filters.max_score)

        if filters.status:
            base_stmt = base_stmt.having(status_expr == filters.status)

        leaderboard_cte = base_stmt.cte("leaderboard")

        rank_expr = func.dense_rank().over(
            order_by=(
                leaderboard_cte.c.average_score.desc(),
                leaderboard_cte.c.tests_count.desc(),
                leaderboard_cte.c.last_activity.desc(),
            )
        ).label("rank")

        final_stmt = select(
            rank_expr,
            leaderboard_cte.c.student_id,
            leaderboard_cte.c.username,
            leaderboard_cte.c.first_name,
            leaderboard_cte.c.last_name,
            leaderboard_cte.c.profile_image,
            leaderboard_cte.c.full_name,
            leaderboard_cte.c.group_names,
            leaderboard_cte.c.average_score,
            leaderboard_cte.c.tests_count,
            leaderboard_cte.c.streak_days,
            leaderboard_cte.c.last_activity,
            leaderboard_cte.c.status,
        )

        ordering_map = {
            "average_score": leaderboard_cte.c.average_score.asc(),
            "-average_score": leaderboard_cte.c.average_score.desc(),
            "tests_count": leaderboard_cte.c.tests_count.asc(),
            "-tests_count": leaderboard_cte.c.tests_count.desc(),
            "last_activity": leaderboard_cte.c.last_activity.asc(),
            "-last_activity": leaderboard_cte.c.last_activity.desc(),
            "full_name": leaderboard_cte.c.full_name.asc(),
            "-full_name": leaderboard_cte.c.full_name.desc(),
            "rank": rank_expr.asc(),
            "-rank": rank_expr.desc(),
        }
        final_stmt = final_stmt.order_by(
            rank_expr
        )
        if filters.ordering:
            final_stmt = final_stmt.order_by(
                ordering_map.get(
                    filters.ordering
                )
            )

        result = await self.db.execute(final_stmt)
        return paginate(result.mappings().all())
        # rows = result.mappings().all()
        #
        # items = []
        # for row in rows:
        #     rank = int(row["rank"])
        #     crown_type = None
        #     if rank == 1:
        #         crown_type = "gold"
        #     elif rank == 2:
        #         crown_type = "silver"
        #     elif rank == 3:
        #         crown_type = "bronze"
        #
        #     items.append(
        #         {
        #             "rank": rank,
        #             "student_id": row["student_id"],
        #             "username": row["username"],
        #             "first_name": row["first_name"],
        #             "last_name": row["last_name"],
        #             "full_name": row["full_name"],
        #             "profile_image": row["profile_image"],
        #             "group_names": row["group_names"] or [],
        #             "average_score": float(row["average_score"] or 0),
        #             "tests_count": int(row["tests_count"] or 0),
        #             "streak_days": int(row["streak_days"] or 0),
        #             "last_activity": row["last_activity"],
        #             "status": row["status"],
        #             "is_top_3": rank <= 3,
        #             "crown_type": crown_type,
        #         }
        #     )
        #
        # return paginate(items)

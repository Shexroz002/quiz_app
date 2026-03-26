from fastapi_pagination import paginate
from sqlalchemy import select, delete, and_, cast, String, func, Numeric, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Subject, SessionParticipant, QuizAttempt, QuizSession, User
from app.models.group.student_group import StudentGroup, StudentGroupMember
from app.models.quiz.real_time_quiz import QuizSessionGroup


class StudentGroupRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_group(self, group: StudentGroup) -> StudentGroup:
        self.db.add(group)
        await self.db.flush()
        await self.db.refresh(group)
        return group

    async def get_group(self, group_id: int) -> StudentGroup | None:
        stmt = (
            select(StudentGroup)
            .where(StudentGroup.id == group_id)
            .options(selectinload(StudentGroup.members))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_members(self, group_id: int, student_ids: list[int], teacher_id: int):
        for student_id in student_ids:
            self.db.add(
                StudentGroupMember(
                    group_id=group_id,
                    student_id=student_id,
                    added_by=teacher_id,
                )
            )


    async def validate_groups(self, teacher_id: int, group_ids: list[int]) -> list[int]:
        if not group_ids:
            return []

        stmt = (
            select(StudentGroup.id)
            .where(
                StudentGroup.teacher_id == teacher_id,
                StudentGroup.id.in_(group_ids),
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


    async def remove_members(self, group_id: int, student_ids: list[int]):
        stmt = (
            delete(StudentGroupMember)
            .where(
                StudentGroupMember.group_id == group_id,
                StudentGroupMember.student_id.in_(student_ids),
            )
        )
        await self.db.execute(stmt)


    async def group_members(
            self,
            group_id: int,
            search: str | None = None,
    ):
        full_name_expr = func.concat(
            User.first_name, " ", User.last_name
        ).label("full_name")

        stmt = (
            select(
                User.id.label("student_id"),
                full_name_expr,
                User.profile_image.label("profile_image"),
                User.gender.label("gender"),
                User.phone_number.label("phone_number"),
                User.date_of_birth.label("birth_date"),
            )
            .select_from(StudentGroupMember)
            .join(User, User.id == StudentGroupMember.student_id)
            .where(StudentGroupMember.group_id == group_id)
        )

        if search:
            search_value = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    User.first_name.ilike(search_value),
                    User.last_name.ilike(search_value),
                    full_name_expr.ilike(search_value),
                )
            )

        stmt = stmt.order_by(User.first_name.asc(), User.last_name.asc())

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())


    async def is_group_member(self, group_id: int, student_id: int) -> bool:
        stmt = select(StudentGroupMember).where(
            StudentGroupMember.group_id == group_id,
            StudentGroupMember.student_id == student_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None


    async def list_groups_by_teacher(self, teacher_id: int, search: str | None = None,
                                     subject_id: int | None = None, ):
        students_count_expr = func.count(
            func.distinct(StudentGroupMember.student_id)
        ).label("students_count")

        tests_count_expr = func.count(
            func.distinct(QuizSessionGroup.session_id)
        ).label("tests_count")

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
            0,
        ).label("average_score")

        last_activity_expr = func.max(
            func.coalesce(
                QuizAttempt.finished_at,
                QuizSession.created_at,
                SessionParticipant.joined_at,
            )
        ).label("last_activity")

        stmt = (
            select(
                StudentGroup.id.label("id"),
                StudentGroup.name.label("name"),
                Subject.name.label("subject_name"),
                StudentGroup.description.label("description"),
                cast(StudentGroup.status, String).label("status"),
                students_count_expr,
                tests_count_expr,
                average_score_expr,
                last_activity_expr,
                cast(StudentGroup.color, String).label("color"),
                StudentGroup.cover_image.label("cover_image"),
            )
            .select_from(StudentGroup)
            .join(Subject, Subject.id == StudentGroup.subject_id, isouter=True)
            .join(
                StudentGroupMember,
                StudentGroupMember.group_id == StudentGroup.id,
                isouter=True,
            )
            .join(
                QuizSessionGroup,
                QuizSessionGroup.group_id == StudentGroup.id,
                isouter=True,
            )
            .join(
                QuizSession,
                QuizSession.id == QuizSessionGroup.session_id,
                isouter=True,
            )
            .join(
                SessionParticipant,
                and_(
                    SessionParticipant.session_id == QuizSession.id,
                    SessionParticipant.user_id == StudentGroupMember.student_id,
                ),
                isouter=True,
            )
            .join(
                QuizAttempt,
                and_(
                    QuizAttempt.participant_id == SessionParticipant.id,
                    QuizAttempt.session_id == QuizSession.id,
                ),
                isouter=True,
            )
            .where(StudentGroup.teacher_id == teacher_id)
        )

        if search:
            stmt = stmt.where(StudentGroup.name.ilike(f"%{search.strip()}%"))

        if subject_id is not None:
            stmt = stmt.where(StudentGroup.subject_id == subject_id)

        stmt = (
            stmt.group_by(
                StudentGroup.id,
                StudentGroup.name,
                Subject.name,
                StudentGroup.description,
                StudentGroup.status,
                StudentGroup.color,
                StudentGroup.cover_image,
            )
            .order_by(last_activity_expr.desc().nulls_last())
        )

        result = await self.db.execute(stmt)
        rows = result.mappings().all()
        return paginate(rows)

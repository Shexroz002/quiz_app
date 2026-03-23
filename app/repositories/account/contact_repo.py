from typing import Any, Sequence
from fastapi_pagination import Page, add_pagination, paginate
from sqlalchemy import select, func, case, literal, and_, or_, cast, Numeric, text, String
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.teacher.my_student.params.student_filter import StudentFilterParams
from app.models import Contact, User, QuizAttempt, QuizSession, SessionParticipant
from app.repositories.base.base_repository import BaseRepository
from app.schemas.account.users import StudentStatus


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
        return result.scalars().all()

    async def contact_suggestions(self, contact_user_id: int) -> Sequence[User]:
        contacts = await self.contact_list(contact_user_id)
        contact_ids = {contact.friend_id for contact in contacts}
        stmt = select(User).where(~User.id.in_(contact_ids.union({contact_user_id}))).limit(10)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_contact_by_id(self, friend_id: int, contact_user_id: int) -> Contact:
        stmt = select(Contact).where(Contact.user_id == contact_user_id, Contact.friend_id == friend_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def my_student_list(self, teacher_id: int, filters: StudentFilterParams):

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
            func.count(func.distinct(QuizAttempt.id)).filter(
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

        full_name_expr = func.concat(
            User.first_name, literal(" "), User.last_name
        ).label("full_name")

        stmt = (
            select(
                User.id.label("student_id"),
                User.username.label("username"),
                full_name_expr,
                func.coalesce(
                    cast(User.education_level, String),
                    "Noma'lum"
                ).label("class_name"),
                average_score_expr,
                tests_count_expr,
                last_activity_expr,
                status_expr,
            )
            .select_from(Contact)
            .join(User, User.id == Contact.friend_id)
            .join(SessionParticipant, SessionParticipant.user_id == User.id, isouter=True)
            .join(QuizSession, QuizSession.id == SessionParticipant.session_id, isouter=True)
            .join(
                QuizAttempt,
                and_(
                    QuizAttempt.participant_id == SessionParticipant.id,
                    QuizAttempt.session_id == QuizSession.id,
                ),
                isouter=True,
            )
            .where(Contact.user_id == teacher_id)
            .group_by(
                User.id,
                User.username,
                User.first_name,
                User.last_name,
                User.education_level,
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

        if filters.class_name:
            stmt = stmt.where(User.education_level == filters.class_name)

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
            "full_name": full_name_expr.desc(),
            "-full_name": full_name_expr.asc(),
        }

        stmt = stmt.order_by(
            ordering_map.get(filters.ordering, last_activity_expr.desc())
        )

        result = await self.db.execute(stmt)
        return paginate(result.mappings().all())

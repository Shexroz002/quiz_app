from fastapi import HTTPException, Depends
from pydantic_settings.sources.providers import aws
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.api.v1.teacher.my_student.params.student_filter import StudentFilterParams
from app.core.database.base import get_db
from app.repositories.account import ContactRepository, UserRepository
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository
from app.schemas.account.users import TeacherStudentListParams


class ContactService:

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ContactRepository(db)
        self.user_repo = UserRepository(db)
        self.session_repo = QuizSessionRepository(db)

    async def create_contact(self, contact_user_id: int, friend_id: int, name: str = None):
        if friend_id == contact_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot add yourself as a contact.")

        contact = await self.repo.get_contact_by_id(friend_id, contact_user_id)
        if contact:
            return contact

        friend = await self.user_repo.get_by_id(friend_id)
        if not friend:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend not found.")
        if name is None:
            if friend.first_name and friend.last_name:
                name = f"{friend.first_name} {friend.last_name}"
            else:
                name = friend.username
        data = await self.repo.create_contact(user_id=contact_user_id, friend_id=friend_id, name=name)
        await self.db.commit()
        return data

    async def contact_list(self, contact_user_id: int):
        return await self.repo.contact_list(contact_user_id)

    async def contact_suggestions(self, contact_user_id: int, search: str | None = None):
        return await self.repo.contact_suggestions(contact_user_id, search)

    async def get_my_students(self, teacher_id: int, filters: StudentFilterParams):
        return await self.repo.my_student_list(teacher_id, filters)

    async def get_student_dashboard_stats(self, teacher_id: int, student_id: int):
        if not await self.repo.is_my_contact(teacher_id, student_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
        return await self.repo.student_dashboard_stats(teacher_id, student_id)

    async def student_week_topics(self, teacher_id: int, student_id: int):
        if not await self.repo.is_my_contact(teacher_id, student_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
        return await self.repo.student_weak_topics(teacher_id, student_id)

    async def get_student_subject_stats(self, teacher_id, student_id):
        if not await self.repo.is_my_contact(teacher_id, student_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

        rows, overall = await self.repo.student_subject_stats(teacher_id, student_id)
        return {
            "overall_percent": overall,
            "items": rows,
        }

    async def student_quiz_session_history(self, teacher_id, student_id, search: str | None = None):
        if not await self.repo.is_my_contact(teacher_id, student_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
        return await self.repo.student_quiz_session_history(student_id, teacher_id, search)

    async def get_teacher_students_leaderboard(self, teacher_id: int, filters: TeacherStudentListParams):
        return await self.repo.teacher_students_leaderboard(teacher_id, filters)


def get_contact_service(db: AsyncSession = Depends(get_db)) -> ContactService:
    return ContactService(db)

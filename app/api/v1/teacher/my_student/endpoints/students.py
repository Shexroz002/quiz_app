from fastapi_pagination import Page
from fastapi import APIRouter, Depends

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.api.v1.teacher.my_student.params.student_filter import StudentFilterParams
from app.schemas.account.users import StudentTableItemSchema
from app.services.account.contact_service import get_contact_service

from app.models import User

my_student_router = APIRouter(prefix="/my/student", tags=["My Student Management"])


@my_student_router.get("/", response_model=Page[StudentTableItemSchema])
async def my_students(
        current_user: User = Depends(get_current_user),
        contact_service=Depends(get_contact_service),
        filters: StudentFilterParams = Depends(),
):
    return await contact_service.get_my_students(current_user.id, filters)

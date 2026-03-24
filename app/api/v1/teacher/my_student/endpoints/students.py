from fastapi_pagination import Page
from fastapi import APIRouter, Depends
from starlette import status
from starlette.responses import JSONResponse

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.api.v1.teacher.my_student.params.student_filter import StudentFilterParams
from app.schemas.account.users import StudentTableItemSchema, UserShortInfoSchema, UserContactListSchema
from app.services.account.contact_service import get_contact_service, ContactService

from app.models import User
from app.services.account.users import UserService, get_user_service

my_student_router = APIRouter(prefix="/my/student", tags=["My Student Management"])


@my_student_router.get("/", response_model=Page[StudentTableItemSchema])
async def my_students(
        current_user: User = Depends(get_current_user),
        contact_service=Depends(get_contact_service),
        filters: StudentFilterParams = Depends(),
):
    return await contact_service.get_my_students(current_user.id, filters)


@my_student_router.get("/suggestions/", response_model=Page[UserShortInfoSchema])
async def contact_suggestions(contact_service: ContactService = Depends(get_contact_service),
                       current_user: User = Depends(get_current_user)):
    return await contact_service.contact_suggestions(current_user.id)

@my_student_router.get("/search", response_model=Page[UserContactListSchema])
async def search_users(
        search: str = None,
        user_service: UserService = Depends(get_user_service),
        current_user: User = Depends(get_current_user),
):
    return await user_service.search_users_for_contact(current_user_id=current_user.id, search=search)

@my_student_router.post("/create/{student_id}", status_code=status.HTTP_201_CREATED)
async def create_contact(student_id: int, contact_service: ContactService = Depends(get_contact_service),
                         current_user: User = Depends(get_current_user), ):
    await contact_service.create_contact(current_user.id, student_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content={"message": "Contact created successfully."})
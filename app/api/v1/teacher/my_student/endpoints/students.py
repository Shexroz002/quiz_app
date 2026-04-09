from fastapi_pagination import Page
from fastapi import APIRouter, Depends
from sqlalchemy.util import await_only
from starlette import status
from starlette.responses import JSONResponse

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.api.v1.teacher.my_student.params.student_filter import StudentFilterParams
from app.schemas.account.users import StudentTableItemSchema, UserShortInfoSchema, UserContactListSchema, \
    StudentCardResponse, WeakTopicItemResponse, SubjectStatsResponse, TeacherStudentLeaderboardItem, \
    TeacherStudentListParams
from app.schemas.quiz.quiz_session import SessionLeaderboardRow
from app.services.account import contact_service
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
async def contact_suggestions(
        search: str = None,
        contact_service: ContactService = Depends(get_contact_service),
        current_user: User = Depends(get_current_user)):
    return await contact_service.contact_suggestions(current_user.id, search)


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


@my_student_router.get('/{student_id}/card', response_model=StudentCardResponse)
async def student_card(student_id: int, contact_service: ContactService = Depends(get_contact_service),
                       current_user: User = Depends(get_current_user), ):
    return await contact_service.get_student_dashboard_stats(current_user.id, student_id)


@my_student_router.get('/{student_id}/weak-topics', response_model=Page[WeakTopicItemResponse])
async def week_topics(student_id: int, contact_service: ContactService = Depends(get_contact_service),
                      current_user: User = Depends(get_current_user)):
    return await contact_service.student_week_topics(teacher_id=current_user.id, student_id=student_id)


@my_student_router.get('/{student_id}/subjects-stat', response_model=SubjectStatsResponse)
async def subjects_stat(student_id: int, contact_service: ContactService = Depends(get_contact_service),
                        current_user: User = Depends(get_current_user)):
    return await contact_service.get_student_subject_stats(teacher_id=current_user.id, student_id=student_id)


@my_student_router.get("/{student_id}/history", response_model=Page[SessionLeaderboardRow])
async def student_session_history(student_id: int, contact_service: ContactService = Depends(get_contact_service),
                                  current_user: User = Depends(get_current_user)):
    return await contact_service.student_quiz_session_history(teacher_id=current_user.id, student_id=student_id)


@my_student_router.get('/leaderboard', response_model=Page[TeacherStudentLeaderboardItem])
async def teacher_students_leaderboard(
        filters: TeacherStudentListParams = Depends(),
        contact_service: ContactService = Depends(get_contact_service),
        current_user: User = Depends(get_current_user)):
    return await contact_service.get_teacher_students_leaderboard(current_user.id, filters)

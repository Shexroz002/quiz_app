from fastapi import APIRouter

from app.api.v1.teacher.my_student.endpoints.students import my_student_router
teacher_router = APIRouter(prefix="/teacher", tags=["My Student Management"])
teacher_router.include_router(my_student_router)
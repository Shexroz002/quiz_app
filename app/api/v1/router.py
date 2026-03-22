from fastapi import APIRouter

from app.api.v1.common.router import common_router
from app.api.v1.student.router import student_router
from app.api.v1.teacher.router import teacher_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(common_router)
api_router.include_router(student_router)
api_router.include_router(teacher_router)
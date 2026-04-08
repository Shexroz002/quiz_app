from fastapi import APIRouter

from app.api.v1.student.group.router import student_group_router_base
from app.api.v1.student.quiz.router import base_quiz_router
student_router = APIRouter(prefix="/student", tags=["Student"])
student_router.include_router(base_quiz_router)
student_router.include_router(student_group_router_base)

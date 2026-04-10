from fastapi import APIRouter

from app.api.v1.teacher.group.router import group_router
from app.api.v1.teacher.my_student.endpoints.students import my_student_router
from app.api.v1.teacher.quiz.router import base_teacher_quiz_router
from app.api.v1.teacher.quiz_session.router import quiz_group_live_base
from app.api.v1.teacher.statistics.router import statistic_base_router

teacher_router = APIRouter(prefix="/teacher", tags=["My Student Management"])
teacher_router.include_router(my_student_router)
teacher_router.include_router(group_router)
teacher_router.include_router(quiz_group_live_base)
teacher_router.include_router(base_teacher_quiz_router)
teacher_router.include_router(statistic_base_router)
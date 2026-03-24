from fastapi import APIRouter

from app.api.v1.teacher.group.endpoints.student_group import student_group_router

group_router = APIRouter(prefix="/group", tags=["Group Management"])
group_router.include_router(student_group_router)
from fastapi import APIRouter

from app.api.v1.student.group.endpoints.student_group import group_router_v2

student_group_router_base = APIRouter(prefix="/group", tags=["Student Group Management"])
student_group_router_base.include_router(group_router_v2)
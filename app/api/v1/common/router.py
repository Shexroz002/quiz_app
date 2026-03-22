from fastapi import APIRouter

from app.api.v1.common.auth.router import auth_router
from app.api.v1.common.notification.router import notification_base_router
from app.api.v1.common.subject.router import base_subject_router
from app.api.v1.common.users.router import user_router

from app.api.v1.common.quiz_generator.router import quiz_generator_router


common_router = APIRouter(prefix="", tags=["Common"])
common_router.include_router(user_router)
common_router.include_router(auth_router)
common_router.include_router(base_subject_router)
common_router.include_router(notification_base_router)
common_router.include_router(quiz_generator_router)

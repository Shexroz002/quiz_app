from fastapi import APIRouter

from app.api.v1.notification.endpoint.notification import notification_router

notification_base_router = APIRouter(prefix="/notifications", tags=["Notifications"])

notification_base_router.include_router(notification_router)

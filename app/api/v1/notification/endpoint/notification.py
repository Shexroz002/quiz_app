from fastapi import APIRouter, Depends
from app.api.v1.auth.dependencies.current_user import get_current_user
from app.schemas.notification.notification import NotificationResponseSchema, NotificationReadResponseSchema
from app.services.notification.notification_service import get_notification_service

notification_router = APIRouter(prefix="")


@notification_router.get("/", response_model=list[NotificationResponseSchema])
async def get_notifications(
        current_user=Depends(get_current_user),
        notification_service=Depends(get_notification_service)
):
    return await notification_service.list_notifications(current_user.id)


@notification_router.patch("/{notification_id}/read/", response_model=NotificationReadResponseSchema)
async def mark_notification_as_read(
        notification_id: int,
        current_user=Depends(get_current_user),
        notification_service=Depends(get_notification_service)
):
    return await notification_service.mark_as_read(notification_id, current_user.id)


@notification_router.patch("/read-all/", response_model=list[NotificationReadResponseSchema])
async def mark_all_notifications_as_read(
        current_user=Depends(get_current_user),
        notification_service=Depends(get_notification_service)
):
    return await notification_service.mark_all_as_read(current_user.id)

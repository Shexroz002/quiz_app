from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.repositories.notification.notification_repo import NotificationRepo
from app.schemas.notification.notification import NotificationCreateSchema, NotificationResponseSchema
from app.websocket import notification_manager


class NotificationService:

    def __init__(self, db: AsyncSession):
        self.repo = NotificationRepo(db)
        self.db = db

    async def list_notifications(self, user_id: int):
        return await self.repo.list_notifications(user_id)

    async def mark_as_read(self, notification_id: int, user_id: int):
        return await self.repo.mark_as_read(notification_id, user_id)

    async def mark_all_as_read(self, user_id: int):
        return await self.repo.mark_as_read_all(user_id)

    async def create_notification(self, data: NotificationCreateSchema):
        notification = await self.repo.create_notification(data)
        await self.repo.db.commit()
        await self.repo.db.refresh(notification)
        count_notifications = await self.repo.count_notifications(notification.recipient_id)

        data = NotificationResponseSchema.model_validate(notification)

        await notification_manager.send_to_user(
            user_id=notification.recipient_id,
            notification_type = "test_invite_notification",
            payload=data.model_dump( exclude={"recipient_id", "sender_id", "is_read", "is_deleted", "created_at", "read_at"}),
            unread_count=count_notifications
        )

        return notification


async def get_notification_service(db: AsyncSession = Depends(get_db)) -> NotificationService:
    return NotificationService(db)

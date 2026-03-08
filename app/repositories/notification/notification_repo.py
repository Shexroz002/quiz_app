from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification import Notification, NotificationType, NotificationActionType
from app.schemas.notification.notification import NotificationCreateSchema


class NotificationRepo:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_notification(
        self,
        data: NotificationCreateSchema,
    ) -> Notification:
        notification = Notification(**data.model_dump(exclude_none=True))
        self.db.add(notification)
        await self.db.flush()
        await self.db.refresh(notification)
        return notification

    async def list_notifications(self, current_user_id: int):
        stmt = (
            select(Notification)
            .where(
                Notification.recipient_id == current_user_id,
                Notification.is_deleted == False,
            )
            .order_by(Notification.created_at.desc())
        )
        result = await self.db.execute(stmt)
        notifications = result.scalars().all()
        return notifications

    async def mark_as_read(self, notification_id: int, current_user_id: int) -> Notification | None:
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_id == current_user_id,
            Notification.is_deleted == False,
        )
        result = await self.db.execute(stmt)
        notification = result.scalar_one_or_none()

        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        notification.is_read = True
        notification.read_at = datetime.utcnow()
        await self.db.flush()
        return notification


    async def mark_as_read_all(self, current_user_id: int):
        stmt = (
            update(Notification)
            .where(
                Notification.recipient_id == current_user_id,
                Notification.is_read == False,
                Notification.is_deleted == False,
            )
            .values(
                is_read=True,
                read_at=datetime.utcnow(),
            )
        )

        await self.db.execute(stmt)
        await self.db.flush()

        return {"detail": "Notification marked as read"}

    async def count_notifications(self, current_user_id: int) -> int:
        stmt = (
            select(Notification)
            .where(
                Notification.recipient_id == current_user_id,
                Notification.is_read == False,
                Notification.is_deleted == False,
            )
        )
        result = await self.db.execute(stmt)
        notifications = result.scalars().all()
        return len(notifications)

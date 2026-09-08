from typing import List

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.base import get_db
from app.core.database.redis import get_redis_client
from app.models import User, NotificationType
from app.repositories.notification.notification_repo import NotificationRepo
from app.schemas.notification.notification import NotificationCreateSchema, NotificationResponseSchema
from app.services.redis_service.realtime_events import publish_realtime_event
from app.websocket import notification_manager


class NotificationService:

    def __init__(self, db: AsyncSession, redis: Redis | None = None):
        self.repo = NotificationRepo(db)
        self.db = db
        self.redis = redis

    async def list_notifications(self, user_id: int):
        return await self.repo.list_notifications(user_id)

    async def mark_as_read(self, notification_id: int, user_id: int):
        return await self.repo.mark_as_read(notification_id, user_id)

    async def mark_all_as_read(self, user_id: int):
        return await self.repo.mark_as_read_all(user_id)

    async def create_notification(
        self,
        data: NotificationCreateSchema,
        notification_type: NotificationType | None = None,
        *,
        commit: bool = True,
        deliver: bool = True,
    ):
        notification = await self.repo.create_notification(data)
        if commit:
            await self.repo.db.commit()
            await self.repo.db.refresh(notification)
        if not deliver:
            return notification

        count_notifications = await self.repo.count_notifications(notification.recipient_id)

        data = NotificationResponseSchema.model_validate(notification)

        await notification_manager.send_to_user(
            user_id=notification.recipient_id,
            notification_type=notification_type or notification.type,
            payload=data.model_dump( exclude={"recipient_id", "sender_id", "is_read", "is_deleted", "created_at", "read_at"}),
            unread_count=count_notifications
        )

        return notification

    async def publish_notification(self, notification) -> None:
        count = await self.repo.count_notifications(notification.recipient_id)
        payload = {
            "id": notification.id,
            "type": notification.type.value,
            "action_type": notification.action_type.value,
            "title": notification.title,
            "message": notification.message,
            "payload": notification.payload,
            "read_at": notification.read_at,
            "created_at": notification.created_at,
            "sender": None,
        }
        if self.redis is not None:
            await publish_realtime_event(
                self.redis,
                {
                    "target": "notification",
                    "user_id": notification.recipient_id,
                    "notification_type": notification.type.value,
                    "payload": payload,
                    "unread_count": count,
                },
            )
            return
        await notification_manager.send_to_user(
            user_id=notification.recipient_id,
            notification_type=notification.type.value,
            payload=payload,
            unread_count=count,
        )


    async def send_notification_to_group_by_teacher(self, current_user:User,session_code:str,user_ids: List[int]):
       for user_id in user_ids:
           data = {
               "recipient_id": user_id,
               "sender_id": current_user.id,
               "type": "test_invite",
               "action_type": "test_invite",
               "payload": {"session_code": session_code},
               "title": "Quiz Session  taklif",
               "message": f"{current_user.first_name} {current_user.last_name} sizni birgalikda test ishlashga taklif qilmoqda."
           }
           data_schema = NotificationCreateSchema(**data)
           await self.create_notification(data_schema)




async def get_notification_service(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis_client),
) -> NotificationService:
    return NotificationService(db, redis)

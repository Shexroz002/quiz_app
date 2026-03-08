from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer

from app.models.notification.notification import NotificationType, NotificationActionType
from app.schemas.quiz.question import BASE_URL


class NotificationSenderSchema(BaseModel):
    id: int | None = None
    first_name: str | None = None
    last_name: str | None = None
    profile_image: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"


class NotificationCreateSchema(BaseModel):
    recipient_id: int
    sender_id: int | None = None
    type: NotificationType
    action_type: NotificationActionType = NotificationActionType.NONE
    title: str
    message: str
    payload: dict[str, Any] | None = None


class NotificationResponseSchema(BaseModel):
    id: int
    type: NotificationType
    action_type: NotificationActionType
    title: str
    message: str
    payload: dict[str, Any] | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime
    sender: NotificationSenderSchema | None = None

    model_config = ConfigDict(from_attributes=True)

class NotificationReadResponseSchema(BaseModel):
    id: int
    is_read: bool
    read_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
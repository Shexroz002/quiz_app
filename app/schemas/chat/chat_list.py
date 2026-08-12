from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_serializer

from app.schemas.quiz.question import BASE_URL


class LastMessageOut(BaseModel):
    id: str|None
    sender_id: int
    sender_name: str | None = None
    text: str
    created_at: datetime


class ChatListItemOut(BaseModel):
    id: int
    type: str
    title: str
    avatar: str | None = None

    is_online: bool | None = None
    last_seen: datetime | None = None

    last_message: LastMessageOut | None = None
    unread_count: int = 0
    updated_at: datetime | None = None


class ChatListOut(BaseModel):
    items: list[ChatListItemOut]

class ChatMemberDetailOut(BaseModel):
    user_id: int
    username: str
    first_name: str | None = None
    last_name: str | None = None
    profile_image: str | None = None
    last_read_message_id: str | None = None
    role: str
    joined_at: datetime

    is_online: bool

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"



class ChatDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str

    description: str | None = None
    avatar_url: str | None = None

    owner_id: int
    direct_key: str | None = None

    last_message_text: str | None = None
    last_message_sender_id: int | None = None
    last_message_created_at: datetime | None = None

    members_count: int

    members: list[ChatMemberDetailOut]

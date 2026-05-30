from pydantic import BaseModel, Field

from app.models.chat.chats import ChatType


class CreateGroupChatSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(None, max_length=255)
    member_ids: list[int] = Field(default_factory=list)


class CreatePrivateChatSchema(BaseModel):
    target_user_id: int


class ChatResponse(BaseModel):
    id: int
    name: str
    chat_type: ChatType
    description: str | None
    avatar_url: str | None
    owner_id: int
    last_message_text: str | None
    last_message_created_at: str | None

    class Config:
        from_attributes = True
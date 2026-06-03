from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class Attachment(BaseModel):
    attachment_id: int
    type: str
    url: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    size: int


class MessageCreate(BaseModel):
    chat_id: int
    sender_id: int
    text: str | None = None
    reply_to_message_id: str | None = None
    forwarded_from: str | None = None
    attachments: list[Attachment] = []
    mentions: list[int] = []


class MessageUpdate(BaseModel):
    text: str


class ReactionRequest(BaseModel):
    emoji: str


class MessageOut(BaseModel):
    id: str = Field(alias="_id")
    chat_id: int
    sender_id: int
    text: str | None
    reply_to_message_id: str | None
    forwarded_from: str | None
    attachments: list[Attachment]
    reactions: list[dict]
    mentions: list[int]
    views_count: int
    is_read: bool
    edited: bool
    deleted: bool
    created_at: datetime
    edited_at: datetime | None

    class Config:
        populate_by_name = True

class MessageMarkAsReadRequest(BaseModel):
    message_ids: List[str]
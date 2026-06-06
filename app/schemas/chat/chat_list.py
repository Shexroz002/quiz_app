from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class ChatTypeOut(str, Enum):
    PRIVATE = "private"
    GROUP = "group"
    CHANNEL = "channel"


class AttachmentKind(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    VOICE = "voice"
    DOCUMENT = "document"
    STICKER = "sticker"


class AvatarOut(BaseModel):
    url: str | None = None
    initials: str
    color_seed: int | None = None


class UserPeerOut(BaseModel):
    type: str = Field(default="user", frozen=True)
    user_id: int
    username: str | None = None
    is_online: bool = False
    last_seen_at: datetime | None = None


class GroupPeerOut(BaseModel):
    type: str = Field(default="group", frozen=True)
    members_count: int


class MessageSenderOut(BaseModel):
    id: int
    name: str
    is_self: bool


class MessageAttachmentOut(BaseModel):
    kind: AttachmentKind
    display_label: str
    thumbnail_url: str | None = None


class MessagePreviewOut(BaseModel):
    text: str | None = None
    type: str = "text"  # text, photo, video, voice, document, sticker
    show_sender_prefix: bool = False
    attachment: MessageAttachmentOut | None = None


class LastMessageOut(BaseModel):
    sender: MessageSenderOut
    preview: MessagePreviewOut
    created_at: datetime
    status: str | None = None  # sent, delivered, read - faqat o'zinikida


class ChatOut(BaseModel):
    id: int
    type: ChatTypeOut
    title: str
    avatar: AvatarOut
    peer: UserPeerOut | GroupPeerOut
    last_message: LastMessageOut | None = None
    unread_count: int = 0
    is_pinned: bool = False
    is_muted: bool = False
    sort_key: datetime | None = None


class PaginationOut(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class ChatListResponse(BaseModel):
    chats: list[ChatOut]
    pagination: PaginationOut
    server_time: datetime
from enum import StrEnum


class EventType(StrEnum):
    MESSAGE_NEW = "message:new"
    MESSAGE_ACK = "message:ack"
    MESSAGE_EDITED = "message:edited"
    MESSAGE_DELETED = "message:deleted"
    MESSAGE_REACTION_ADD = "message:reaction_add"
    MESSAGE_READ = "message:read"
    TYPING_UPDATE = "typing:update"
    PRESENCE_UPDATE = "presence:update"
    CHAT_CREATED = "chat:created"
    CHAT_UPDATED = "chat:updated"
    CHAT_LEAVED = "chat:leaved"
    HEARTBEAT = "heartbeat:heartbeat"

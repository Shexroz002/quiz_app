from fastapi import APIRouter

from app.api.v1.common.chat.endpoints.chat import chat_router
from app.api.v1.common.chat.endpoints.message import message_router


base_chat_router = APIRouter(prefix="")
base_chat_router.include_router(chat_router)
base_chat_router.include_router(message_router)


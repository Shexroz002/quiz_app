from fastapi import APIRouter, Depends, Query
from fastapi_pagination import Page

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.schemas.chat.chat_list import ChatListOut, ChatDetailOut
from app.schemas.chat.chat_schema import ChatResponse, CreateGroupChatSchema, CreatePrivateChatSchema
from app.services.chat.chat_service import chat_service

chat_router = APIRouter(prefix="/chats", tags=["Chats"])


@chat_router.get("", response_model=ChatListOut)
async def get_chat_list(
        current_user=Depends(get_current_user),
        chat_services=Depends(chat_service),
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0),
):
    return await chat_services.get_chat_list(
        current_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@chat_router.get("/{chat_id}", response_model=ChatDetailOut)
async def get_chat(
        chat_id: int,
        current_user=Depends(get_current_user),
        chat_services=Depends(chat_service),
):
    return await chat_services.chat_detail(chat_id, current_user.id)


@chat_router.post("/group", response_model=ChatResponse, status_code=201)
async def create_group(
        data: CreateGroupChatSchema,
        current_user=Depends(get_current_user),
        chat_services=Depends(chat_service),
):
    return await chat_services.create_group_chat(
        owner_id=current_user.id,
        data=data,
    )


@chat_router.post("/private", response_model=ChatResponse, status_code=201)
async def create_or_get_private(
        data: CreatePrivateChatSchema,
        current_user=Depends(get_current_user),
        chat_services=Depends(chat_service),
):
    return await chat_services.get_or_create_private_chat(
        current_user_id=current_user.id,
        data=data,
    )


@chat_router.get("/my", response_model=list[ChatResponse])
async def my_chats(
        current_user=Depends(get_current_user),
        chat_services=Depends(chat_service),
):
    return await chat_services.get_my_chats(current_user.id)


@chat_router.delete("/{chat_id}/leave", status_code=204)
async def leave_chat(
        chat_id: int,
        current_user=Depends(get_current_user),
        chat_services=Depends(chat_service),
):
    await chat_services.leave_group(chat_id, current_user.id)

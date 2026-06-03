from fastapi import APIRouter, Query, Depends, Body
from starlette import status

from app.api.v1.common.auth.dependencies.current_user import get_current_user
from app.schemas.chat.message_schema import MessageCreate, MessageUpdate, ReactionRequest, MessageMarkAsReadRequest
from app.services.chat.message_service import MessageService, get_message_service

message_router = APIRouter(prefix="/messages", tags=["Messages"])


@message_router.post("/mark-as-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_as_read(
    body: MessageMarkAsReadRequest = Body(...),
    current_user=Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
):
    await service.message_mark_as_read(body.message_ids)
    return {"status": "ok"}



@message_router.post("/{chat_id}", status_code=201)
async def send_message(
        chat_id: int,
        data: MessageCreate,
        current_user=Depends(get_current_user),
        service: MessageService = Depends(get_message_service)):
    return await service.send_message(data, chat_id, current_user.id)


@message_router.get("/chat/{chat_id}")
async def get_history(
        chat_id: int,
        limit: int = Query(50, le=100),
        before_id: str = Query(None),
        service: MessageService = Depends(get_message_service),
):
    return await service.get_history(chat_id, limit, before_id)


@message_router.patch("/{message_id}")
async def edit_message(
        message_id: str,
        data: MessageUpdate,
        current_user=Depends(get_current_user),
        service: MessageService = Depends(get_message_service),
):
    return await service.edit_message(message_id, current_user.id, data)


@message_router.delete("/{message_id}")
async def delete_message(
        message_id: str,
        current_user=Depends(get_current_user),
        service: MessageService = Depends(get_message_service),
):
    return await service.delete_message(message_id, current_user.id)


@message_router.post("/{message_id}/reactions")
async def toggle_reaction(
        message_id: str,
        data: ReactionRequest,
        current_user=Depends(get_current_user),
        service: MessageService = Depends(get_message_service),
):
    return await service.toggle_reaction(message_id, current_user.id, data.emoji)


@message_router.post("/{message_id}/view")
async def view_message(
        message_id: str,
        service: MessageService = Depends(get_message_service),
):
    await service.view_message(message_id)
    return {"status": "ok"}

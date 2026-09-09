import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from fastapi import HTTPException

from app.bot.services.quiz_room import (
    publish_room,
    queue_room_maintenance,
    registered_user,
    send_room_start_to_participants,
)
from app.core.database.base import AsyncSessionLocal
from app.services.quiz.multiplayer import MultiplayerQuizService

router = Router()
logger = logging.getLogger(__name__)


def room_session_id(data: str | None, prefix: str) -> int | None:
    value = (data or "").removeprefix(prefix)
    return int(value) if value.isdigit() else None


@router.callback_query(F.data.startswith("room:start:"))
async def start_room(callback: CallbackQuery):
    session_id = room_session_id(callback.data, "room:start:")
    if session_id is None:
        await callback.answer("Xona havolasi yaroqsiz.", show_alert=True)
        return

    try:
        user = await registered_user(callback.from_user.id)
        async with AsyncSessionLocal() as db:
            session = await MultiplayerQuizService(db).start(session_id, user)
            deadline = session.deadline_at
    except HTTPException as exc:
        await callback.answer(str(exc.detail), show_alert=True)
        return
    except Exception:
        logger.exception("Could not start Telegram room %s", session_id)
        queue_room_maintenance(session_id)
        await callback.answer("Xonani boshlashda xatolik yuz berdi.", show_alert=True)
        return
    queue_room_maintenance(session_id, eta=deadline)
    try:
        await publish_room(callback.bot, session_id)
    except Exception:
        logger.exception("Could not publish started Telegram room %s", session_id)
        queue_room_maintenance(session_id)
    try:
        await send_room_start_to_participants(callback.bot, session_id)
    except Exception:
        logger.exception("Could not send Telegram room %s start links", session_id)
    await callback.answer("Test boshlandi.")


@router.callback_query(F.data.startswith("room:refresh:"))
async def refresh_room(callback: CallbackQuery):
    session_id = room_session_id(callback.data, "room:refresh:")
    if session_id is None:
        await callback.answer("Xona havolasi yaroqsiz.", show_alert=True)
        return
    try:
        await publish_room(callback.bot, session_id)
    except HTTPException as exc:
        await callback.answer(str(exc.detail), show_alert=True)
        return
    except Exception:
        logger.exception("Could not refresh Telegram room %s", session_id)
        queue_room_maintenance(session_id)
        await callback.answer("Xonani yangilab bo'lmadi.", show_alert=True)
        return
    await callback.answer("Yangilandi.")

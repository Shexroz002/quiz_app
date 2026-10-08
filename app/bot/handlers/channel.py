"""Publishing a quiz to a Telegram channel or group.

The bot never reads channel posts -- a channel post carries no sender, so there
is nobody to check rights against. The target chat comes from Telegram's own
chat picker (or, as a fallback for a channel the picker cannot offer yet, from
a forwarded post), and the rights are verified again before anything is posted.
"""

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from fastapi import HTTPException

from app.bot.handlers.menu import show_quiz_catalog
from app.bot.keyboards.channel import (
    CANCEL_TEXT,
    CHANNEL_NEW,
    CHANNEL_PICK,
    CHANNEL_REQUEST_ID,
    GROUP_NEW,
    GROUP_REQUEST_ID,
    chat_list_keyboard,
    chat_picker_keyboard,
    parse_channel_id,
)
from app.bot.keyboards.reply import main_menu_keyboard
from app.bot.services.channels import CHANNEL, GROUP, remember_chat, remembered_chats
from app.bot.services.quiz_room import ensure_publish_rights
from app.bot.states import CHANNEL_TARGET_KEY, ChannelQuizState
from app.bot.utils.registration import get_user_by_telegram_id

router = Router()
logger = logging.getLogger(__name__)

CHANNEL_PICK_PROMPT = (
    "\U0001F4E3 <b>Kanal testi</b>\n\n"
    "Quyidagi tugma orqali kanalni tanlang. Ro'yxatda siz administrator bo'lgan "
    "va bot post yubora oladigan kanallar ko'rinadi.\n\n"
    "Kanal ro'yxatda yo'qmi? Botni o'sha kanalga administrator qilib qo'shing "
    "(«Post yuborish» huquqi bilan) yoki kanaldan istalgan postni menga forward qiling."
)

GROUP_PICK_PROMPT = (
    "\U0001F465 <b>Guruh testi</b>\n\n"
    "Quyidagi tugma orqali guruhni tanlang. Ro'yxatda siz administrator bo'lgan "
    "va bot a'zo bo'lgan guruhlar ko'rinadi.\n\n"
    "Guruh ro'yxatda yo'qmi? Avval botni o'sha guruhga qo'shing."
)

CHANNEL_CHOICE_PROMPT = "\U0001F4E3 <b>Kanal testi</b>\n\nQaysi kanalga joylaymiz?"
GROUP_CHOICE_PROMPT = "\U0001F465 <b>Guruh testi</b>\n\nQaysi guruhga joylaymiz?"


async def offer_chat_picker(message: Message, state: FSMContext, *, is_channel: bool) -> None:
    await state.set_state(None)
    await state.update_data(**{CHANNEL_TARGET_KEY: None})
    await message.answer(
        CHANNEL_PICK_PROMPT if is_channel else GROUP_PICK_PROMPT,
        reply_markup=chat_picker_keyboard(is_channel=is_channel),
        parse_mode="HTML",
    )


async def registered(event: Message | CallbackQuery):
    user = await get_user_by_telegram_id(event.from_user.id)
    if user is None or not user.is_active:
        warning = "Avval /start orqali ro'yxatdan o'ting."
        if isinstance(event, CallbackQuery):
            await event.answer(warning, show_alert=True)
        else:
            await event.answer(warning)
        return None
    return user


async def offer_remembered_or_picker(
    message: Message, state: FSMContext, user, *, is_channel: bool
) -> None:
    chats = await remembered_chats(user.id, CHANNEL if is_channel else GROUP)
    if not chats:
        await offer_chat_picker(message, state, is_channel=is_channel)
        return

    await state.set_state(None)
    await state.update_data(**{CHANNEL_TARGET_KEY: None})
    await message.answer(
        CHANNEL_CHOICE_PROMPT if is_channel else GROUP_CHOICE_PROMPT,
        reply_markup=chat_list_keyboard(chats, is_channel=is_channel),
        parse_mode="HTML",
    )


@router.message(Command("kanal"))
async def start_channel_flow(message: Message, state: FSMContext) -> None:
    user = await registered(message)
    if user is None:
        return
    await offer_remembered_or_picker(message, state, user, is_channel=True)


@router.message(Command("challenge"))
async def start_group_flow(message: Message, state: FSMContext) -> None:
    """``/challenge`` inside the bot: pick a group, then publish into it.

    Typed in the group itself the command still opens the live waiting room --
    that handler lives in ``handlers/challenge.py`` and is untouched, because
    this router only ever sees private chats.
    """
    user = await registered(message)
    if user is None:
        return
    await offer_remembered_or_picker(message, state, user, is_channel=False)


@router.callback_query(F.data.in_({CHANNEL_NEW, GROUP_NEW}))
async def connect_another_chat(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await offer_chat_picker(
        callback.message, state, is_channel=callback.data == CHANNEL_NEW
    )


@router.callback_query(F.data.startswith(CHANNEL_PICK))
async def pick_remembered_channel(callback: CallbackQuery, state: FSMContext) -> None:
    chat_id = parse_channel_id(callback.data)
    if chat_id is None or callback.message is None:
        await callback.answer("Kanal tanlovi yaroqsiz.", show_alert=True)
        return
    if await registered(callback) is None:
        return
    # A remembered channel is only a shortcut: the rights are asked for again.
    try:
        await ensure_publish_rights(callback.bot, callback.from_user.id, chat_id)
    except HTTPException as exc:
        await callback.answer(str(exc.detail), show_alert=True)
        return

    await callback.answer()
    await state.set_state(None)
    await state.update_data(**{CHANNEL_TARGET_KEY: chat_id})
    await show_quiz_catalog(callback, state, page=1, friends_mode=True)


@router.message(F.chat_shared)
async def receive_picked_chat(message: Message, state: FSMContext) -> None:
    """Telegram hands back the chat the user picked from their own list."""
    shared = message.chat_shared
    logger.info(
        "Chat picked: request_id=%s chat_id=%s title=%r",
        shared.request_id,
        shared.chat_id,
        shared.title,
    )
    if shared.request_id not in (CHANNEL_REQUEST_ID, GROUP_REQUEST_ID):
        return
    is_channel = shared.request_id == CHANNEL_REQUEST_ID

    user = await registered(message)
    if user is None:
        return
    try:
        await ensure_publish_rights(message.bot, message.from_user.id, shared.chat_id)
    except HTTPException as exc:
        logger.info("Picked chat %s refused: %s", shared.chat_id, exc.detail)
        await message.answer(str(exc.detail), reply_markup=main_menu_keyboard())
        return

    title = shared.title or ("Kanal" if is_channel else "Guruh")
    await remember_chat(user.id, shared.chat_id, title, CHANNEL if is_channel else GROUP)

    await state.set_state(None)
    await state.update_data(**{CHANNEL_TARGET_KEY: shared.chat_id})
    icon = "\U0001F4E3" if is_channel else "\U0001F465"
    await message.answer(
        f"{icon} <b>{title}</b> tanlandi.\n\nEndi joylanadigan testni tanlang.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await show_quiz_catalog(message, state, page=1, friends_mode=True)


@router.message(F.text == CANCEL_TEXT)
async def cancel_chat_picker(message: Message, state: FSMContext) -> None:
    await state.set_state(None)
    await state.update_data(**{CHANNEL_TARGET_KEY: None})
    await message.answer("Bekor qilindi.", reply_markup=main_menu_keyboard())


def forwarded_channel(message: Message):
    """The channel a message was forwarded from, across both Bot API shapes."""
    chat = message.forward_from_chat or getattr(message.forward_origin, "chat", None)
    if chat is None or chat.type != ChatType.CHANNEL:
        return None
    return chat


@router.message(ChannelQuizState.waiting_for_channel, F.forward_from_chat | F.forward_origin)
async def receive_channel(message: Message, state: FSMContext) -> None:
    """Fallback for a channel the picker cannot offer yet."""
    channel = forwarded_channel(message)
    if channel is None:
        await message.answer("Bu post kanaldan emas. Kanaldagi postni forward qiling.")
        return

    try:
        await ensure_publish_rights(message.bot, message.from_user.id, channel.id)
    except HTTPException as exc:
        await message.answer(str(exc.detail))
        return

    user = await registered(message)
    if user is None:
        return
    await remember_chat(user.id, channel.id, channel.title or "Kanal", CHANNEL)

    await state.set_state(None)
    await state.update_data(**{CHANNEL_TARGET_KEY: channel.id})
    await message.answer(
        f"\U0001F4E3 <b>{channel.title}</b> ulandi.\n\nEndi kanalga joylanadigan testni tanlang.",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    await show_quiz_catalog(message, state, page=1, friends_mode=True)

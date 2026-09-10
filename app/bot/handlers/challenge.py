import hashlib
import hmac

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.deep_linking import create_start_link
from fastapi import HTTPException

from app.bot.handlers.menu import (
    custom_duration_values,
    get_telegram_user_quiz,
    prepare_custom_duration,
    remove_catalog_messages,
    return_to_quiz_catalog,
    show_duration_menu,
    show_quiz_catalog,
)
from app.bot.keyboards.inline import CHALLENGE_CALLBACK_PREFIX, challenge_callback
from app.bot.services.quiz_room import create_room, parse_duration
from app.bot.states import QuizDurationState
from app.bot.utils.registration import get_user_by_telegram_id
from app.core.config import settings

router = Router()


CALLBACK_OWNER_ALERT = "Bu tanlov boshqa foydalanuvchiga tegishli."
CHALLENGE_GROUP_CHAT_ID = "challenge_group_chat_id"
CHALLENGE_GROUP_MESSAGE_ID = "challenge_group_message_id"
GROUP_ADMIN_ALERT = "Faqat guruh administratorlari test xonasini yarata oladi."


async def is_group_admin(bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        return False
    return member.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
    }


def parse_challenge_callback(data: str | None) -> tuple[int, str, tuple[int, ...]] | None:
    parts = (data or "").split(":")
    if len(parts) < 3 or parts[0] != CHALLENGE_CALLBACK_PREFIX.removesuffix(":"):
        return None
    if not parts[1].isdigit() or any(not value.isdigit() for value in parts[3:]):
        return None
    return int(parts[1]), parts[2], tuple(int(value) for value in parts[3:])


def challenge_action_prefix(owner_id: int, action: str) -> str:
    return f"{challenge_callback(owner_id, action)}:"


def parse_challenge_start_payload(
    payload: str | None,
) -> tuple[int, int, int] | None:
    parts = (payload or "").split("_")
    if len(parts) != 5 or parts[0] != "challenge":
        return None
    owner_id, chat_id, message_id, signature = parts[1:]
    if not owner_id.isdigit() or not message_id.isdigit():
        return None
    if not chat_id.removeprefix("-").isdigit():
        return None
    unsigned = "_".join(parts[:4])
    expected = hmac.new(
        settings.SECRET_KEY.encode(),
        unsigned.encode(),
        hashlib.sha256,
    ).hexdigest()[:12]
    if not hmac.compare_digest(signature, expected):
        return None
    return int(owner_id), int(chat_id), int(message_id)


def challenge_start_payload(owner_id: int, chat_id: int, message_id: int) -> str:
    unsigned = f"challenge_{owner_id}_{chat_id}_{message_id}"
    signature = hmac.new(
        settings.SECRET_KEY.encode(),
        unsigned.encode(),
        hashlib.sha256,
    ).hexdigest()[:12]
    return f"{unsigned}_{signature}"


async def start_private_challenge(
    message: Message,
    state: FSMContext,
    payload: str,
) -> bool:
    target = parse_challenge_start_payload(payload)
    if target is None:
        if payload.startswith("challenge_"):
            await message.answer("Xona sozlash havolasi yaroqsiz.")
            return True
        return False
    owner_id, group_chat_id, group_message_id = target
    if message.from_user is None or message.from_user.id != owner_id:
        await message.answer(CALLBACK_OWNER_ALERT)
        return True
    if not await is_group_admin(message.bot, group_chat_id, owner_id):
        await message.answer(GROUP_ADMIN_ALERT)
        return True
    await state.clear()
    await state.update_data(
        **{
            CHALLENGE_GROUP_CHAT_ID: group_chat_id,
            CHALLENGE_GROUP_MESSAGE_ID: group_message_id,
        }
    )
    await show_quiz_catalog(
        message,
        state,
        page=1,
        challenge_owner_id=owner_id,
    )
    return True


async def challenge_group_target(
    state: FSMContext,
) -> tuple[int, int] | None:
    data = await state.get_data()
    chat_id = data.get(CHALLENGE_GROUP_CHAT_ID)
    message_id = data.get(CHALLENGE_GROUP_MESSAGE_ID)
    if not isinstance(chat_id, int) or not isinstance(message_id, int):
        return None
    return chat_id, message_id


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    Command("challenge"),
)
async def challenge(message: Message, state: FSMContext) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        return
    if not await is_group_admin(message.bot, message.chat.id, telegram_user.id):
        await message.answer(GROUP_ADMIN_ALERT)
        return

    user = await get_user_by_telegram_id(telegram_user.id)
    if user is None or not user.is_active:
        registration_url = await create_start_link(message.bot, "challenge")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Shaxsiy chatda ro'yxatdan o'tish",
                        url=registration_url,
                    )
                ]
            ]
        )
        await message.answer(
            "Guruh testidan foydalanish uchun avval bot bilan shaxsiy chatda "
            "ro'yxatdan o'ting.",
            reply_markup=keyboard,
        )
        return

    room_message = await message.answer(
        "🎯 <b>Test xonasi</b>\n\n"
        "Xonani sozlashni shaxsiy bot chatida davom ettiring.",
        parse_mode="HTML",
    )
    configuration_url = await create_start_link(
        message.bot,
        challenge_start_payload(
            telegram_user.id,
            message.chat.id,
            room_message.message_id,
        ),
    )
    await room_message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(
                text="⚙️ Test xonasini sozlash",
                url=configuration_url,
            )]],
        )
    )


@router.callback_query(
    F.message.chat.type == ChatType.PRIVATE,
    F.data.startswith(CHALLENGE_CALLBACK_PREFIX),
)
async def handle_challenge_callback(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    parsed = parse_challenge_callback(callback.data)
    if parsed is None:
        await callback.answer("Tanlov yaroqsiz.", show_alert=True)
        return

    owner_id, action, values = parsed
    if callback.from_user.id != owner_id:
        await callback.answer(CALLBACK_OWNER_ALERT, show_alert=True)
        return
    if callback.message is None:
        await callback.answer("Xabar topilmadi.", show_alert=True)
        return

    prefix = challenge_action_prefix(owner_id, action)
    if action == "page" and len(values) == 1:
        await show_quiz_catalog(
            callback,
            state,
            page=values[0],
            challenge_owner_id=owner_id,
        )
        return
    if action == "current" and not values:
        await callback.answer()
        return
    if action == "duration" and len(values) == 2:
        await show_duration_menu(
            callback,
            state,
            prefix=prefix,
            challenge_owner_id=owner_id,
        )
        return
    if action == "custom" and len(values) == 2:
        await prepare_custom_duration(
            callback,
            state,
            prefix=prefix,
            target_state=QuizDurationState.waiting_for_group_challenge_custom_minutes,
            challenge_owner_id=owner_id,
        )
        return
    if action == "card" and len(values) == 2:
        await return_to_quiz_catalog(
            callback,
            state,
            prefix=prefix,
            challenge_owner_id=owner_id,
        )
        return
    if action != "set" or len(values) != 3:
        await callback.answer("Tanlov yaroqsiz.", show_alert=True)
        return

    quiz_id, minutes, _ = values
    if await get_telegram_user_quiz(owner_id, quiz_id) is None:
        await callback.answer(
            "Test topilmadi yoki sizga tegishli emas.",
            show_alert=True,
        )
        return
    target = await challenge_group_target(state)
    if target is None:
        await callback.answer(
            "Guruhdagi xona sozlamasi topilmadi. /challenge ni qayta yuboring.",
            show_alert=True,
        )
        return
    group_chat_id, group_message_id = target
    if not await is_group_admin(callback.bot, group_chat_id, owner_id):
        await callback.answer(GROUP_ADMIN_ALERT, show_alert=True)
        return
    try:
        await create_room(
            callback.bot,
            owner_id,
            group_chat_id,
            group_message_id,
            quiz_id,
            parse_duration(minutes),
        )
    except HTTPException as exc:
        await callback.answer(str(exc.detail), show_alert=True)
        return
    await remove_catalog_messages(
        callback.bot,
        callback.message.chat.id,
        state,
        keep_message_id=callback.message.message_id,
        include_header=True,
    )
    await callback.message.edit_text(
        "✅ Xona guruhda yaratildi.",
    )
    await state.clear()
    await callback.answer("Xona yaratildi.")


@router.message(
    F.chat.type == ChatType.PRIVATE,
    QuizDurationState.waiting_for_group_challenge_custom_minutes,
)
async def receive_group_challenge_custom_duration(
    message: Message,
    state: FSMContext,
) -> None:
    if message.from_user is None:
        await state.clear()
        return

    data = await state.get_data()
    if data.get("challenge_owner_id") != message.from_user.id:
        await state.clear()
        return

    values = await custom_duration_values(message, state)
    if values is None:
        return
    quiz, configuration_message_id, minutes = values
    target = await challenge_group_target(state)
    if target is None:
        await state.clear()
        await message.answer(
            "Guruhdagi xona sozlamasi topilmadi. Guruhda /challenge ni qayta yuboring."
        )
        return
    group_chat_id, group_message_id = target
    if not await is_group_admin(
        message.bot,
        group_chat_id,
        message.from_user.id,
    ):
        await state.clear()
        await message.answer(GROUP_ADMIN_ALERT)
        return

    try:
        await create_room(
            message.bot,
            message.from_user.id,
            group_chat_id,
            group_message_id,
            quiz["id"],
            minutes,
        )
    except HTTPException as exc:
        await message.answer(f"❗ {exc.detail}")
        return

    try:
        await message.bot.edit_message_text(
            "✅ Xona guruhda yaratildi.",
            chat_id=message.chat.id,
            message_id=configuration_message_id,
        )
    except TelegramBadRequest:
        pass
    await state.clear()
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

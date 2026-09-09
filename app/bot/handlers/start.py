from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from fastapi import HTTPException

from app.bot.handlers.menu import show_main_menu
from app.bot.keyboards.inline import grade_keyboard
from app.bot.keyboards.reply import contact_keyboard
from app.bot.states import RegistrationState
from app.bot.services.quiz_room import enter_room
from app.bot.utils.registration import (
    GRADE_TO_EDUCATION_LEVEL,
    RegistrationConflictError,
    get_user_by_telegram_id,
    register_telegram_student,
)
from app.bot.utils.profile_photo import save_telegram_profile_photo

router = Router()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, command: CommandObject):
    telegram_user = message.from_user
    if telegram_user is None:
        return

    room_code = None
    if command.args and command.args.startswith("room_"):
        candidate = command.args.removeprefix("room_").upper()
        if len(candidate) == 6 and candidate.isalnum() and candidate.isascii():
            room_code = candidate

    existing_user = await get_user_by_telegram_id(telegram_user.id)
    if existing_user:
        await state.clear()
        if room_code:
            try:
                await enter_room(message, room_code)
            except HTTPException as exc:
                await message.answer(str(exc.detail))
        else:
            await show_main_menu(message)
        return

    await state.clear()
    await state.set_state(RegistrationState.waiting_for_contact)
    await state.update_data(
        telegram_id=str(telegram_user.id),
        first_name=telegram_user.first_name or "",
        last_name=telegram_user.last_name or "",
        pending_room_code=room_code,
    )
    await message.answer("Telefon raqamingizni yuboring.", reply_markup=contact_keyboard())


@router.message(RegistrationState.waiting_for_contact, F.contact)
async def receive_contact(message: Message, state: FSMContext):
    telegram_user = message.from_user
    contact = message.contact
    if telegram_user is None or contact is None:
        return

    if contact.user_id != telegram_user.id:
        await message.answer("Faqat o'zingizning telefon raqamingizni yuboring.")
        return

    existing_user = await get_user_by_telegram_id(telegram_user.id)
    if existing_user:
        await state.clear()
        await show_main_menu(message)
        return

    await state.update_data(phone_number=contact.phone_number)
    await state.set_state(RegistrationState.waiting_for_grade)
    await message.answer(
        "Sinfingizni tanlang.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Sinf:", reply_markup=grade_keyboard())


@router.message(RegistrationState.waiting_for_contact)
async def reject_non_contact(message: Message):
    await message.answer("Iltimos, pastdagi tugma orqali telefon raqamingizni yuboring.")


@router.callback_query(RegistrationState.waiting_for_grade, F.data.startswith("grade:"))
async def receive_grade(callback: CallbackQuery, state: FSMContext, bot: Bot):
    telegram_user = callback.from_user
    grade = callback.data.split(":", 1)[1] if callback.data else ""
    if grade not in GRADE_TO_EDUCATION_LEVEL:
        await callback.answer("Noto'g'ri sinf tanlandi.", show_alert=True)
        return

    existing_user = await get_user_by_telegram_id(telegram_user.id)
    if existing_user:
        await state.clear()
        await show_main_menu(callback.message)
        await callback.answer()
        return

    data = await state.get_data()
    profile_image = await save_telegram_profile_photo(bot, telegram_user.id)
    try:
        await register_telegram_student(
            telegram_id=data["telegram_id"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone_number=data["phone_number"],
            grade=grade,
            profile_image=profile_image,
        )
    except RegistrationConflictError as exc:
        await callback.answer()
        await callback.message.answer(str(exc))
        return

    await state.clear()
    await callback.message.answer("Ro'yxatdan o'tish yakunlandi.")
    if data.get("pending_room_code"):
        try:
            await enter_room(callback.message, data["pending_room_code"])
        except HTTPException as exc:
            await callback.message.answer(str(exc.detail))
    else:
        await show_main_menu(callback.message)
    await callback.answer()

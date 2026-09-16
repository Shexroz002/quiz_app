from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from fastapi import HTTPException

from app.bot.handlers.challenge import start_private_challenge
from app.bot.handlers.menu import show_main_menu
from app.bot.keyboards.inline import (
    REG_SUBJECT_DONE,
    REG_SUBJECT_TOGGLE,
    registration_subject_keyboard,
)
from app.bot.keyboards.reply import contact_keyboard
from app.bot.states import RegistrationState
from app.bot.services.quiz_room import enter_room
from app.bot.utils.registration import (
    RegistrationConflictError,
    get_user_by_telegram_id,
    register_telegram_student,
)
from app.bot.utils.subjects import load_subjects
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
        elif command.args and await start_private_challenge(
            message,
            state,
            command.args,
        ):
            return
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

    subjects = await load_subjects()
    if not subjects:
        await message.answer(
            "Fanlar ro'yxati hozircha bo'sh. Administratorga murojaat qiling.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    await state.update_data(phone_number=contact.phone_number, selected_subject_ids=[])
    await state.set_state(RegistrationState.waiting_for_subjects)
    await message.answer(
        "Qaysi fanlar bo'yicha test ishlaysiz?",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "Bir nechtasini tanlashingiz mumkin:",
        reply_markup=registration_subject_keyboard(subjects, []),
    )


@router.message(RegistrationState.waiting_for_contact)
async def reject_non_contact(message: Message):
    await message.answer("Iltimos, pastdagi tugma orqali telefon raqamingizni yuboring.")


@router.callback_query(
    RegistrationState.waiting_for_subjects,
    F.data.startswith(REG_SUBJECT_TOGGLE),
)
async def toggle_subject(callback: CallbackQuery, state: FSMContext):
    subject_id = (callback.data or "").rsplit(":", 1)[-1]
    if not subject_id.isdigit():
        await callback.answer("Fan tanlanmadi.", show_alert=True)
        return

    subjects = await load_subjects()
    known_ids = {subject["id"] for subject in subjects}
    subject_id = int(subject_id)
    if subject_id not in known_ids:
        await callback.answer("Bu fan topilmadi.", show_alert=True)
        return

    data = await state.get_data()
    # Faqat mavjud fanlar qoladi: ro'yxatdan o'chirilgan fan tanlovda osilib qolmaydi.
    selected = [value for value in data.get("selected_subject_ids", []) if value in known_ids]
    if subject_id in selected:
        selected.remove(subject_id)
    else:
        selected.append(subject_id)
    await state.update_data(selected_subject_ids=selected)

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(
            reply_markup=registration_subject_keyboard(subjects, selected)
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(RegistrationState.waiting_for_subjects, F.data == REG_SUBJECT_DONE)
async def finish_registration(callback: CallbackQuery, state: FSMContext, bot: Bot):
    telegram_user = callback.from_user
    data = await state.get_data()
    selected = data.get("selected_subject_ids") or []
    if not selected:
        await callback.answer("Kamida bitta fan tanlang.", show_alert=True)
        return

    existing_user = await get_user_by_telegram_id(telegram_user.id)
    if existing_user:
        await state.clear()
        await show_main_menu(callback.message)
        await callback.answer()
        return

    profile_image = await save_telegram_profile_photo(bot, telegram_user.id)
    try:
        await register_telegram_student(
            telegram_id=data["telegram_id"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone_number=data["phone_number"],
            subject_ids=selected,
            profile_image=profile_image,
        )
    except RegistrationConflictError as exc:
        await callback.answer()
        await callback.message.answer(str(exc))
        return

    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Ro'yxatdan o'tish yakunlandi.")
    if data.get("pending_room_code"):
        try:
            await enter_room(callback.message, data["pending_room_code"])
        except HTTPException as exc:
            await callback.message.answer(str(exc.detail))
    else:
        await show_main_menu(callback.message)
    await callback.answer()

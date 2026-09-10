"""Telegram transport and durable room message delivery."""
import hashlib
import logging
from html import escape

from aiogram.exceptions import TelegramBadRequest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.bot.keyboards.quiz_room import (
    host_room_keyboard,
    player_keyboard,
    room_keyboard,
    room_link,
    room_webapp_url,
)
from app.bot.models import TelegramQuizRoom
from app.bot.utils.registration import get_user_by_telegram_id
from app.core.database.base import AsyncSessionLocal
from app.models import Quiz, QuizSession, SessionParticipant, User
from app.services.quiz.multiplayer import MultiplayerQuizService

logger = logging.getLogger(__name__)
MAX_ROOM_PARTICIPANTS = 20
MAX_DURATION_MINUTES = 10080
ROOM_MESSAGE_REVISION_VERSION = "4"
GROUP_ROOM_MESSAGE_REVISION_VERSION = "1"
ROOM_PARTICIPANT_PREVIEW_LIMIT = 8
GROUP_LEADERBOARD_PREVIEW_LIMIT = MAX_ROOM_PARTICIPANTS
GROUP_ROOM_MESSAGE_MAX_LENGTH = 4000


def parse_duration(value):
    raw = str(value).strip()
    if not raw.isascii() or not raw.isdigit() or len(raw) > 8:
        raise HTTPException(400, "Vaqtni musbat butun son bilan kiriting. Masalan: 25.")
    minutes = int(raw)
    if not 1 <= minutes <= MAX_DURATION_MINUTES:
        raise HTTPException(400, f"Vaqt 1 dan {MAX_DURATION_MINUTES} daqiqagacha bo'lishi kerak.")
    return minutes


async def registered_user(telegram_id):
    user = await get_user_by_telegram_id(telegram_id)
    if not user or not user.is_active:
        raise HTTPException(403, "Avval /start orqali ro'yxatdan o'ting.")
    return user


def queue_room_maintenance(session_id, *, eta=None):
    try:
        from app.core.celery_app import celery_app

        celery_app.send_task("telegram.maintain_room", args=[session_id], eta=eta)
    except Exception:
        logger.exception("Could not queue Telegram room maintenance for session %s", session_id)


async def create_room(bot, telegram_id, chat_id, message_id, quiz_id, duration):
    minutes = parse_duration(duration)
    user = await registered_user(telegram_id)
    username = (await bot.get_me()).username
    host_control = None
    async with AsyncSessionLocal() as db:
        # Deduplicate even callbacks from different users on the same shared message.
        await db.execute(select(func.pg_advisory_xact_lock(
            func.hashtextextended(f"telegram-room:{chat_id}:{message_id}", 0)
        )))
        existing = (await db.execute(select(TelegramQuizRoom).where(
            TelegramQuizRoom.chat_id == chat_id, TelegramQuizRoom.message_id == message_id
        ))).scalar_one_or_none()
        if existing:
            session = await db.get(QuizSession, existing.session_id)
            if session.host_id != user.id:
                raise HTTPException(403, "Bu xonani boshqa foydalanuvchi yaratgan.")
            session_id = existing.session_id
        else:
            service = MultiplayerQuizService(db)
            session = await service.create_managed_session(
                quiz_id=quiz_id,
                duration_minutes=minutes,
                max_participants=MAX_ROOM_PARTICIPANTS,
                user=user,
                commit=False,
            )
            session_id = session.id
            db.add(TelegramQuizRoom(
                session_id=session_id, chat_id=chat_id, message_id=message_id,
                bot_username=username,
            ))
            if chat_id < 0:
                quiz = await db.get(Quiz, session.quiz_id)
                participants = await service.participant_repo.get_participant_list(
                    session_id,
                    pagination=False,
                )
                question_count = await service.quiz_repo.quiz_question_count(quiz.id)
                host_control = (
                    format_host_waiting_room(
                        quiz,
                        session,
                        len(participants),
                        question_count,
                    ),
                    host_room_keyboard(session),
                )
        await db.commit()
    # The DB record also acts as an outbox; Celery Beat recovers failed edits.
    try:
        await publish_room(bot, session_id)
    except Exception:
        logger.exception("Could not publish Telegram room %s", session_id)
        queue_room_maintenance(session_id)
    if host_control is not None:
        try:
            text, keyboard = host_control
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Could not send Telegram room %s host control",
                session_id,
            )
    return session_id


def format_leaderboard(quiz, session, rows):
    total_questions = rows[0]["total_questions"] if rows else 0
    lines = [
        "🏆 <b>Test yakunlandi!</b>",
        "",
        f"📚 {escape((quiz.subject or 'Test')[:80])}",
        f"📝 {escape(quiz.title[:500])}",
        "",
        f"⏱ {session.duration_minutes} daqiqa",
        f"👥 {len(rows)} ishtirokchi",
        f"❓ {total_questions} ta savol",
        "",
        "━━━━━━━━━━━━━━",
    ]
    for index, row in enumerate(rows, 1):
        rank = {1: "🥇", 2: "🥈", 3: "🥉"}.get(index, f"{index}.")
        total = row["total_questions"]
        percent = round(100 * row["correct_answers"] / total) if total else 0
        minutes, seconds = divmod(row["spend_time"], 60)
        lines.extend([
            "",
            f"{rank} <b>{escape(row['display_name'][:80])}</b>",
            f"✅ {row['correct_answers']} / {total}",
            f"🎯 {percent}%",
            f"⏱ {minutes:02}:{seconds:02}",
        ])
    lines.extend([
        "",
        "━━━━━━━━━━━━━━",
        "",
        "💪 Har bir test — yangi tajriba.",
        "Keyingi safar yanada yaxshi natija ko‘rsatishga harakat qiling!",
    ])
    return "\n".join(lines)


def format_group_leaderboard(quiz, session, rows):
    total_questions = rows[0]["total_questions"] if rows else 0
    lines = [
        "🏆 <b>Test yakunlandi!</b>",
        "",
        f"📚 {escape((quiz.subject or 'Test')[:80])}",
        f"📝 {escape(quiz.title[:180])}",
        "",
        f"⏱ {session.duration_minutes} daqiqa",
        f"👥 {len(rows)} ishtirokchi",
        f"❓ {total_questions} savol",
        "",
        "━━━━━━━━━━━━━━",
        "",
        "🏅 <b>LEADERBOARD</b>",
    ]
    footer = [
        "",
        "━━━━━━━━━━━━━━",
        "",
        "🔥 Zo‘r bellashuv!",
        "Keyingi testda kim 1-o‘rinni oladi?",
    ]
    visible_rows = rows[:GROUP_LEADERBOARD_PREVIEW_LIMIT]
    for position, row in enumerate(visible_rows, 1):
        rank = {1: "🥇", 2: "🥈", 3: "🥉"}.get(position, f"{position}.")
        total = row["total_questions"]
        correct = row["correct_answers"]
        percent = round(100 * correct / total) if total else 0
        minutes, seconds = divmod(row["spend_time"], 60)
        result_lines = [
            "",
            f"{rank} <b>{escape(row['display_name'][:60])}</b>",
            f"✅ {correct}/{total}  •  🎯 {percent}%  •  "
            f"⏱ {minutes:02}:{seconds:02}",
        ]
        remaining = len(rows) - position
        overflow_lines = ["", f"… yana {remaining} ishtirokchi"] if remaining else []
        projected_text = "\n".join([*lines, *result_lines, *overflow_lines, *footer])
        if len(projected_text) > GROUP_ROOM_MESSAGE_MAX_LENGTH:
            remaining = len(rows) - position + 1
            lines.extend(["", f"… yana {remaining} ishtirokchi"])
            break
        lines.extend(result_lines)
    else:
        remaining = len(rows) - len(visible_rows)
        if remaining:
            lines.extend(["", f"… yana {remaining} ishtirokchi"])
    lines.extend(footer)
    return "\n".join(lines)


def format_room_join_confirmation(quiz, session, participants):
    host = next(
        (participant for participant in participants if participant["is_host"]),
        None,
    )
    host_name = "Xona egasi"
    if host is not None:
        host_name = MultiplayerQuizService.participant_display_name(
            host["first_name"],
            host["last_name"],
            host["nickname"],
        )
    quiz_name = " — ".join(
        part for part in (quiz.subject, quiz.title) if part
    ) or "Test"
    return (
        "🎉 <b>Xonaga muvaffaqiyatli qo‘shildingiz!</b>\n\n"
        f"📘 {escape(quiz_name[:500])}\n"
        f"⏱ Test vaqti: {session.duration_minutes} daqiqa\n"
        f"👥 Ishtirokchilar: {len(participants)}/{session.max_participants}\n\n"
        f"👑 Xona egasi: {escape(host_name[:100])}\n"
        "🟡 Holat: Boshlanishi kutilmoqda\n\n"
        "Xona egasi testni boshlashi bilan siz testni ishlashni boshlashingiz mumkin."
    )


def format_room_start_message(quiz, session):
    quiz_name = " — ".join(
        part for part in (quiz.subject, quiz.title) if part
    ) or "Test"
    return (
        "🚀 <b>Test boshlandi!</b>\n\n"
        f"📚 {escape(quiz_name[:500])}\n"
        f"⏱ Vaqt: {session.duration_minutes} daqiqa\n\n"
        "Savollar tayyor. Omad tilaymiz!\n"
        "Testni boshlash uchun quyidagi tugmani bosing. 👇"
    )


def format_host_waiting_room(quiz, session, participant_count, question_count):
    return (
        "🎯 <b>Test xonasi tayyor!</b>\n\n"
        f"📚 {escape((quiz.subject or 'Umumiy')[:80])}\n"
        f"📝 {escape(quiz.title[:180])}\n"
        f"❓ {question_count} savol\n"
        f"⏱ {session.duration_minutes} daqiqa\n\n"
        f"👥 {participant_count}/{session.max_participants} ishtirokchi\n\n"
        "Do‘stlaringiz qo‘shilgach testni boshlang."
    )


def format_private_running_room(quiz, session):
    return (
        "🚀 <b>Test boshlandi!</b>\n\n"
        f"📚 {escape((quiz.subject or 'Umumiy')[:80])}\n"
        f"⏱ {session.duration_minutes} daqiqa\n\n"
        "Omad! Testni boshlash uchun quyidagi tugmani bosing. 👇"
    )


def format_waiting_group_room(quiz, session, participants, question_count):
    participant_lines = []
    for index, participant in enumerate(
        participants[:ROOM_PARTICIPANT_PREVIEW_LIMIT],
        1,
    ):
        display_name = MultiplayerQuizService.participant_display_name(
            participant["first_name"],
            participant["last_name"],
            participant["nickname"],
        )
        participant_lines.append(f"{index}. {escape(display_name[:80])}")
    remaining = len(participants) - len(participant_lines)
    if remaining:
        participant_lines.append(f"… yana {remaining} ishtirokchi")
    participant_preview = "\n".join(participant_lines)
    if participant_preview:
        participant_preview = f"\n{participant_preview}"

    return (
        "🎯 <b>Test xonasi</b>\n\n"
        f"📚 {escape((quiz.subject or 'Umumiy')[:80])}\n"
        f"📝 {escape(quiz.title[:180])}\n"
        f"❓ {question_count} savol\n"
        f"⏱ {session.duration_minutes} daqiqa\n\n"
        f"👥 {len(participants)}/{session.max_participants} ishtirokchi"
        f"{participant_preview}\n"
        "🟡 Boshlanishi kutilmoqda\n\n"
        "Xona egasi testni boshlashini kuting."
    )


def format_running_group_room(quiz, session, participant_count, question_count):
    return (
        "🚀 <b>Test boshlandi!</b>\n\n"
        f"📚 {escape((quiz.subject or 'Umumiy')[:80])}\n"
        f"📝 {escape(quiz.title[:180])}\n"
        f"❓ {question_count} savol\n"
        f"⏱ {session.duration_minutes} daqiqa\n"
        f"👥 {participant_count} ishtirokchi\n\n"
        "Savollar tayyor.\n"
        "Testni ishlashni boshlashingiz mumkin. 👇"
    )


async def publish_room(bot, session_id, session_factory=AsyncSessionLocal):
    async with session_factory() as db:
        service = MultiplayerQuizService(db)
        session = await service.lock_session(session_id)
        room = (await db.execute(select(TelegramQuizRoom).where(
            TelegramQuizRoom.session_id == session_id
        ).with_for_update())).scalar_one()
        if room.leaderboard_delivered_at:
            return

        is_group_chat = room.chat_id < 0
        quiz = await db.get(Quiz, session.quiz_id)
        if session.status == "finished":
            rows = await service.leaderboard(session)
            if is_group_chat:
                text = format_group_leaderboard(quiz, session, rows)
                keyboard = None
            else:
                text = format_leaderboard(quiz, session, rows)
                await bot.send_message(
                    chat_id=room.chat_id,
                    text=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                room.leaderboard_delivered_at = await service.now()
                await db.commit()
                return
        else:
            participants = await service.participant_repo.get_participant_list(
                session_id,
                pagination=False,
            )
            if is_group_chat and session.status == "waiting":
                question_count = await service.quiz_repo.quiz_question_count(quiz.id)
                text = format_waiting_group_room(
                    quiz,
                    session,
                    participants,
                    question_count,
                )
            elif is_group_chat:
                question_count = await service.quiz_repo.quiz_question_count(quiz.id)
                text = format_running_group_room(
                    quiz,
                    session,
                    len(participants),
                    question_count,
                )
            else:
                participant_names = []
                for index, participant in enumerate(participants, 1):
                    display_name = service.participant_display_name(
                        participant["first_name"],
                        participant["last_name"],
                        participant["nickname"],
                    )
                    participant_names.append(
                        f"{index}. {escape(display_name[:80])}"
                    )
                names = "\n".join(participant_names)
                status = (
                    "Boshlanishini kutmoqda"
                    if session.status == "waiting"
                    else "Test boshlandi"
                )
                text = (
                    f"📚 <b>{escape(quiz.title[:180])}</b>\n"
                    f"{escape((quiz.subject or 'Umumiy')[:80])}\n"
                    f"📝 {await service.quiz_repo.quiz_question_count(quiz.id)} ta savol\n"
                    f"⏱ {session.duration_minutes} daqiqa · "
                    f"👥 {len(participants)}/{session.max_participants}\n\n"
                    f"{names}\n\n<b>{status}</b>\n"
                    f"Taklif: {room_link(room.bot_username, session.join_code)}"
                )
            keyboard = room_keyboard(
                session,
                room.bot_username,
                is_host=True,
                group_chat=is_group_chat,
            )
        if is_group_chat:
            revision_payload = (
                f"{GROUP_ROOM_MESSAGE_REVISION_VERSION}:{session.status}:{text}"
            )
        else:
            webapp_url = (
                room_webapp_url(session) if session.status == "running" else ""
            )
            revision_payload = (
                f"{ROOM_MESSAGE_REVISION_VERSION}:{session.status}:"
                f"{webapp_url}:{text}"
            )
        revision = hashlib.sha256(revision_payload.encode()).hexdigest()
        if room.published_revision != revision:
            try:
                await bot.edit_message_text(
                    text, chat_id=room.chat_id, message_id=room.message_id,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )
            except TelegramBadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
            room.published_revision = revision
        if session.status == "finished" and room.leaderboard_delivered_at is None:
            room.leaderboard_delivered_at = await service.now()
        await db.commit()


async def send_room_start_to_participants(
    bot,
    session_id,
    session_factory=AsyncSessionLocal,
):
    async with session_factory() as db:
        session = await db.get(QuizSession, session_id)
        if session is None:
            raise HTTPException(404, "Xona topilmadi.")
        quiz = await db.get(Quiz, session.quiz_id)
        if quiz is None:
            raise HTTPException(404, "Test topilmadi.")
        telegram_ids = (await db.execute(
            select(User.telegram_id)
            .join(SessionParticipant, SessionParticipant.user_id == User.id)
            .where(
                SessionParticipant.session_id == session_id,
                User.telegram_id.is_not(None),
            )
        )).scalars().all()

    keyboard = player_keyboard(session)
    text = format_room_start_message(quiz, session)
    for telegram_id in dict.fromkeys(telegram_ids):
        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        except Exception:
            logger.exception(
                "Could not send room %s start link to Telegram user %s",
                session_id,
                telegram_id,
            )


async def enter_room(message, code):
    user = await registered_user(message.from_user.id)
    async with AsyncSessionLocal() as db:
        service = MultiplayerQuizService(db)
        session = await service.session_repo.get_by_join_code(code)
        room = None
        if session is not None:
            room = (await db.execute(select(TelegramQuizRoom).where(
                TelegramQuizRoom.session_id == session.id
            ))).scalar_one_or_none()
        if session is None or room is None:
            raise HTTPException(404, "Xona topilmadi.")
        session_id = session.id
        session = await service.lock_session(session_id)
        if session.status == "waiting":
            await service.join(session_id, user)
            quiz = await db.get(Quiz, session.quiz_id)
            participants = await service.participant_repo.get_participant_list(
                session_id,
                pagination=False,
            )
            join_confirmation = format_room_join_confirmation(
                quiz,
                session,
                participants,
            )
        else:
            await service.participant(session_id, user.id)
            await service.finalize_quiz_session(session_id)
            quiz = await db.get(Quiz, session.quiz_id)
            join_confirmation = None
        status = session.status
        try:
            keyboard = player_keyboard(session) if status == "running" else None
        except ValueError as exc:
            raise HTTPException(503, "Telegram Mini App HTTPS manzili sozlanmagan.") from exc
        username = room.bot_username
    if status == "running":
        await message.answer(
            format_private_running_room(quiz, session),
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    elif status == "finished":
        await message.answer("Test yakunlangan. Natijalar xona xabarida.")
    else:
        await message.answer(
            join_confirmation,
            reply_markup=room_keyboard(
                session,
                username,
                is_host=session.host_id == user.id,
            ),
            parse_mode="HTML",
        )
    try:
        await publish_room(message.bot, session_id)
    except Exception:
        logger.exception("Could not refresh Telegram room %s after join", session_id)
        queue_room_maintenance(session_id)

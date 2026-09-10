import asyncio

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType

from app.bot.handlers.challenge import router as challenge_router
from app.bot.handlers.menu import router as menu_router
from app.bot.handlers.quiz import router as quiz_router
from app.bot.handlers.quiz_room import router as quiz_room_router
from app.bot.handlers.start import router as start_router
from app.core.config import settings


async def main():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    private_router = Router(name="private")
    private_router.message.filter(F.chat.type == ChatType.PRIVATE)
    private_router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    private_router.include_routers(
        start_router,
        menu_router,
        quiz_router,
    )

    group_router = Router(name="group")
    group_router.message.filter(
        F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
    )
    group_router.callback_query.filter(
        F.message.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP})
    )
    dp.include_routers(
        private_router,
        group_router,
        challenge_router,
        quiz_room_router,
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

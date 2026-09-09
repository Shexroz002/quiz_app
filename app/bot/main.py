import asyncio

from aiogram import Bot, Dispatcher

from app.bot.handlers.menu import router as menu_router
from app.bot.handlers.quiz import router as quiz_router
from app.bot.handlers.quiz_room import router as quiz_room_router
from app.bot.handlers.start import router as start_router
from app.core.config import settings


async def main():
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(menu_router)
    dp.include_router(quiz_router)
    dp.include_router(quiz_room_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

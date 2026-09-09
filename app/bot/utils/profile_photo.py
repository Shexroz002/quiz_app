from io import BytesIO
import os
from uuid import uuid4

from aiogram import Bot

from app.core.config import settings
from app.services.pdf.storage_service import StorageService


class TelegramPhotoUpload:
    content_type = "image/jpeg"

    def __init__(self, data: bytes):
        self._buffer = BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    async def close(self) -> None:
        self._buffer.close()


async def save_telegram_profile_photo(bot: Bot, telegram_user_id: int) -> str | None:
    try:
        photos = await bot.get_user_profile_photos(user_id=telegram_user_id, limit=1)
        if photos.total_count == 0 or not photos.photos:
            return None

        latest_photo = photos.photos[0]
        best_photo = max(
            latest_photo,
            key=lambda photo: (photo.width * photo.height, photo.file_size or 0),
        )

        buffer = await bot.download(best_photo.file_id, destination=BytesIO())
        if buffer is None:
            return None

        file_name = f"telegram_{telegram_user_id}_{uuid4()}.jpg"
        file_path = os.path.join(settings.AVATAR_DIR, file_name)
        db_path = f"{settings.AVATAR_DIR}/{file_name}"

        storage = StorageService(
            upload_dir=settings.AVATAR_DIR,
            max_size_bytes=settings.MAX_PDF_SIZE,
        )
        saved = await storage.save_pdf(TelegramPhotoUpload(buffer.getvalue()), file_path)
        print("Saved:", saved, "Path:", db_path)
        return db_path if saved else None
    except Exception:
        print("Error saving profile photo for user:", telegram_user_id)
        return None

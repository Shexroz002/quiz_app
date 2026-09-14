import os
import uuid

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.services.pdf.storage_service import StorageService

# Kengaytma har doim shu jadvaldan olinadi, hech qachon file.filename dan emas -
# aks holda fayl nomi orqali katalogdan chiqib ketish (path traversal) mumkin bo'ladi.
# SVG qasddan yo'q: /media static sifatida beriladi va inline ochilganda XSS bo'ladi.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    # Rasm
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    # Hujjat
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "text/plain": ".txt",
    "text/csv": ".csv",
    # Audio / video
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    # Arxiv
    "application/zip": ".zip",
    "application/x-7z-compressed": ".7z",
    "application/vnd.rar": ".rar",
}


class ChatAttachmentService:
    def __init__(self, storage: StorageService):
        self.storage = storage

    async def save_attachment(self, file: UploadFile) -> dict:
        extension = ALLOWED_CONTENT_TYPES.get(file.content_type)
        if not extension:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{file.content_type}' turdagi fayl qabul qilinmaydi",
            )

        max_size = self.storage.max_size_bytes
        declared_size = getattr(file, "size", None)
        if declared_size is not None and declared_size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Fayl hajmi {max_size // (1024 * 1024)} MB dan oshmasligi kerak",
            )

        file_name = f"{uuid.uuid4()}{extension}"
        file_path = os.path.join(self.storage.upload_dir, file_name)

        # StorageService oqim davomida ham chegarani ushlab turadi va oshsa o'chiradi.
        saved = await self.storage.save(file, file_path)
        if not saved:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fayl saqlanmadi",
            )

        return {
            "file_name": file.filename,
            "file_url": f"/{settings.CHAT_UPLOAD_DIR}/{file_name}",
            "size": os.path.getsize(file_path),
        }


def get_chat_attachment_service() -> ChatAttachmentService:
    storage = StorageService(
        upload_dir=settings.CHAT_UPLOAD_DIR,
        max_size_bytes=settings.MAX_CHAT_FILE_SIZE,
    )
    return ChatAttachmentService(storage)

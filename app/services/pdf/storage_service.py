import os
import aiofiles
from fastapi import UploadFile, HTTPException


class StorageService:
    def __init__(self, upload_dir: str, max_size_bytes: int):
        self.upload_dir = upload_dir
        self.max_size_bytes = max_size_bytes
        os.makedirs(self.upload_dir, exist_ok=True)

    async def save_pdf(self, file: UploadFile, dest_path: str) -> None:
        total_size = 0

        try:
            async with aiofiles.open(dest_path, "wb") as out:
                while chunk := await file.read(1024 * 1024):  # 1MB
                    total_size += len(chunk)
                    if total_size > self.max_size_bytes:
                        raise HTTPException(400, "PDF hajmi maksimal 20MB bo‘lishi kerak")
                    await out.write(chunk)
        finally:
            await file.close()
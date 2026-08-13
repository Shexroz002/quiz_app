import os
import aiofiles

from fastapi import UploadFile


class StorageService:
    def __init__(self, upload_dir: str, max_size_bytes: int):
        self.upload_dir = upload_dir
        self.max_size_bytes = max_size_bytes
        os.makedirs(self.upload_dir, exist_ok=True)

    async def save_pdf(self, file: UploadFile, dest_path: str) -> bool:
        total_size = 0

        try:
            async with aiofiles.open(dest_path, "wb") as out:
                while chunk := await file.read(1024 * 1024):  # 1 MB
                    total_size += len(chunk)

                    if total_size > self.max_size_bytes:
                        return False

                    await out.write(chunk)

            return os.path.isfile(dest_path)

        except Exception:
            return False

        finally:
            await file.close()

            if total_size > self.max_size_bytes:
                if os.path.exists(dest_path):
                    os.remove(dest_path)

from io import BytesIO


class TelegramUploadFile:
    def __init__(self, *, data: bytes, filename: str, content_type: str | None):
        self._buffer = BytesIO(data)
        self.filename = filename
        self.content_type = content_type or "application/octet-stream"

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    async def close(self) -> None:
        self._buffer.close()

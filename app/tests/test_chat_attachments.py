from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from app.services.chat.attachment_service import ALLOWED_CONTENT_TYPES, ChatAttachmentService

MAX_SIZE = 50 * 1024 * 1024


def build_service(save_result: bool = True) -> ChatAttachmentService:
    storage = MagicMock()
    storage.upload_dir = "media/uploads"
    storage.max_size_bytes = MAX_SIZE
    storage.save = AsyncMock(return_value=save_result)
    return ChatAttachmentService(storage)


def upload(filename="rasm.png", content_type="image/png", size=1024):
    return SimpleNamespace(filename=filename, content_type=content_type, size=size)


class AttachmentValidationTests(IsolatedAsyncioTestCase):
    async def test_rejects_disallowed_content_types(self):
        service = build_service()

        for content_type in ("image/svg+xml", "text/html", "application/x-sh",
                             "application/octet-stream", None):
            with self.subTest(content_type=content_type):
                with self.assertRaises(HTTPException) as ctx:
                    await service.save_attachment(upload(content_type=content_type))
                self.assertEqual(ctx.exception.status_code, 400)

        service.storage.save.assert_not_awaited()

    async def test_rejects_oversized_file_before_writing(self):
        service = build_service()

        with self.assertRaises(HTTPException) as ctx:
            await service.save_attachment(upload(size=MAX_SIZE + 1))

        self.assertEqual(ctx.exception.status_code, 413)
        service.storage.save.assert_not_awaited()

    async def test_accepts_file_at_size_limit(self):
        service = build_service()

        with patch("app.services.chat.attachment_service.os.path.getsize", return_value=MAX_SIZE):
            await service.save_attachment(upload(size=MAX_SIZE))

        service.storage.save.assert_awaited_once()

    async def test_malicious_filename_cannot_escape_upload_dir(self):
        """Kengaytma allowlist'dan olinadi, fayl nomidan emas."""
        service = build_service()
        evil = upload(filename="../../../etc/passwd.png/../../evil", content_type="image/png")

        with patch("app.services.chat.attachment_service.os.path.getsize", return_value=10):
            result = await service.save_attachment(evil)

        written_path = service.storage.save.await_args.args[1]
        self.assertTrue(written_path.startswith("media/uploads/"))
        self.assertTrue(written_path.endswith(".png"))
        self.assertNotIn("..", written_path)
        # Saqlangan nom - uuid, faqat javobdagi file_name original bo'lib qoladi.
        self.assertNotIn("passwd", written_path)
        self.assertTrue(result["file_url"].startswith("/media/uploads/"))
        self.assertNotIn("..", result["file_url"])

    async def test_extension_comes_from_content_type_not_filename(self):
        service = build_service()
        mismatched = upload(filename="hujjat.exe", content_type="application/pdf")

        with patch("app.services.chat.attachment_service.os.path.getsize", return_value=10):
            await service.save_attachment(mismatched)

        written_path = service.storage.save.await_args.args[1]
        self.assertTrue(written_path.endswith(".pdf"))

    async def test_failed_write_is_reported(self):
        service = build_service(save_result=False)

        with self.assertRaises(HTTPException) as ctx:
            await service.save_attachment(upload())

        self.assertEqual(ctx.exception.status_code, 400)

    async def test_successful_upload_payload(self):
        service = build_service()

        with patch("app.services.chat.attachment_service.os.path.getsize", return_value=2048):
            result = await service.save_attachment(upload(filename="hisobot.pdf",
                                                          content_type="application/pdf"))

        self.assertEqual(result["file_name"], "hisobot.pdf")
        self.assertEqual(result["size"], 2048)
        self.assertTrue(result["file_url"].endswith(".pdf"))

    async def test_unknown_size_still_streams_with_storage_cap(self):
        """Content-Length bo'lmasa StorageService oqim chegarasi ishlaydi."""
        service = build_service()

        with patch("app.services.chat.attachment_service.os.path.getsize", return_value=10):
            await service.save_attachment(upload(size=None))

        service.storage.save.assert_awaited_once()

    def test_allowlist_excludes_executable_and_inline_script_types(self):
        for blocked in ("image/svg+xml", "text/html", "application/javascript",
                        "application/x-msdownload", "application/octet-stream"):
            self.assertNotIn(blocked, ALLOWED_CONTENT_TYPES)

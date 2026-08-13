import os
import json
import asyncio
from typing import Optional

from mistralai.client import Mistral, errors

from app.services.ai.base import (
    AIProvider,
    AIQuizParseRequest,
    ProgressCb,
    AIQuizParseResult,
)

RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


class MistralProvider(AIProvider):
    name = "mistral"

    def __init__(
            self,
            *,
            api_key: str="uBbrWGR9VA4zFhp1RxanNzeS4WXvXTG7",
            model: str = "mistral-ocr-4-0",
            logger,
    ):
        self.client = Mistral(api_key=api_key)
        self.model = model
        self.logger = logger

    def _ensure_data_uri(
            self,
            image_base64: str,
            image_id: str,
    ) -> str:

        if image_base64.startswith("data:image/"):
            return image_base64

        extension = image_id.rsplit(".", 1)[-1].lower()

        mime_types = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif",
        }

        mime_type = mime_types.get(
            extension,
            "image/png",
        )

        return f"data:{mime_type};base64,{image_base64}"

    def _build_image_map(
            self,
            ocr_response,
    ) -> dict[str, str]:

        image_map: dict[str, str] = {}

        pages = getattr(
            ocr_response,
            "pages",
            [],
        ) or []

        for page in pages:

            images = getattr(
                page,
                "images",
                [],
            ) or []

            for image in images:

                image_id = getattr(
                    image,
                    "id",
                    None,
                )

                image_base64 = getattr(
                    image,
                    "image_base64",
                    None,
                )

                if not image_id:
                    continue

                if not image_base64:
                    continue

                image_map[image_id] = self._ensure_data_uri(
                    image_base64,
                    image_id,
                )

        return image_map

    async def _upload_pdf(self, pdf_path: str):


        def upload():
            with open(pdf_path, "rb") as pdf_file:
                return self.client.files.upload(
                    file={
                        "file_name": os.path.basename(pdf_path),
                        "content": pdf_file,
                    },
                    purpose="ocr",
                )

        return await asyncio.to_thread(upload)

    async def _process_ocr(
            self,
            *,
            file_id: str,
            req: AIQuizParseRequest,
    ):
        """
        PDF ni OCR + Document Annotation orqali
        structured JSON formatga o'tkazadi.
        """

        def process():
            return self.client.ocr.process(
                model=self.model,

                document={
                    "type": "file",
                    "file_id": file_id,
                },

                # Rasmlarni base64 bilan olish
                include_image_base64=True,

                # Diagram, equation, table va boshqa blocklar
                include_blocks=True,

                # Kichik rasmlar ham olinishi uchun
                image_min_size=20,

                document_annotation_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "quiz",
                        "schema": req.schema,
                        "strict": True,
                    },
                },

                document_annotation_prompt=req.prompt,
            )

        return await asyncio.wait_for(
            asyncio.to_thread(process),
            timeout=req.timeout_sec,
        )

    async def _delete_file(self, file_id: str):
        """
        Mistral serveridagi temporary PDF ni o'chiradi.
        """

        await asyncio.to_thread(
            self.client.files.delete,
            file_id=file_id,
        )

    def _is_retryable_error(self, exc: Exception) -> bool:
        """
        Faqat vaqtinchalik API xatolarida retry qilamiz.
        """

        if isinstance(exc, asyncio.TimeoutError):
            return True

        status_code = getattr(exc, "status_code", None)

        return status_code in RETRYABLE_STATUS_CODES

    async def parse_quiz_from_pdf(
            self,
            req: AIQuizParseRequest,
            progress: Optional[ProgressCb] = None,
    ) -> AIQuizParseResult:

        pdf_path = req.pdf_path

        uploaded_file_id: str | None = None
        raw_text: str | None = None

        max_retries = 3

        # ---------------------------------------------------------
        # 1. Local file check
        # ---------------------------------------------------------

        if not os.path.exists(pdf_path):
            if progress:
                await progress(
                    100,
                    "",
                    "Kechirasiz, PDF fayl topilmadi!",
                )

            raise FileNotFoundError(
                f"Fayl topilmadi: {pdf_path}"
            )

        try:

            # ---------------------------------------------------------
            # 2. Upload PDF
            # ---------------------------------------------------------

            if progress:
                await progress(
                    15,
                    "PDF Mistral serveriga yuklanmoqda",
                    "",
                )

            uploaded_file = await self._upload_pdf(pdf_path)

            uploaded_file_id = getattr(
                uploaded_file,
                "id",
                None,
            )

            if not uploaded_file_id:
                raise RuntimeError(
                    "Mistral uploaded file ID qaytarmadi"
                )

            self.logger.info(
                "PDF uploaded to Mistral. file_id=%s",
                uploaded_file_id,
            )

            if progress:
                await progress(
                    30,
                    "PDF muvaffaqiyatli yuklandi",
                    "",
                )

            # ---------------------------------------------------------
            # 3. OCR + Structured output
            # ---------------------------------------------------------

            for attempt in range(1, max_retries + 1):

                try:

                    if progress:
                        if attempt == 1:
                            await progress(
                                50,
                                "AI PDF faylni tahlil qilmoqda",
                                "",
                            )
                        else:
                            await progress(
                                min(50 + attempt * 8, 75),
                                (
                                    "AI qayta urinmoqda "
                                    f"({attempt}/{max_retries})"
                                ),
                                "",
                            )

                    self.logger.info(
                        "Mistral OCR processing. "
                        "attempt=%d/%d file_id=%s",
                        attempt,
                        max_retries,
                        uploaded_file_id,
                    )

                    response = await self._process_ocr(
                        file_id=uploaded_file_id,
                        req=req,
                    )

                    # -------------------------------------------------
                    # 4. Document annotation
                    # -------------------------------------------------

                    raw_text = getattr(
                        response,
                        "document_annotation",
                        None,
                    )

                    if not raw_text:
                        raise ValueError(
                            "Mistral document_annotation "
                            "bo'sh javob qaytardi"
                        )

                    if not isinstance(raw_text, str):
                        raw_text = str(raw_text)

                    if not raw_text.strip():
                        raise ValueError(
                            "Mistral bo'sh JSON qaytardi"
                        )

                    # -------------------------------------------------
                    # 5. JSON parsing
                    # -------------------------------------------------
                    # Mistral OCR'dan rasmlarni olish
                    image_map = self._build_image_map(
                        response
                    )

                    self.logger.info(
                        "Mistral OCR completed. questions parsed, images=%d",
                        len(image_map),
                    )

                    data = json.loads(raw_text)

                    if progress:
                        await progress(
                            80,
                            "AI javobi olindi",
                            "",
                        )

                    self.logger.info(
                        "Mistral OCR successfully completed. "
                        "file_id=%s",
                        uploaded_file_id,
                    )

                    # -------------------------------------------------
                    # 6. Result
                    # -------------------------------------------------

                    return AIQuizParseResult(
                        data=data,
                        raw_text=raw_text,
                        provider=self.name,
                        model=self.model,
                        image_map=image_map
                    )

                # -----------------------------------------------------
                # Invalid JSON
                # -----------------------------------------------------

                except json.JSONDecodeError as e:

                    self.logger.warning(
                        "Mistral JSON parsing failed. "
                        "attempt=%d/%d "
                        "line=%s column=%s raw=%r",
                        attempt,
                        max_retries,
                        e.lineno,
                        e.colno,
                        raw_text,
                        exc_info=True,
                    )

                    if attempt == max_retries:

                        if progress:
                            await progress(
                                100,
                                "",
                                (
                                    "AI JSON formatdagi to'g'ri "
                                    "javob qaytarmadi"
                                ),
                            )

                        raise ValueError(
                            f"Mistral JSON parsing error: {e.msg} "
                            f"(line={e.lineno}, "
                            f"column={e.colno})"
                        ) from e

                # -----------------------------------------------------
                # Timeout
                # -----------------------------------------------------

                except asyncio.TimeoutError as e:

                    self.logger.warning(
                        "Mistral OCR timeout. "
                        "attempt=%d/%d",
                        attempt,
                        max_retries,
                        exc_info=True,
                    )

                    if attempt == max_retries:

                        if progress:
                            await progress(
                                100,
                                "",
                                (
                                    "AI PDF faylni qayta ishlashda "
                                    "timeout yuz berdi"
                                ),
                            )

                        raise TimeoutError(
                            "Mistral OCR processing timeout"
                        ) from e

                # -----------------------------------------------------
                # Mistral/API error
                # -----------------------------------------------------

                except Exception as e:

                    status_code = getattr(
                        e,
                        "status_code",
                        None,
                    )

                    self.logger.warning(
                        "Mistral request failed. "
                        "attempt=%d/%d status_code=%s",
                        attempt,
                        max_retries,
                        status_code,
                        exc_info=True,
                    )

                    retryable = self._is_retryable_error(e)

                    if not retryable:
                        if progress:
                            await progress(
                                100,
                                "",
                                (
                                    "Mistral API so'rovida "
                                    "xatolik yuz berdi"
                                ),
                            )

                        raise

                    if attempt == max_retries:
                        if progress:
                            await progress(
                                100,
                                "",
                                (
                                    "AI javob berishda xatolik "
                                    "yuz berdi. Qayta urinib ko'ring."
                                ),
                            )

                        raise

                # -----------------------------------------------------
                # Retry backoff
                # -----------------------------------------------------

                if attempt < max_retries:
                    sleep_seconds = 2 ** (attempt - 1)

                    self.logger.info(
                        "Retrying Mistral after %s seconds",
                        sleep_seconds,
                    )

                    await asyncio.sleep(sleep_seconds)

            raise RuntimeError(
                "Mistral OCR processing muvaffaqiyatsiz tugadi"
            )

        finally:

            # ---------------------------------------------------------
            # 7. Delete uploaded temp file
            # ---------------------------------------------------------

            if uploaded_file_id:
                try:

                    await self._delete_file(
                        uploaded_file_id
                    )

                    self.logger.info(
                        "Mistral temporary file deleted. "
                        "file_id=%s",
                        uploaded_file_id,
                    )

                except Exception as e:

                    self.logger.warning(
                        "Mistral temporary file delete failed. "
                        "file_id=%s error=%s",
                        uploaded_file_id,
                        e,
                        exc_info=True,
                    )

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from google import genai
from google.genai import types
from app.services.ai.base import AIProvider, AIQuizParseRequest, ProgressCb, AIQuizParseResult


class GeminiProvider(AIProvider):
    name = "gemini"

    def __init__(self, *, api_key: str, model: str, logger):
        self.client = genai.Client(api_key=api_key)  # sizdagi Client ga moslang
        self.model = model
        self.logger = logger

    async def _wait_until_ready(self, file_name: str, timeout_sec: int = 120):
        start = asyncio.get_event_loop().time()

        while True:
            file = self.client.files.get(name=file_name)
            state = getattr(file.state, "name", None) or str(file.state)

            self.logger.info("Gemini file state: %s", state)

            if state == "ACTIVE":
                return file
            if state == "FAILED":
                raise RuntimeError("Gemini serverida fayl processing FAILED")

            if (asyncio.get_event_loop().time() - start) > timeout_sec:
                raise TimeoutError("Gemini file processing timeout")

            await asyncio.sleep(2)

    async def parse_quiz_from_pdf(
            self,
            req: AIQuizParseRequest,
            progress: Optional[ProgressCb] = None,
    ) -> AIQuizParseResult:
        pdf_path = req.pdf_path
        uploaded_file_name: str | None = None
        max_retries = 3
        raw_text: str | None = None
        data: dict | list | None = None

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Fayl topilmadi: {pdf_path}")

        try:
            if progress:
                await progress(15, "PDF AI serverga yuklanmoqda","")

            with open(pdf_path, "rb") as f:
                uploaded_file = self.client.files.upload(
                    file=f,
                    config={"mime_type": "application/pdf"},
                )

            uploaded_file_name = getattr(uploaded_file, "name", None)

            if progress:
                await progress(25, "PDF qayta ishlashga yuborildi","")

            uploaded_file = await self._wait_until_ready(
                uploaded_file_name,
                timeout_sec=req.timeout_sec,
            )

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=req.schema,
                temperature=0.1,
            )

            for attempt in range(1, max_retries + 1):
                try:
                    if progress:
                        if attempt == 1:
                            await progress(55, "AI savollar yaratmoqda","")
                        else:
                            await progress(
                                min(55 + attempt * 5, 75),
                                f"Qayta urinilmoqda ({attempt}/{max_retries})",
                            "")

                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=[
                            types.Part.from_text(text=req.prompt),
                            uploaded_file,
                        ],
                        config=config,
                    )

                    raw_text = getattr(response, "text", None)

                    if not raw_text or not raw_text.strip():
                        raise ValueError("AI bo'sh javob qaytardi")

                    data = json.loads(raw_text)

                    if progress:
                        await progress(80, "AI javobi olindi","")

                    return AIQuizParseResult(
                        data=data,
                        raw_text=raw_text,
                        provider=self.name,
                        model=self.model,
                    )

                except json.JSONDecodeError as e:
                    self.logger.warning(
                        "Gemini JSON parsing failed on attempt %d/%d. "
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
                                "AI JSON formatdagi to‘g‘ri javob qaytarmadi",
                            )
                        raise ValueError(
                            f"JSON parsing error: {e.msg} "
                            f"(line={e.lineno}, column={e.colno})\n"
                            f"Raw response: {raw_text}"
                        ) from e

                except Exception as e:
                    self.logger.warning(
                        "Gemini request failed on attempt %d/%d",
                        attempt,
                        max_retries,
                        exc_info=True,
                    )

                    if attempt == max_retries:
                        if progress:
                            await progress(
                                100,
                                "",
                                "AI javob berishda xatolik yuz berdi. Qayta urinib ko‘ring.",
                            )
                        raise

                if attempt < max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))  # 1s, 2s

            raise ValueError("AI javobini qayta ishlash muvaffaqiyatsiz tugadi")

        finally:
            if uploaded_file_name:
                try:
                    self.client.files.delete(name=uploaded_file_name)
                except Exception as e:
                    self.logger.warning(
                        "Gemini temp file delete failed for %s %s",
                        uploaded_file_name,
                        e,
                        exc_info=True,
                    )

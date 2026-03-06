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
        uploaded_file = None

        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Fayl topilmadi: {pdf_path}")

        try:
            if progress:
                await progress(15, "PDF AI serverga yuklanmoqda")

            with open(pdf_path, "rb") as f:
                uploaded_file = self.client.files.upload(
                    file=f,
                    config={"mime_type": "application/pdf"},
                )

            if progress:
                await progress(25, "PDF qayta ishlashga yuborildi")

            uploaded_file = await self._wait_until_ready(uploaded_file.name, timeout_sec=req.timeout_sec)

            if progress:
                await progress(55, "AI savollar yaratmoqda")
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=req.schema,
            )
            response = self.client.models.generate_content(
                model=self.model,
                contents=[req.prompt, uploaded_file],
                config=config
            )

            raw_text = getattr(response, "text", None) or ""
            # Agar response.text JSON bo'lsa:
            try:
                data = json.loads(raw_text)
                print("✅ JSON muvaffaqiyatli ajratildi")
            except Exception as e:
                raise ValueError(f"JSON parsing error: {e}\nRaw response: {response.text}")

            if progress:
                await progress(80, "AI javobi olindi")

            return AIQuizParseResult(
                data=data,
                raw_text=raw_text,
                provider=self.name,
                model=self.model,
            )

        finally:
            # temp file delete
            if uploaded_file:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                except Exception as e:
                    self.logger.warning(f"Gemini temp file delete failed for {e}", exc_info=True)

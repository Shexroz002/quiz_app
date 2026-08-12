from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from google import genai
from google.genai import types
from google.genai.errors import ServerError

from app.services.ai.base import AIProvider, AIQuizParseRequest, ProgressCb, AIQuizParseResult

RETRYABLE_STATUS_CODES = {500, 503}

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
            if progress:
                await progress(100, "", "Kechirasiz qandaydir xatolik yuz berdi!")
            raise FileNotFoundError(f"Fayl topilmadi: {pdf_path}")

        try:
            if progress:
                await progress(15, "PDF AI serverga yuklanmoqda", "")

            with open(pdf_path, "rb") as f:
                uploaded_file = self.client.files.upload(
                    file=f,
                    config={"mime_type": "application/pdf"},
                )

            uploaded_file_name = getattr(uploaded_file, "name", None)

            if progress:
                await progress(25, "PDF qayta ishlashga yuborildi", "")

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
                            await progress(55, "AI savollar yaratmoqda", "")
                        else:
                            await progress(
                                min(55 + attempt * 5, 75),
                                f"Qayta urinilmoqda ({attempt}/{max_retries})",
                                "")
                    model_name  = self.model if attempt!=max_retries else "gemini-2.5-flash-lite"
                    response = self.client.models.generate_content(
                        model=model_name,
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
                        await progress(80, "AI javobi olindi", "")

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

    async def generate_quiz_from_description(
        self,
        req: AIQuizParseRequest,
        progress: Optional[ProgressCb] = None,
        timeout_sec: int = 120,
    ) -> AIQuizParseResult:
        max_retries = 3
        last_error: Exception | None = None

        if progress:
            await progress(50, "Sizing so'rovingiz AIga jo'natilmoqda", "")

        for attempt in range(1, max_retries + 1):
            try:
                if progress:
                    await progress(
                        65,
                        f"AI savollar yaratmoqda... ({attempt}/{max_retries})",
                        ""
                    )

                # sync generate_content ni timeout bilan thread ichida ishlatamiz
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_content,
                        model="gemini-2.5-flash-lite",
                        contents=[
                            types.Part.from_text(text=req.prompt)
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=req.schema,
                            temperature=0.1,
                        ),
                    ),
                    timeout=timeout_sec,
                )

                raw_text = getattr(response, "text", None)
                if not raw_text:
                    raise ValueError("AI bo'sh javob qaytardi.")

                if progress:
                    await progress(75, "AIdan testlar olindi.", "")

                data = json.loads(raw_text)

                if progress:
                    await progress(80, "AI javobi olindi", "")

                return AIQuizParseResult(
                    data=data,
                    raw_text=raw_text,
                    provider=self.name,
                    model=self.model,
                )

            except ServerError as e:
                last_error = e
                status_code = getattr(e, "status_code", None)

                # faqat retry qilinadigan server xatolari
                if status_code in RETRYABLE_STATUS_CODES and attempt < max_retries:
                    delay = 2 ** (attempt - 1)  # 1, 2, 4 sekund

                    if progress:
                        await progress(
                            70,
                            f"AI serverida vaqtinchalik xato ({status_code}). "
                            f"Qayta urinilmoqda... ({attempt}/{max_retries})",
                            str(e),
                        )

                    await asyncio.sleep(delay)
                    continue

                # oxirgi urinish ham yiqilsa websocketga failed yuboramiz
                if progress:
                    await progress(
                        100,
                        "AI xizmatida xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.",
                        f"ServerError {status_code}: {str(e)}",
                    )

                raise ValueError(
                    f"AI server xatoligi. "
                    f"Status: {status_code}. "
                    f"3 marta urinildi, lekin muvaffaqiyatsiz tugadi. "
                    f"Original error: {str(e)}"
                ) from e

            except asyncio.TimeoutError as e:
                last_error = e

                if attempt < max_retries:
                    delay = 2 ** (attempt - 1)

                    if progress:
                        await progress(
                            70,
                            f"AI javobi juda sekin kelmoqda. Qayta urinilmoqda... ({attempt}/{max_retries})",
                            "Timeout",
                        )

                    await asyncio.sleep(delay)
                    continue

                if progress:
                    await progress(
                        100,
                        "AI javobi kelmadi. Iltimos, keyinroq qayta urinib ko'ring.",
                        "TimeoutError",
                    )

                raise ValueError(
                    "AI javobi timeout bo'ldi. 3 marta urinildi, lekin javob kelmadi."
                ) from e

            except Exception as e:
                # bu yerda JSON parse xatosi yoki boshqa ichki xatolar
                last_error = e

                if progress:
                    await progress(
                        100,
                        "AI javobini qayta ishlashda xatolik yuz berdi.",
                        str(e),
                    )

                raise ValueError(
                    f"AI javobini qayta ishlashda xatolik: {str(e)}"
                ) from e

        # nazariy fallback
        if progress:
            await progress(
                100,
                "AI bilan ishlashda noma'lum xatolik yuz berdi.",
                str(last_error) if last_error else "",
            )

        raise ValueError(
            f"AI generate xatosi: {str(last_error) if last_error else 'Unknown error'}"
        )

    # async def generate_quiz_from_description(
    #         self,
    #         req: AIQuizParseRequest,
    #         progress: Optional[ProgressCb] = None,
    #         timeout_sec: int = 120,
    # ) -> AIQuizParseResult:
    #     if progress:
    #         await progress(50, "Sizing so'rovingiz AIga jo'natilmoqda", "")
    #
    #     if progress:
    #         await progress(65, "AI savollar yaratmoqda...", "")
    #     response = self.client.models.generate_content(
    #         model=self.model,
    #         contents=[
    #             types.Part.from_text(text=req.prompt)
    #         ],
    #         config=types.GenerateContentConfig(
    #             response_mime_type="application/json",
    #             response_schema=req.schema,
    #             temperature=0.1,
    #         ),
    #     )
    #     # check if response status code =500 and retry 2 times with exponential backoff
    #
    #     raw_text = getattr(response, "text", None)
    #     try:
    #         if progress:
    #             await progress(75, "AIdan testlar olindi.", "")
    #         data = json.loads(raw_text)
    #
    #         if progress:
    #             await progress(80, "AI javobi olindi", "")
    #
    #         return AIQuizParseResult(
    #             data=data,
    #             raw_text=raw_text,
    #             provider=self.name,
    #             model=self.model,
    #         )
    #     except Exception as e:
    #         raise ValueError(f"AI javobini qayta ishlashda xatolik: {str(e)}\nRaw response: {response.text}") from e

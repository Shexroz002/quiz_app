import logging

from app.services.ai.base import AIProvider, ProgressCb, AIQuizParseRequest

logger = logging.getLogger(__name__)



from typing import Optional


class AIQuizParser:
    """
    Provider-agnostic parser:
    - provider’dan raw text oladi
    - JSON ni extract/validate qiladi
    """

    def __init__(self, provider: AIProvider, *, prompt: str, schema: dict | None = None):
        self.provider = provider
        self.prompt = prompt
        self.schema = schema

    async def parse_pdf(
            self,
            pdf_path: str,
            *,
            progress: Optional[ProgressCb] = None,
            timeout_sec: int = 120,
    ) -> dict:
        if progress:
            await progress(5, f"AI provider tayyorlanmoqda: {self.provider.name}")

        req = AIQuizParseRequest(
            pdf_path=pdf_path,
            prompt=self.prompt,
            schema=self.schema,
            timeout_sec=timeout_sec,
        )

        res = await self.provider.parse_quiz_from_pdf(req, progress=progress)

        if progress:
            await progress(85, "AI javobi JSON formatga o‘tkazilmoqda")

        if isinstance(res.data, dict) and res.data:
            return res.data

        raw = res.data or {}

        return raw

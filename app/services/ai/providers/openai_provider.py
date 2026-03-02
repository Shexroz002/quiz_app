from __future__ import annotations
from typing import Optional
from app.services.ai.base import AIProvider, AIQuizParseRequest, ProgressCb, AIQuizParseResult
class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self, *, client, model: str):
        self.client = client
        self.model = model

    async def parse_quiz_from_pdf(self, req: AIQuizParseRequest, progress: Optional[ProgressCb] = None) -> AIQuizParseResult:
        if progress:
            await progress(15, "PDF OpenAI ga tayyorlanmoqda")

        # Bu yerda sizning real OpenAI pipeline:
        # - pdf text extract qiling (local)
        # - prompt + extracted text yuboring
        # - JSON qaytarib oling


        raw_text = "{}"
        data = {}  # bu yerga real JSON parsing natijasi keladi

        if progress:
            await progress(80, "AI javobi olindi")

        return AIQuizParseResult(data=data, raw_text=raw_text, provider=self.name, model=self.model)
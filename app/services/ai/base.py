from __future__ import annotations
from typing import Any
from dataclasses import dataclass
from typing import Protocol, Callable, Awaitable, Any, Optional

ProgressCb = Callable[[int, str,  str | None,], Awaitable[None]]

@dataclass
class AIQuizParseRequest:
    pdf_path: str
    prompt: str
    schema: dict | None = None
    timeout_sec: int = 120

@dataclass
class AIQuizParseResult:
    data: dict
    raw_text: str | None = None
    provider: str = "unknown"
    model: str | None = None

class AIProvider(Protocol):
    name: str

    async def parse_quiz_from_pdf(
        self,
        req: AIQuizParseRequest,
        progress: Optional[ProgressCb] = None,
    ) -> AIQuizParseResult:
        ...
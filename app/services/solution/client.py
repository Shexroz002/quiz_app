"""A thin Gemini client for solutions.

Separate from ``GeminiProvider`` so the quiz pipeline keeps its own model,
retries and timeouts; this module only adds, it changes nothing there. It uses
the same API key and SDK.
"""

import json
import logging
import time
from dataclasses import dataclass

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from app.core.config import settings
from app.services.solution.prompts import RECOGNIZE_PROMPT
from app.services.solution.schema import RECOGNIZE_SCHEMA, SOLUTION_SCHEMA

logger = logging.getLogger(__name__)

#: "Busy" answers clear within seconds; worth a few patient tries.
_BUSY = {500, 503}
#: A timeout already cost up to a minute and a half; one more try at most.
_TIMEOUT = {504}
_BUSY_WAITS = (4, 10)
#: Not worth starting a call with less time than this left in the budget.
_MIN_CALL_SEC = 8


def _can_wait(deadline: float | None, seconds: float) -> bool:
    """True when sleeping still leaves room for one more call before the deadline."""
    return deadline is None or deadline - time.monotonic() - seconds >= _MIN_CALL_SEC


class SolutionModelError(Exception):
    """The model could not be reached or returned something unusable."""


class SolutionQuotaError(SolutionModelError):
    """The provider's daily quota for the model is spent.

    Retrying today is pointless, and telling a student to "try again in a bit"
    would be a false promise: on the free tier the quota resets once a day.
    """


@dataclass
class ModelReply:
    """Parsed JSON plus what is worth recording about the call."""

    data: dict
    raw: str
    model: str
    latency_ms: int


class SolutionClient:
    """Calls the solution model with a fixed JSON schema."""

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self._client = genai.Client(api_key=api_key or settings.GEMINI_API_KEY)
        self.model = model or settings.SOLUTION_MODEL

    def solve(
        self,
        prompt: str,
        *,
        images: list[tuple[bytes, str]] = (),
        previous: str | None = None,
        repair: str | None = None,
        temperature: float = 0.2,
        deadline: float | None = None,
    ) -> ModelReply:
        """Solves or explains a problem.

        ``images`` go in front of the prompt so a figure is read with the text.
        ``previous`` and ``repair`` turn the call into a second round: the
        model sees its own reply and the list of rules it broke.
        ``deadline`` is a ``time.monotonic()`` instant shared by the whole task;
        no call, retry or fallback starts or runs past it.
        """
        parts = [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images]
        parts.append(types.Part.from_text(text=prompt))
        contents = [types.Content(role="user", parts=parts)]
        if previous is not None and repair is not None:
            contents.append(types.Content(role="model", parts=[types.Part.from_text(text=previous)]))
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=repair)]))

        # Thinking stays on — this is the call that has to reason — but bounded,
        # so a student is never left waiting minutes for one problem.
        last: SolutionModelError | None = None
        for index, model in enumerate(self._models()):
            if deadline is not None and deadline - time.monotonic() < _MIN_CALL_SEC:
                break
            try:
                return self._call(
                    contents,
                    schema=SOLUTION_SCHEMA,
                    temperature=temperature,
                    thinking=settings.SOLUTION_THINKING_BUDGET,
                    model=model,
                    # The main model gets the patient retries; a fallback one
                    # short try, so a student is not kept waiting through all.
                    waits=_BUSY_WAITS if index == 0 else (3,),
                    deadline=deadline,
                )
            except SolutionQuotaError as exc:
                last = exc
                logger.info("Daily quota spent for %s; trying the next model", model)
            except SolutionModelError as exc:
                # Withdrawn (404), or still busy after its retries (500/503):
                # on 2026-10-05 one model stayed busy for long stretches while
                # another answered. A timeout or a bad request is not retried
                # elsewhere — the first is slow everywhere, the second is ours.
                if not any(code in str(exc) for code in ("404", "500", "503")):
                    raise
                last = exc
                logger.warning("%s could not answer (%s); trying the next model", model, str(exc)[:60])
        raise last or SolutionModelError("no model configured")

    def _models(self) -> list[str]:
        """The main model, then the fallbacks, without repeats."""
        fallbacks = [m.strip() for m in settings.SOLUTION_FALLBACK_MODELS.split(",") if m.strip()]
        return list(dict.fromkeys([self.model, *fallbacks]))

    def recognize(self, image: bytes, mime_type: str) -> ModelReply:
        """Reads the problem off a photo, with the light model.

        No thinking settings at all: a budget of 0 used to switch thinking off,
        but the newer models reject it with 400 INVALID_ARGUMENT — which broke
        every photo once the model alias moved. Their default is fine here.
        The request runs inside an HTTP call the app waits on, so it gets one
        short retry rather than the background task's patient ones.
        """
        contents = [
            types.Part.from_bytes(data=image, mime_type=mime_type),
            RECOGNIZE_PROMPT,
        ]
        return self._call(
            contents,
            schema=RECOGNIZE_SCHEMA,
            temperature=0.0,
            thinking=None,
            model=settings.SOLUTION_RECOGNIZE_MODEL,
            waits=(3,),
            deadline=time.monotonic() + settings.SOLUTION_RECOGNIZE_BUDGET_SEC,
        )

    def _call(
        self,
        contents: list,
        *,
        schema: dict,
        temperature: float,
        thinking: int | None,
        model: str | None = None,
        waits: tuple[int, ...] = _BUSY_WAITS,
        deadline: float | None = None,
    ) -> ModelReply:
        model = model or self.model
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
        )
        if thinking is not None:
            config.thinking_config = types.ThinkingConfig(thinking_budget=thinking)

        last_error: Exception | None = None
        timeouts = 0
        for attempt in range(len(waits) + 1):
            timeout = settings.SOLUTION_TIMEOUT_SEC
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining < _MIN_CALL_SEC:
                    raise SolutionModelError(f"time budget spent: {last_error}")
                timeout = min(timeout, remaining)
            config.http_options = types.HttpOptions(timeout=int(timeout * 1000))
            started = time.monotonic()
            try:
                response = self._client.models.generate_content(
                    model=model, contents=contents, config=config
                )
            except ServerError as exc:
                last_error = exc
                code = getattr(exc, "code", None)
                if code in _BUSY and attempt < len(waits) and _can_wait(deadline, waits[attempt]):
                    time.sleep(waits[attempt])
                    continue
                if code in _TIMEOUT and timeouts == 0:
                    timeouts += 1
                    continue
                raise SolutionModelError(str(exc)) from exc
            except ClientError as exc:
                # 429 is a client error in this SDK, not a server one.
                last_error = exc
                if getattr(exc, "code", None) == 429:
                    if "PerDay" in str(exc):
                        raise SolutionQuotaError(str(exc)) from exc
                    if attempt < len(waits) and _can_wait(deadline, waits[attempt]):
                        time.sleep(waits[attempt])  # a per-minute limit passes quickly
                        continue
                # 400/403/404 mean the request itself is wrong for this model;
                # loud in the log, because no retry will ever fix it.
                logger.error("Solution model rejected the request (%s): %s", model, str(exc)[:300])
                raise SolutionModelError(str(exc)) from exc
            except Exception as exc:  # network, timeout
                raise SolutionModelError(str(exc)) from exc

            latency = int((time.monotonic() - started) * 1000)
            text = (response.text or "").strip()
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning("Solution model returned non-JSON (%s chars)", len(text))
                continue
            if not isinstance(data, dict):
                last_error = ValueError("top level is not an object")
                continue
            # The concrete model behind an alias, so a quality change can be
            # traced to the day the alias moved.
            served_by = getattr(response, "model_version", None) or model
            return ModelReply(data=data, raw=text, model=served_by, latency_ms=latency)

        raise SolutionModelError(f"no usable reply: {last_error}")

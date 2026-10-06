"""Turns a problem into a checked solution.

Plain functions with the model client passed in, so the flow can be tested
without the network. The Celery tasks are the only callers.
"""

import logging
import mimetypes
import os
import time
from dataclasses import dataclass

from app.core.config import settings

from app.services.solution.client import ModelReply, SolutionClient, SolutionModelError, SolutionQuotaError
from app.services.solution.prompts import explain_bank_prompt, repair_prompt, solve_free_prompt
from app.services.solution.validator import Verdict, normalize, validate


def model_failure(exc: SolutionModelError) -> str:
    """The internal error line for a model that could not answer.

    The prefix is what the service reads to tell the student the truth: "busy,
    try again" and "today's quota is spent, try tomorrow" are different promises.
    """
    prefix = "model quota" if isinstance(exc, SolutionQuotaError) else "model unavailable"
    return f"{prefix}: {exc}"

logger = logging.getLogger(__name__)

#: Independent solving rounds for a bank question before it is rejected.
BANK_ROUNDS = 2
_MEDIA_ROOT = os.path.realpath("media")


@dataclass
class Outcome:
    """What a generation produced, ready to be written to a row."""

    ok: bool
    payload: dict | None
    error: str | None
    model: str | None
    latency_ms: int
    matches_key: bool = False
    rounds: int = 0


def question_images(paths: list[str]) -> list[tuple[bytes, str]]:
    """Reads a question's figures from disk; anything outside media/ is skipped."""
    images: list[tuple[bytes, str]] = []
    for path in paths:
        real = os.path.realpath(path.lstrip("/"))
        if not real.startswith(_MEDIA_ROOT + os.sep) or not os.path.isfile(real):
            continue
        mime = mimetypes.guess_type(real)[0] or "image/jpeg"
        with open(real, "rb") as fh:
            images.append((fh.read(), mime))
    return images


def _ask(
    client: SolutionClient,
    prompt: str,
    *,
    images: list[tuple[bytes, str]],
    labels: list[str] | None,
    temperature: float,
    deadline: float,
) -> tuple[dict | None, Verdict, ModelReply]:
    """One answer, plus one repair round if the validator objects."""
    reply = client.solve(prompt, images=images, temperature=temperature, deadline=deadline)
    data = normalize(reply.data)
    verdict = validate(data, option_labels=labels)
    if verdict.ok:
        return data, verdict, reply

    if deadline - time.monotonic() < 10:
        # No time left to repair: keep the first reply if it can be shown.
        return (data if verdict.usable else None), verdict, reply
    repaired = client.solve(
        prompt,
        images=images,
        previous=reply.raw,
        repair=repair_prompt(verdict.all()),
        temperature=temperature,
        deadline=deadline,
    )
    data2 = normalize(repaired.data)
    verdict2 = validate(data2, option_labels=labels)
    total_ms = reply.latency_ms + repaired.latency_ms
    repaired.latency_ms = total_ms

    # Prefer the repair when it can be shown and is no worse; otherwise keep the
    # first reply if only reading rules were broken.
    if verdict2.usable and len(verdict2.all()) <= len(verdict.all()):
        return data2, verdict2, repaired
    if verdict.usable:
        reply.latency_ms = total_ms
        return data, verdict, reply
    return None, verdict2, repaired


def explain_bank_question(
    client: SolutionClient,
    *,
    subject: str,
    question: str,
    table: str | None,
    options: list[tuple[str, str, bool]],
    image_paths: list[str],
) -> Outcome:
    """Solves a bank question blind and keeps it only if it lands on the key.

    The model is not told the correct option. If it were, it would simply agree,
    and the check below would prove nothing. Solved independently, reaching the
    keyed option is real evidence that both the solution and the key are right.
    """
    keyed = [label for label, _, correct in options if correct]
    if len(keyed) != 1:
        return Outcome(False, None, f"question has {len(keyed)} correct options", None, 0)
    key = keyed[0]
    labels = [label for label, _, _ in options]
    prompt = explain_bank_prompt(
        subject=subject,
        question=question,
        table=table,
        options=[(label, text) for label, text, _ in options],
    )
    images = question_images(image_paths)

    latency = 0
    model = None
    seen: list[str] = []
    picks: list[str | None] = []
    deadline = time.monotonic() + settings.SOLUTION_TASK_BUDGET_SEC
    for round_no in range(1, BANK_ROUNDS + 1):
        try:
            data, verdict, reply = _ask(
                client,
                prompt,
                images=images,
                labels=labels,
                # A second round at a higher temperature is a genuinely
                # independent try, not the same answer twice.
                temperature=0.2 if round_no == 1 else 0.7,
                deadline=deadline,
            )
        except SolutionModelError as exc:
            return Outcome(False, None, model_failure(exc), model, latency, rounds=round_no)

        latency += reply.latency_ms
        model = reply.model
        if data is None:
            seen.append(f"round {round_no}: unusable ({'; '.join(verdict.hard[:2])})")
            continue
        if data.get("problem_ok") is False:
            seen.append(f"round {round_no}: model says unsolvable ({data.get('problem_note')})")
            continue
        chosen = data.get("chosen_option")
        picks.append(chosen)
        if chosen == key:
            if verdict.soft:
                logger.info("Explanation kept with reading issues: %s", verdict.soft)
            return Outcome(True, data, None, model, latency, matches_key=True, rounds=round_no)
        seen.append(f"round {round_no}: model chose {chosen}, key is {key}")

    # Every round solved it and every round landed on the same other option:
    # that is two independent solutions against one key. In the data seen so
    # far this has meant a wrong key far more often than a wrong solution, so
    # it is kept as a dispute for review instead of a silent rejection.
    disputed = None
    if len(picks) == BANK_ROUNDS and picks[0] is not None and len(set(picks)) == 1:
        disputed = {"disputed": {"model_option": picks[0], "key": key}}
    return Outcome(False, disputed, "; ".join(seen), model, latency, rounds=BANK_ROUNDS)


def solve_problem(client: SolutionClient, *, subject: str, problem: str) -> Outcome:
    """Solves a problem a student brought in. There is no key to check against."""
    try:
        data, verdict, reply = _ask(
            client,
            solve_free_prompt(subject=subject, problem=problem),
            images=[],
            labels=None,
            temperature=0.2,
            deadline=time.monotonic() + settings.SOLUTION_TASK_BUDGET_SEC,
        )
    except SolutionModelError as exc:
        return Outcome(False, None, model_failure(exc), None, 0, rounds=1)

    if data is None:
        return Outcome(False, None, "; ".join(verdict.hard[:3]), reply.model, reply.latency_ms, rounds=1)
    if data.get("problem_ok") is False:
        # The model's own note is written for the student, so it travels in the
        # payload; ``error`` stays an internal log line.
        note = (data.get("problem_note") or "").strip() or "Masalada ma'lumot yetishmayapti."
        return Outcome(
            False, {"note": note}, f"unsolvable: {note}", reply.model, reply.latency_ms, rounds=1
        )
    data.pop("hints", None)
    data.pop("chosen_option", None)
    return Outcome(True, data, None, reply.model, reply.latency_ms, rounds=1)

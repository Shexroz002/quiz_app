"""Background generation of solutions.

Both tasks read what they need in one short session, call the model with no
connection held (a solution can take a minute), then write the result in a
second session. Neither task retries on its own: a failed row is retried when a
student next asks for it, so a provider outage never turns into a retry storm.
"""

import asyncio
import logging

from app.core.celery_app import celery_app
from app.core.database.base import CeleryAsyncSessionLocal
from app.models.solution import ExplanationStatus, SolveStatus
from app.repositories.solution.solution_repo import SolutionRepository
from app.services.solution.client import SolutionClient
from app.services.solution.generator import explain_bank_question, solve_problem

logger = logging.getLogger(__name__)


async def _explain(question_id: int) -> str:
    async with CeleryAsyncSessionLocal() as db:
        repo = SolutionRepository(db)
        row = await repo.explanation_for(question_id)
        if row is None or row.status == ExplanationStatus.ready:
            return "skipped"
        question = await repo.question_with_options(question_id)
        if question is None:
            row.status = ExplanationStatus.rejected
            row.error = "question no longer exists"
            await db.commit()
            return "rejected"
        inputs = {
            "subject": (question.subject or "").strip(),
            "question": question.question_text or "",
            "table": question.table_markdown,
            "options": sorted(
                ((o.label or "").strip().upper(), o.text or "", bool(o.is_correct))
                for o in question.options
            ),
            "image_paths": [image.image_url for image in question.images or []],
        }

    outcome = await asyncio.to_thread(explain_bank_question, SolutionClient(), **inputs)

    async with CeleryAsyncSessionLocal() as db:
        repo = SolutionRepository(db)
        row = await repo.explanation_for(question_id)
        if row is None:
            return "gone"
        row.attempts += outcome.rounds
        row.model = outcome.model
        if outcome.ok:
            row.status = ExplanationStatus.ready
            row.payload = outcome.payload
            row.matches_key = outcome.matches_key
            row.error = None
        elif (outcome.error or "").startswith(("model unavailable", "model quota")):
            row.status = ExplanationStatus.failed
            row.error = outcome.error
        else:
            row.status = ExplanationStatus.rejected
            # Kept for review: which option two independent solves agreed on.
            row.payload = outcome.payload
            row.error = outcome.error
        await db.commit()
        logger.info(
            "Explanation for question %s: %s (%s rounds, %s ms)",
            question_id, row.status.value, outcome.rounds, outcome.latency_ms,
        )
        return row.status.value


async def _solve(request_id: int) -> str:
    async with CeleryAsyncSessionLocal() as db:
        repo = SolutionRepository(db)
        row = await repo.request(request_id)
        if row is None or row.status != SolveStatus.pending:
            return "skipped"
        subject, problem = row.subject, row.input_text

    outcome = await asyncio.to_thread(solve_problem, SolutionClient(), subject=subject, problem=problem)

    async with CeleryAsyncSessionLocal() as db:
        repo = SolutionRepository(db)
        row = await repo.request(request_id)
        if row is None:
            return "gone"
        row.model = outcome.model
        row.latency_ms = outcome.latency_ms
        if outcome.ok:
            row.status = SolveStatus.done
            row.payload = outcome.payload
            row.error = None
        else:
            row.status = SolveStatus.failed
            row.payload = outcome.payload
            row.error = outcome.error
        await db.commit()
        return row.status.value


@celery_app.task(name="solution.explain_question", queue="celery")
def explain_question(question_id: int) -> str:
    """Writes and checks the solution for one bank question."""
    return asyncio.run(_explain(question_id))


@celery_app.task(name="solution.solve_request", queue="celery")
def solve_request(request_id: int) -> str:
    """Solves one problem a student brought in."""
    return asyncio.run(_solve(request_id))

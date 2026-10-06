"""The HTTP side of solutions: access, quota, queueing and shaping replies."""

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database.base import get_db
from app.models.solution import (
    ExplanationFeedback,
    ExplanationStatus,
    FeedbackVerdict,
    QuestionExplanation,
    SolveRequest,
    SolveStatus,
)
from app.repositories.solution.solution_repo import SolutionRepository
from app.schemas.solution.solution import (
    ExplanationResponse,
    FeedbackCreate,
    FeedbackResponse,
    RecognizeResponse,
    SolutionQuota,
    SolveCreate,
    SolveHistoryItem,
    SolveRequestResponse,
)
from app.services.pdf.storage_service import StorageService
from app.services.solution.client import SolutionClient, SolutionModelError, SolutionQuotaError
from app.utils.datetime import utc_now

#: A pending row older than this is assumed lost (worker restart) and requeued.
STALE_AFTER = timedelta(minutes=4)
#: A failed bank explanation is retried at most this often, so an outage does
#: not turn every page view into a model call.
RETRY_FAILED_AFTER = timedelta(minutes=2)

_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}

_MODEL_DOWN = "Hozir yechib bo‘lmadi. Birozdan keyin qayta urinib ko‘ring."
#: Not "in a bit": on the free tier the provider's quota resets once a day.
_QUOTA = "Bugun masala yechish xizmatining kunlik limiti tugadi. Ertaga qayta urinib ko‘ring."


def _model_message(error: str | None) -> str:
    return _QUOTA if (error or "").startswith("model quota") else _MODEL_DOWN


def _media_url(path: str | None) -> str | None:
    return f"/{path.lstrip('/')}" if path else None


class SolutionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SolutionRepository(db)

    # -- quota ----------------------------------------------------------------

    def _day_start(self, now: datetime) -> datetime:
        """Midnight in the app's time zone, as UTC: "today" is the student's day."""
        local = now.astimezone(ZoneInfo(settings.APP_TIME_ZONE))
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    async def quota(self, user_id: int) -> SolutionQuota:
        start = self._day_start(utc_now())
        used = await self.repo.requests_since(user_id, start)
        limit = settings.SOLUTION_DAILY_LIMIT
        return SolutionQuota(limit=limit, used=used, left=max(0, limit - used), resets_at=start + timedelta(days=1))

    async def _require_quota(self, user_id: int) -> None:
        if (await self.quota(user_id)).left <= 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Bugungi limit tugadi. Ertaga yana masala yechish mumkin.",
            )

    # -- bank questions -------------------------------------------------------

    async def explanation(self, user_id: int, question_id: int, chosen: str | None) -> ExplanationResponse:
        reply = await self._explanation(user_id, question_id, chosen)
        if reply.question_text is None:
            question = await self.repo.question_with_options(question_id)
            reply.question_text = question.question_text if question else None
        return reply

    async def _explanation(self, user_id: int, question_id: int, chosen: str | None) -> ExplanationResponse:
        if not await self.repo.user_may_see(user_id, question_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Yechim testni tugatgandan keyin ochiladi.",
            )
        question = await self.repo.question_with_options(question_id)
        if question is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Savol topilmadi.")
        keyed = [o for o in question.options if o.is_correct]
        if len(keyed) != 1:
            # Without exactly one key there is nothing to check a solution against.
            return ExplanationResponse(
                status="unavailable",
                message="Bu savolning javobi tizimda aniq belgilanmagan, shuning uchun yechim tayyorlanmaydi.",
            )
        correct = (keyed[0].label or "").strip().upper()

        row, created = await self.repo.ensure_explanation(question_id)
        now = utc_now()
        if row.status == ExplanationStatus.ready and row.payload:
            await self.db.commit()
            return self._ready(row, correct, chosen)
        if row.status == ExplanationStatus.rejected:
            await self.db.commit()
            dispute = (row.payload or {}).get("disputed")
            if dispute:
                return self._disputed(dispute, correct, chosen)
            return ExplanationResponse(
                status="unavailable",
                message="Bu savol uchun ishonchli yechim topilmadi. Uni o‘qituvchingizdan so‘rang.",
            )

        requeue = (
            created
            or (row.status == ExplanationStatus.pending and row.updated_at < now - STALE_AFTER)
            or (row.status == ExplanationStatus.failed and row.updated_at < now - RETRY_FAILED_AFTER)
        )
        if requeue:
            row.status = ExplanationStatus.pending
            row.updated_at = now
        await self.db.commit()
        if requeue:
            from app.services.solution.tasks import explain_question

            explain_question.delay(question_id)
        if row.status == ExplanationStatus.failed:
            return ExplanationResponse(status="unavailable", message=_model_message(row.error))
        return ExplanationResponse(status="pending")

    @staticmethod
    def _disputed(dispute: dict, correct: str, chosen: str | None) -> ExplanationResponse:
        """The key and two independent solutions disagree. Say so plainly."""
        model_option = (dispute.get("model_option") or "").upper()
        mine = (chosen or "").strip().upper()
        right = bool(mine) and mine == model_option
        message = (
            f"Bu savolni ikki marta mustaqil yechganda {model_option} javob chiqdi, "
            f"tizimda esa {correct} belgilangan. Javob kaliti xato bo‘lishi mumkin — "
            "savol tekshirish ro‘yxatiga qo‘shildi."
        )
        if right:
            message = f"Sizning javobingiz ({mine}) to‘g‘ri bo‘lishi mumkin. " + message
        return ExplanationResponse(
            status="disputed",
            correct_option=correct,
            model_option=model_option,
            student_may_be_right=right,
            message=message,
        )

    def _ready(self, row: QuestionExplanation, correct: str, chosen: str | None) -> ExplanationResponse:
        payload = dict(row.payload or {})
        hints = payload.pop("hints", None) or []
        payload.pop("chosen_option", None)
        pick = (chosen or "").strip().upper()
        hint = None
        if pick and pick != correct:
            hint = next((h for h in hints if (h.get("option") or "").upper() == pick), None)
        return ExplanationResponse(
            status="ready",
            explanation_id=row.id,
            correct_option=correct,
            solution=payload,
            hint=hint,
        )

    # -- students' own problems -----------------------------------------------

    async def recognize(self, user_id: int, upload: UploadFile) -> RecognizeResponse:
        await self._require_quota(user_id)
        extension = _IMAGE_TYPES.get(upload.content_type or "")
        if extension is None:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Faqat rasm yuborish mumkin (JPG, PNG, WEBP).",
            )
        storage = StorageService(
            upload_dir=settings.SOLUTION_UPLOAD_DIR,
            max_size_bytes=settings.SOLUTION_MAX_IMAGE_BYTES,
        )
        # The extension always comes from the table above, never from the
        # uploaded name, so a crafted file name cannot leave the directory.
        path = os.path.join(settings.SOLUTION_UPLOAD_DIR, f"{uuid.uuid4()}{extension}")
        if not await storage.save(upload, path):
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Rasm hajmi {settings.SOLUTION_MAX_IMAGE_BYTES // (1024 * 1024)} MB dan oshmasin.",
            )
        with open(path, "rb") as fh:
            image = fh.read()

        try:
            reply = await asyncio.wait_for(
                asyncio.to_thread(SolutionClient().recognize, image, upload.content_type),
                timeout=settings.SOLUTION_TIMEOUT_SEC,
            )
        except SolutionQuotaError:
            os.remove(path)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_QUOTA)
        except (SolutionModelError, asyncio.TimeoutError):
            os.remove(path)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_MODEL_DOWN)

        data = reply.data
        readable = bool(data.get("readable")) and bool((data.get("text") or "").strip())
        subject = data.get("subject") if data.get("subject") in ("matematika", "fizika") else "matematika"
        row = await self.repo.add_request(
            SolveRequest(
                user_id=user_id,
                subject=subject,
                status=SolveStatus.recognized,
                input_text=(data.get("text") or "").strip() if readable else "",
                input_image_path=path,
                model=reply.model,
                latency_ms=reply.latency_ms,
            )
        )
        await self.db.commit()
        return RecognizeResponse(
            request_id=row.id,
            readable=readable,
            text=row.input_text,
            subject=subject,
            multiple=bool(data.get("multiple")),
            image_url=_media_url(path),
            quota=await self.quota(user_id),
        )

    async def submit(self, user_id: int, body: SolveCreate) -> SolveRequestResponse:
        text = body.text.strip()
        if body.request_id is not None:
            row = await self.repo.request(body.request_id)
            if row is None or row.user_id != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="So‘rov topilmadi.")
            if row.status != SolveStatus.recognized:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu masala allaqachon yuborilgan.")
            # The photo was already counted when it was read.
            row.input_text = text
            row.subject = body.subject
            row.status = SolveStatus.pending
        else:
            await self._require_quota(user_id)
            row = await self.repo.add_request(
                SolveRequest(user_id=user_id, subject=body.subject, status=SolveStatus.pending, input_text=text)
            )
        await self.db.commit()

        from app.services.solution.tasks import solve_request

        solve_request.delay(row.id)
        return self._request_out(row)

    async def request(self, user_id: int, request_id: int) -> SolveRequestResponse:
        row = await self.repo.request(request_id)
        if row is None or row.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="So‘rov topilmadi.")
        if row.status == SolveStatus.pending and row.updated_at < utc_now() - STALE_AFTER:
            row.updated_at = utc_now()
            await self.db.commit()
            from app.services.solution.tasks import solve_request

            solve_request.delay(row.id)
        return self._request_out(row)

    async def retry(self, user_id: int, request_id: int) -> SolveRequestResponse:
        """Sends a failed problem again. The same row, so the limit is not spent twice."""
        row = await self.repo.request(request_id)
        if row is None or row.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="So‘rov topilmadi.")
        if row.status != SolveStatus.failed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu masala qayta yuborilmaydi.")
        if (row.payload or {}).get("note"):
            # The model said the problem itself is incomplete; asking again would
            # only repeat that. The student fixes the text and sends a new one.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Masala matnini to‘ldirib, qaytadan yuboring.",
            )
        row.status = SolveStatus.pending
        row.error = None
        row.payload = None
        await self.db.commit()
        from app.services.solution.tasks import solve_request

        solve_request.delay(row.id)
        return self._request_out(row)

    async def history(self, user_id: int) -> list[SolveHistoryItem]:
        rows = await self.repo.history(user_id, limit=20)
        return [
            SolveHistoryItem(
                id=row.id, status=row.status.value, subject=row.subject,
                text=row.input_text[:200], created_at=row.created_at,
            )
            for row in rows
        ]

    def _request_out(self, row: SolveRequest) -> SolveRequestResponse:
        solution = row.payload if row.status == SolveStatus.done else None
        message = None
        note = (row.payload or {}).get("note")
        if row.status == SolveStatus.failed:
            message = note or _model_message(row.error)
        return SolveRequestResponse(
            id=row.id,
            status=row.status.value,
            subject=row.subject,
            text=row.input_text,
            image_url=_media_url(row.input_image_path),
            solution=solution,
            message=message,
            retryable=row.status == SolveStatus.failed and not note,
            created_at=row.created_at,
        )

    # -- feedback ---------------------------------------------------------------

    async def feedback(self, user_id: int, body: FeedbackCreate) -> FeedbackResponse:
        verdict = FeedbackVerdict(body.verdict)
        explanation = None
        if body.explanation_id is not None:
            explanation = await self.repo.explanation(body.explanation_id)
            if explanation is None or not await self.repo.user_may_see(user_id, explanation.question_id):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Yechim topilmadi.")
        else:
            request = await self.repo.request(body.solve_request_id)
            if request is None or request.user_id != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Yechim topilmadi.")

        existing = await self.repo.feedback_for(
            user_id, explanation_id=body.explanation_id, solve_request_id=body.solve_request_id
        )
        if existing is not None:
            if explanation is not None:
                self._count(explanation, existing.verdict, -1)
            existing.verdict = verdict
            existing.comment = body.comment
        else:
            await self.repo.add_feedback(
                ExplanationFeedback(
                    user_id=user_id,
                    explanation_id=body.explanation_id,
                    solve_request_id=body.solve_request_id,
                    verdict=verdict,
                    comment=body.comment,
                )
            )
        if explanation is not None:
            self._count(explanation, verdict, +1)
        await self.db.commit()
        return FeedbackResponse(verdict=verdict.value)

    @staticmethod
    def _count(row: QuestionExplanation, verdict: FeedbackVerdict, delta: int) -> None:
        field = {
            FeedbackVerdict.helpful: "helpful_count",
            FeedbackVerdict.unclear: "unclear_count",
            FeedbackVerdict.wrong: "wrong_count",
        }[verdict]
        setattr(row, field, max(0, getattr(row, field) + delta))


def get_solution_service(db: AsyncSession = Depends(get_db)) -> SolutionService:
    return SolutionService(db)

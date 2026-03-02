from fastapi import WebSocket, WebSocketDisconnect, APIRouter
import json
import redis.asyncio as redis

from app.core.config import settings
from app.core.database.base import AsyncSessionLocal
from app.models.quiz.ai_quiz.pdf_to_quiz import PDFJob
from app.websocket.utils import authenticate_websocket

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
job_ws_router = APIRouter(tags=["PDF Job WebSocket"])

@job_ws_router.websocket("/ws/jobs/{job_id}/")
async def ws_pdf_job_progress(websocket: WebSocket, job_id: str):

    user = await authenticate_websocket(websocket)
    print("Authenticated user:", user.username if user else "None")
    if not user:
        await websocket.close(code=1008)
        return

    async with AsyncSessionLocal() as db:
        job = await db.get(PDFJob, job_id)

        if not job or job.user_id != user.id:
            await websocket.close(code=1008)
            return

    await websocket.accept()

    async with AsyncSessionLocal() as db:
        job = await db.get(PDFJob, job_id)
        await websocket.send_json({
            "type": "snapshot",
            "job_id": str(job.id),
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "quiz_id": job.quiz_id,
            "question_count": job.question_count,
            "error": job.error,
        })

    pubsub = redis_client.pubsub()
    channel = f"pdf_job:{job_id}"
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            data = json.loads(message["data"])
            await websocket.send_json(data)

            if data["status"] in ("completed", "failed"):
                break

    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await websocket.close()
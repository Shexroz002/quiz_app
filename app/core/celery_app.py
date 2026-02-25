from celery import Celery
from app.core.config import settings
from kombu import Queue

celery_app = Celery(
    "quiz_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
)
celery_app.conf.task_queues = (
    Queue("celery"),
    Queue("pdf_ai_queue"),
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

celery_app.autodiscover_tasks(["app.services.pdf.tasks"])

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
    Queue("ai_test_generator"),
    Queue("quiz_session"),

)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.APP_TIME_ZONE,
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    task_track_started=True,
)

celery_app.autodiscover_tasks(["app.services.pdf.tasks"])
celery_app.conf.beat_schedule = {
    "finalize-expired-quiz-sessions-every-60-seconds": {
        "task": "quiz.finalize_expired_sessions",
        "schedule": 60.0,
    },
}

# Import task modules whose filenames do not use Celery's default tasks.py name.
from app.services.quiz.tasks import session_tasks  # noqa: E402, F401

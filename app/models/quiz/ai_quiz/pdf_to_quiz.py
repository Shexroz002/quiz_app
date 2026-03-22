import enum
import uuid
from sqlalchemy import String, Integer, Text, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import BaseModel


class PDFJobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PDFJob(BaseModel):
    __tablename__ = "pdf_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    file_name: Mapped[str] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject: Mapped[int | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    number_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    question_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[PDFJobStatus] = mapped_column(
        Enum(PDFJobStatus),
        default=PDFJobStatus.QUEUED,
        nullable=False
    )

    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    quiz_id: Mapped[int | None] = mapped_column(ForeignKey("quizzes.id"), nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    subject_rel = relationship("Subject")

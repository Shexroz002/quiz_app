from enum import Enum

from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey, Text, Enum as SQLEnum
from app.models.base import BaseModel

class QuizGenerateType(str, Enum):
    AI_GENERATE = "AI_GENERATE"
    PDF = "PDF"
    MANUAL = "MANUAL"
    UNDEFINED = "UNDEFINED"

class Quiz(BaseModel):
    __tablename__ = "quizzes"

    title: Mapped[str] = mapped_column(String(1500))
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quiz_generate_type: Mapped[QuizGenerateType] = mapped_column(
        SQLEnum(QuizGenerateType,name="quiz_generate_type"),
        default=QuizGenerateType.UNDEFINED
    )

    questions = relationship(
        "Question",
        back_populates="quiz",
        cascade="all, delete-orphan"
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    sessions = relationship("QuizSession", back_populates="quiz")

    user = relationship("User", back_populates="quizzes")

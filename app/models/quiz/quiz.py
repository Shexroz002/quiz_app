from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, ForeignKey
from app.models.base import BaseModel


class Quiz(BaseModel):
    __tablename__ = "quizzes"

    title: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)

    questions = relationship(
        "Question",
        back_populates="quiz",
        cascade="all, delete-orphan"
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sessions = relationship("QuizSession", back_populates="quiz")

    user = relationship("User", back_populates="quizzes")

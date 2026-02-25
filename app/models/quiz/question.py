from sqlalchemy import ForeignKey, Text, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class Question(BaseModel):
    __tablename__ = "questions"

    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE")
    )

    question_text: Mapped[str] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(String(100), nullable=True)

    table_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)

    difficulty: Mapped[str | None] = mapped_column(String(50))
    topic: Mapped[str | None] = mapped_column(String(255))

    quiz = relationship("Quiz", back_populates="questions")

    options = relationship(
        "Option",
        back_populates="question",
        cascade="all, delete-orphan"
    )

    images = relationship(
        "QuestionImage",
        back_populates="question",
        cascade="all, delete-orphan"
    )


class QuestionImage(BaseModel):
    __tablename__ = "question_images"

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE")
    )

    image_url: Mapped[str] = mapped_column(String(500))

    question = relationship("Question", back_populates="images")

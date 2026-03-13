from sqlalchemy import ForeignKey, String, Boolean, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import BaseModel


class Option(BaseModel):
    __tablename__ = "options"

    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE")
    )

    label: Mapped[str] = mapped_column(String(5))  # A,B,C,D
    text: Mapped[str] = mapped_column(String(2000))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)

    question = relationship("Question", back_populates="options")

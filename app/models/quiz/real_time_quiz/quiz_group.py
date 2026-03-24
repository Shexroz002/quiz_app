from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class QuizSessionGroup(BaseModel):
    __tablename__ = "quiz_session_groups"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    group_id: Mapped[int] = mapped_column(
        ForeignKey("student_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("session_id", "group_id", name="uq_session_group"),
    )

    session: Mapped["QuizSession"] = relationship(
        "QuizSession",
        back_populates="session_groups",
    )

    group: Mapped["StudentGroup"] = relationship(
        "StudentGroup",
        back_populates="group_sessions",
    )
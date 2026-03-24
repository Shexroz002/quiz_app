import datetime
import enum
from sqlalchemy import (
    String,
    Text,
    ForeignKey,
    Enum as SqlEnum,
    UniqueConstraint,
    Index, Boolean, DateTime,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.science.school_subject import Subject
from app.models.base import BaseModel
from app.models.account.user import User


class GroupColor(str, enum.Enum):
    PURPLE = "purple"
    BLUE = "blue"
    VIOLET = "violet"
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    PINK = "pink"
    TEAL = "teal"
    ORANGE = "orange"
    CYAN = "cyan"


class GroupStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class StudentGroup(BaseModel):
    __tablename__ = "student_groups"

    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    color: Mapped[GroupColor] = mapped_column(
        SqlEnum(GroupColor, name="group_color"),
        nullable=False,
        default=GroupColor.TEAL,
    )

    cover_image: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_public: Mapped[bool | None] = mapped_column(Boolean, nullable=False, default=False)
    invite_code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    last_activity_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    status: Mapped[GroupStatus] = mapped_column(
        SqlEnum(GroupStatus, name="group_status"),
        nullable=False,
        default=GroupStatus.ACTIVE,
    )

    teacher: Mapped["User"] = relationship("User", back_populates="created_groups")
    subject: Mapped["Subject | None"] = relationship("Subject")
    members: Mapped[list["StudentGroupMember"]] = relationship(
        "StudentGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )
    group_sessions: Mapped[list["QuizSessionGroup"]] = relationship(
        "QuizSessionGroup",
        back_populates="group",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("teacher_id", "name", name="uq_teacher_group_name"),
        Index("ix_student_groups_teacher_status", "teacher_id", "status"),
    )


class StudentGroupMember(BaseModel):
    __tablename__ = "student_group_members"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("student_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    student_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    added_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    group: Mapped["StudentGroup"] = relationship(
        "StudentGroup",
        back_populates="members",
    )

    student: Mapped["User"] = relationship(
        "User",
        foreign_keys=[student_id],
        back_populates="student_group_links",
    )

    added_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[added_by],
    )

    __table_args__ = (
        UniqueConstraint("group_id", "student_id", name="uq_group_student"),
    )

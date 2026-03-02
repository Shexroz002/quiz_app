import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import Enum
from app.models.base import BaseModel


class UserType(enum.Enum):
    student = "student"
    schoolboy = "schoolboy"
    teacher = "teacher"


class User(BaseModel):
    __tablename__ = "users"

    username = Column(String(50), unique=True, nullable=False, index=True)
    phone_number = Column(String(20), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)  # store hash, not raw password

    # Profile Info
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    profile_image = Column(String(255), nullable=True)  # URL or file path
    gender = Column(String(20), nullable=True)  # male, female, other
    date_of_birth = Column(DateTime, nullable=True)

    # Account Management
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # after email/phone verification
    is_superuser = Column(Boolean, default=False)  # admin user

    # User role
    role: Mapped[UserType] = mapped_column(Enum(UserType,name="usertype"), nullable=True, default=UserType.schoolboy)

    # Login
    last_login = Column(DateTime, nullable=True)

    # Reletionship
    quiz_participation = relationship("SessionParticipant", back_populates="user")
    quizzes = relationship("Quiz", back_populates="user")
    subjects = relationship("UserSubject", back_populates="user")
    contacts = relationship("Contact", back_populates="friend", foreign_keys="Contact.friend_id")
    contact_of = relationship("Contact", back_populates="friend", foreign_keys="Contact.user_id")

    def __str__(self):
        return f"<User(username={self.username})>"

    class Config:
        orm_mode = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

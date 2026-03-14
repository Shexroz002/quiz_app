import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SqlEnum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import BaseModel


class UserType(enum.Enum):
    student = "student"
    schoolboy = "schoolboy"
    teacher = "teacher"


class GenderType(enum.Enum):
    male = "male"
    female = "female"


class EducationLevel(str, enum.Enum):
    CLASS_1 = "1-sinf"
    CLASS_2 = "2-sinf"
    CLASS_3 = "3-sinf"
    CLASS_4 = "4-sinf"
    CLASS_5 = "5-sinf"
    CLASS_6 = "6-sinf"
    CLASS_7 = "7-sinf"
    CLASS_8 = "8-sinf"
    CLASS_9 = "9-sinf"
    CLASS_10 = "10-sinf"
    CLASS_11 = "11-sinf"
    UNIVERSITY = "Universitet"


class User(BaseModel):
    __tablename__ = "users"

    username = Column(String(50), unique=True, nullable=False, index=True)
    phone_number = Column(String(20), unique=True, nullable=True)
    email = Column(String(255), nullable=True, unique=True)
    telegram_id = Column(String(25), nullable=True, unique=True)
    password_hash = Column(String(255), nullable=False)
    # Profile Info
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    profile_image = Column(String(255), nullable=True)
    gender: Mapped[GenderType] = mapped_column(SqlEnum(GenderType, name="gender_type"), nullable=True)
    date_of_birth = Column(DateTime, nullable=True)
    bio = Column(String(500), nullable=True)
    school_name = Column(String(255), nullable=True)
    education_level: Mapped[EducationLevel] = mapped_column(
        SqlEnum(
            EducationLevel,
            name="education_level",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=True
    )

    # Account Management
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)  # after email/phone verification
    is_superuser = Column(Boolean, default=False)  # admin user

    # User role
    role: Mapped[UserType] = mapped_column(SqlEnum(UserType, name="usertype"), nullable=True,
                                           default=UserType.schoolboy)

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

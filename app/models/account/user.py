from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


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

    #Login
    last_login = Column(DateTime, nullable=True)
    quiz_participation = relationship("SessionParticipant", back_populates="user")
    quizzes = relationship("Quiz", back_populates="user")

    def __str__(self):
        return f"<User(username={self.username}, email={self.email})>"

    class Config:
        orm_mode = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

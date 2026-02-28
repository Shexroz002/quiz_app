from datetime import datetime

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class UserSubject(BaseModel):
    __tablename__ = "user_subject"

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)

    user = relationship("User", back_populates="subjects")
    subject = relationship("Subject", back_populates="users")

    def __str__(self):
        return f"<UserSubject(user={self.user_id}, subject={self.subject_id})>"

    class Config:
        orm_mode = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

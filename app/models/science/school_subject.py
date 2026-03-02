from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class Subject(BaseModel):
    __tablename__ = "subjects"

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )
    type: Mapped[str] = mapped_column(String(100), nullable=True)
    icon: Mapped[str] = mapped_column(String(25), nullable=True)

    users = relationship("UserSubject", back_populates="subject")

    class Config:
        orm_mode = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

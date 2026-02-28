import enum
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy import Enum
from app.models.base import BaseModel


class Contact(BaseModel):
    __tablename__ = "contacts"

    name:Mapped[str] = mapped_column(String(100), nullable=False)
    friend_id:Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    friend = relationship("User", back_populates="contacts")

    def __str__(self):
        return f"<Contact(name={self.name}, friend_id={self.friend_id})>"


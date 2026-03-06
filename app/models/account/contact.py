from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.models.base import BaseModel


class Contact(BaseModel):
    __tablename__ = "contacts"

    name:Mapped[str] = mapped_column(String(100), nullable=False)
    user_id:Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    friend_id:Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    friend = relationship("User", back_populates="contacts", foreign_keys=[friend_id])
    user = relationship("User", back_populates="contact_of", foreign_keys=[user_id])

    # Optional: You can add a unique constraint to prevent duplicate contacts
    __table_args__ = (
        UniqueConstraint('user_id', 'friend_id', name='uq_user_friend'),
    )


    def __str__(self):
        return f"<Contact(name={self.name}, friend_id={self.friend_id})>"


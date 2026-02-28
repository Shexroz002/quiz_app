# from sqlalchemy import ForeignKey, String,JSON
# from sqlalchemy.orm import Mapped, mapped_column, relationship
# from app.models.base import BaseModel
#
#
#
# class UploadQuizModel(BaseModel):
#     __tablename__ = 'quiz_pdf_uploads'
#
#     file_path: Mapped[str] = mapped_column(String(255), nullable=False)
#     user_id : Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
#
#     user = relationship("User", back_populates="pdf_uploads")
#
#     class Config:
#         orm_mode = True




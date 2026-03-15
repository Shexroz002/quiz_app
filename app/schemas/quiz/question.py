from app.schemas.quiz.options import OptionBase, OptionWithoutCorrect
from pydantic import BaseModel, field_serializer
from typing import Optional, List

BASE_URL = 'http://localhost:8000'
class QuestionImageBase(BaseModel):
    id: int
    image_url: str= None

    @field_serializer("image_url")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"


class QuestionBase(BaseModel):
    id: int= None
    question_text: str = None

class QuestionListSchema(QuestionBase):
    topic: str = None


class QuestionDetail(BaseModel):
    id:int
    subject: Optional[str] = None
    question_text: Optional[str] = None
    table_markdown: Optional[str] = None
    difficulty: Optional[str] = None
    topic: Optional[str] = None
    images: List[QuestionImageBase] = None
    options: list[OptionBase]


class QuestionDetailWithoutCorrect(QuestionDetail):
    options: list[OptionWithoutCorrect]

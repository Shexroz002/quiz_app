from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, field_serializer

from app.schemas.quiz.question import QuestionDetail, QuestionDetailWithoutCorrect, QuestionImageBase, BASE_URL


class QuizSessionCreate(BaseModel):
    quiz_id: int
    duration_minutes: int
    max_participants: int


class JoinSessionRequest(BaseModel):
    session_code: str


class QuizSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    quiz_id: int
    host_id: int
    join_code: str
    status: str
    duration_minutes: int
    questions_count: int
    started_at: datetime | None
    finished_at: datetime | None


class StartSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    participants_count: int
    attempts_created: int


class StartSessionSinglePlayerBaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: int
    quiz_id: int


class StartSessionSinglePlayerResponse(StartSessionSinglePlayerBaseResponse):
    status: str
    questions_count: int
    started_at: datetime | None
    finished_at: datetime | None
    questions: list[QuestionDetailWithoutCorrect]


class OptionSchema(BaseModel):
    id: int
    label: str
    text: str
    is_correct: bool


class QuestionErrorAnalyticSessionResponse(BaseModel):
    id: int
    question_id: int
    difficulty: Optional[str] = None
    question_text: str
    subject: Optional[str] = None
    table_markdown: Optional[str] = None
    images: List[QuestionImageBase]
    topic: Optional[str] = None

    options: List[OptionSchema] = []

    user_select_option: Optional[str] = None
    user_select_option_is_correct: Optional[bool] = None


class SessionLeaderboardRow(BaseModel):
    session_id: int
    user_id: int

    title: str | None = None
    subject: str | None = None

    rank: int
    participant_count: int

    correct_answers: int | None = None
    wrong_answers: int | None = None
    total_questions: int | None = None

    finished_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ParticipantResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int

    first_name: str | None = None
    last_name: str | None = None
    profile_image: str | None = None

    score: int | None = None
    wrong_answers: int | None = None
    total_questions: int | None = None

    spend_time_seconds: Decimal | float | None = None

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"

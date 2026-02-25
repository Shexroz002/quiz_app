from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QuizSessionCreate(BaseModel):
    quiz_id: int
    duration_minutes: int


class JoinSessionRequest(BaseModel):
    session_code: str


class QuizSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quiz_id: int
    host_id: int
    join_code: str
    status: str
    duration_minutes: int
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

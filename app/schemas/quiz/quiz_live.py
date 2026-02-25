from pydantic import BaseModel
from uuid import UUID


class QuizSessionCreate(BaseModel):
    id: UUID
    quiz_id: int
    host_id: int
    join_code: str
    status: str = "waiting"

class SessionParticipantCreate(BaseModel):
    user_id: UUID
    nickname: str
    session_id: UUID

class QuizAttemptCreate(BaseModel):
    session_id: UUID
    participant_id: UUID

class AttemptAnswerCreate(BaseModel):
    attempt_id: UUID
    question_id: UUID
    selected_option: str
    is_correct: bool

class JoinSessionRequest(BaseModel):
    join_code: str
    user_id: UUID
    nickname: str

class StartQuizRequest(BaseModel):
    session_id: UUID

class SubmitAnswerRequest(BaseModel):
    attempt_id: UUID
    question_id: UUID
    selected_option: str
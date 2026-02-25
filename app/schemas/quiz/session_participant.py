from pydantic import BaseModel
from uuid import UUID


class QuizSessionCreate(BaseModel):
    id: UUID
    quiz_id: int
    host_id: int
    join_code: str
    status: str = "waiting"

class SessionParticipantCreate(BaseModel):
    user_id: int
    nickname: str
    session_id: int
    is_host: bool = False

class SessionParticipantList(BaseModel):
    nickname: str
    profile_image: str|None
    is_host: bool
    first_name: str
    last_name: str
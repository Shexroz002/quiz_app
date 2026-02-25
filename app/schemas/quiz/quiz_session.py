from pydantic import BaseModel


class QuizSessionCreate(BaseModel):
    quiz_id: int
    duration_minutes: int

class QuizSessionList(BaseModel):
    id: int
    quiz_id: int
    host_id: int
    join_code: str
    status: str = "waiting"

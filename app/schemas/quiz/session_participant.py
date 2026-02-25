from pydantic import BaseModel


class SessionParticipantCreate(BaseModel):
    user_id: int
    nickname: str
    session_id: int
    is_host: bool = False


class SessionParticipantList(BaseModel):
    participant_id: int
    nickname: str
    profile_image: str | None
    is_host: bool
    first_name: str | None
    last_name: str | None

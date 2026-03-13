from pydantic import BaseModel, field_serializer


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
    participant_status: str | None
    user_id:int

    @field_serializer("profile_image")
    def add_base_url(self, value: str):
        BASE_URL = 'http://localhost:8000'
        if value is None:
            return value
        if value.startswith("http"):
            return value
        return f"{BASE_URL}/{value}"


class SessionDetail(BaseModel):
    id: int

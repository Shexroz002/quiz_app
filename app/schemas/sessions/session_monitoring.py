from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class ParticipantLiveStatus(str, Enum):
    WAITING = "waiting"
    PREPARING = "preparing"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"


class ConnectionStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    RECONNECTING = "reconnecting"


class ParticipantLiveStateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    participant_id: int
    user_id: int

    full_name: str = Field(..., description="O'quvchining to'liq ismi")
    nickname: Optional[str] = Field(default=None, description="Session ichidagi nickname")
    profile_image: Optional[str] = Field(default=None, description="Avatar URL")

    is_host: bool = Field(default=False)

    status: ParticipantLiveStatus = Field(
        default=ParticipantLiveStatus.WAITING,
        description="O'quvchining test jarayonidagi hozirgi holati"
    )
    connection_status: ConnectionStatus = Field(
        default=ConnectionStatus.ONLINE,
        description="O'quvchining ulanish holati"
    )

    current_question: int = Field(default=0, ge=0, description="Hozir qaysi savolda turgani")
    answered_count: int = Field(default=0, ge=0, description="Nechta savolga javob bergani")
    total_questions: int = Field(default=0, ge=0, description="Sessiondagi jami savollar soni")

    progress_percent: float = Field(
        default=0,
        ge=0,
        le=100,
        description="Foiz ko'rinishidagi progress"
    )

    score: float = Field(default=0, ge=0, description="Hozirgi ball")
    correct_count: int = Field(default=0, ge=0, description="To'g'ri javoblar soni")
    wrong_count: int = Field(default=0, ge=0, description="Noto'g'ri javoblar soni")
    question_answer_items : dict[int,bool] = Field(
        default={},
    )

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_answer_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class SessionMonitoringTableResponseSchema(BaseModel):
    session_id: int
    total_participants: int
    online_participants: int
    finished_participants: int
    participants: List[ParticipantLiveStateSchema]




class ParticipantLiveStateRedisSchema(ParticipantLiveStateSchema):
    def to_redis_mapping(self) -> dict[str, str]:
        data = self.model_dump(mode="json")
        return {k: "" if v is None else str(v) for k, v in data.items()}

    @classmethod
    def from_redis_mapping(cls, data: dict) -> "ParticipantLiveStateRedisSchema":
        normalized = {k.decode() if isinstance(k, bytes) else k:
                      v.decode() if isinstance(v, bytes) else v
                      for k, v in data.items()}
        return cls.model_validate(normalized)


class ParticipantMonitoringEventSchema(BaseModel):
    event: str = "participant_monitoring_updated"
    session_id: int
    participant: ParticipantLiveStateSchema

from pydantic import BaseModel, Field, constr


class LiveQuizCardSchema(BaseModel):
    session_id: int=Field(..., description="O'quvchining to'liq ismi")
    title: str = Field(..., description="Mathematics Practice Test")
    subject: str|None = Field(..., description="Matematika")
    class_name: str = Field(default="1-A", description="9-A",)
    participants_count: int = Field(..., description="Qatnashuvchilarni max soni")
    duration_minutes: int = Field(...,  description="Quiz davomiyligi minutlarda")
    started_at: str = Field(..., description="HH:MM formatdagi vaqt")
    join_code: str= Field(..., description="A7K92D")
    session_type:str=Field(..., description="Session turi: individual, group yoki public")
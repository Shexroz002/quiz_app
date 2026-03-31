from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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

    full_name: str
    nickname: Optional[str] = None
    profile_image: Optional[str] = None
    is_host: bool = False

    status: ParticipantLiveStatus = ParticipantLiveStatus.WAITING
    connection_status: ConnectionStatus = ConnectionStatus.ONLINE

    current_question: int = Field(default=0, ge=0)
    answered_count: int = Field(default=0, ge=0)
    total_questions: int = Field(default=0, ge=0)
    progress_percent: float = Field(default=0, ge=0, le=100)
    question_answered_count: int = Field(default=0, ge=0)

    score: float = Field(default=0, ge=0)
    correct_count: int = Field(default=0, ge=0)
    wrong_count: int = Field(default=0, ge=0)

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_answer_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None


class ParticipantMonitoringEventSchema(BaseModel):
    event: str = "participant_monitoring_updated"
    session_id: int
    participant: ParticipantLiveStateSchema


class SessionMonitoringSnapshotSchema(BaseModel):
    event: str = "session_monitoring_snapshot"
    session_id: int
    participants: list[ParticipantLiveStateSchema]
    total_participants: int
    online_participants: int
    finished_participants: int
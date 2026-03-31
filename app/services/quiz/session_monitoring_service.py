from app.schemas.quiz.session_monitoring import SessionMonitoringSnapshotSchema, ConnectionStatus
from app.schemas.sessions.session_monitoring import ParticipantLiveStatus
from app.services.redis_service.session_live import SessionLiveStateService


class SessionMonitoringService:
    def __init__(self, live_state_service: SessionLiveStateService):
        self.live_state_service = live_state_service

    async def build_snapshot(self, session_id: int) -> SessionMonitoringSnapshotSchema:
        participants = await self.live_state_service.list_participants(session_id)

        return SessionMonitoringSnapshotSchema(
            session_id=session_id,
            participants=participants,
            total_participants=len(participants),
            online_participants=sum(
                1 for p in participants if p.connection_status == ConnectionStatus.ONLINE
            ),
            finished_participants=sum(
                1 for p in participants if p.status == ParticipantLiveStatus.FINISHED
            ),
        )
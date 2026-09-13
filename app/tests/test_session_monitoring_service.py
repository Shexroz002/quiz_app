from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from app.schemas.quiz.session_monitoring import (
    ConnectionStatus as SnapshotConnectionStatus,
    ParticipantLiveStatus as SnapshotParticipantLiveStatus,
)
from app.schemas.sessions.session_monitoring import (
    ConnectionStatus,
    ParticipantLiveStateSchema,
    ParticipantLiveStatus,
)
from app.services.quiz.session_monitoring_service import SessionMonitoringService


class SessionMonitoringServiceTests(IsolatedAsyncioTestCase):
    async def test_build_snapshot_accepts_ready_participants(self):
        participant = ParticipantLiveStateSchema(
            participant_id=1,
            user_id=2,
            full_name="Ready Student",
            status=ParticipantLiveStatus.READY,
            connection_status=ConnectionStatus.ONLINE,
        )
        live_state_service = AsyncMock()
        live_state_service.list_participants.return_value = [participant]

        snapshot = await SessionMonitoringService(live_state_service).build_snapshot(3)

        self.assertEqual(snapshot.participants[0].status, SnapshotParticipantLiveStatus.READY)
        self.assertEqual(
            snapshot.participants[0].connection_status,
            SnapshotConnectionStatus.ONLINE,
        )
        self.assertEqual(snapshot.total_participants, 1)
        self.assertEqual(snapshot.online_participants, 1)
        self.assertEqual(snapshot.finished_participants, 0)

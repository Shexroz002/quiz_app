from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from app.models import NotificationActionType, NotificationType
from app.services.notification.notification_service import NotificationService


class NotificationServiceTests(IsolatedAsyncioTestCase):
    async def test_group_invite_uses_canonical_notification_types(self):
        service = NotificationService(AsyncMock())
        service.create_notification = AsyncMock()
        teacher = SimpleNamespace(id=7, first_name="Test", last_name="Teacher")

        await service.send_notification_to_group_by_teacher(
            current_user=teacher,
            session_code="ABC123",
            user_ids=[11],
        )

        notification = service.create_notification.await_args.args[0]
        self.assertEqual(notification.type, NotificationType.TEST_INVITE)
        self.assertEqual(notification.action_type, NotificationActionType.TEST_INVITE)
        self.assertEqual(notification.recipient_id, 11)
        self.assertEqual(notification.sender_id, 7)
        self.assertEqual(notification.payload, {"session_code": "ABC123"})

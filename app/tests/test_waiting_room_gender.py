from datetime import datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.dialects import postgresql

from app.models.account.user import GenderType
from app.models.quiz.real_time_quiz.quiz_session import SessionType
from app.repositories.quiz.session_participant import SessionParticipantRepository
from app.schemas.quiz.session_participant import SessionParticipantList, StudentSessionParticipant
from app.services.quiz.quiz_session import QuizSessionService


def _row(**extra):
    row = {
        "participant_id": 31,
        "first_name": "Madina",
        "last_name": "Karimova",
        "user_id": 5,
        "nickname": "madina",
        "joined_at": datetime(2026, 10, 7, 12, 0),
        "profile_image": None,
        "is_host": False,
        "participant_status": "ready",
    }
    row.update(extra)
    return row


class ParticipantListTests(IsolatedAsyncioTestCase):
    """Kutish xonasi o'quvchini o'g'il yoki qiz qilib chizadi: jinsi ro'yxatda keladi."""

    async def test_the_list_reads_the_users_gender(self):
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(mappings=lambda: MagicMock(all=lambda: [])))
        await SessionParticipantRepository(db).get_participant_list(118, pagination=False)
        stmt = db.execute.await_args.args[0]
        sql = str(stmt.compile(dialect=postgresql.dialect()))
        self.assertIn("users.gender", sql)


class StudentParticipantSchemaTests(TestCase):
    def test_a_known_gender_is_sent_as_its_name(self):
        data = StudentSessionParticipant.model_validate(_row(gender=GenderType.female)).model_dump(mode="json")
        self.assertEqual(data["gender"], "female")

    def test_an_unknown_gender_is_null(self):
        self.assertIsNone(StudentSessionParticipant.model_validate(_row(gender=None)).gender)
        self.assertIsNone(StudentSessionParticipant.model_validate(_row()).gender)

    def test_the_teachers_list_is_unchanged(self):
        data = SessionParticipantList.model_validate(_row(gender=GenderType.male)).model_dump(mode="json")
        self.assertNotIn("gender", data)


class JoinedEventTests(IsolatedAsyncioTestCase):
    async def test_a_newcomer_is_announced_with_their_gender(self):
        service = QuizSessionService(db=MagicMock(commit=AsyncMock()))
        session = SimpleNamespace(id=118, status="waiting", session_type=SessionType.public)
        participant = SimpleNamespace(id=31, is_host=False, joined_at=datetime(2026, 10, 7, 12, 0))
        service.session_repo = MagicMock(get_by_join_code=AsyncMock(return_value=session))
        service.participant_repo = MagicMock(
            get_by_session_user=AsyncMock(return_value=None),
            create=AsyncMock(return_value=participant),
        )
        user = SimpleNamespace(id=5, username="madina", profile_image=None, first_name="Madina",
                               last_name="Karimova", gender=GenderType.female)
        with patch("app.services.quiz.quiz_session.session_ws_manager") as ws:
            ws.broadcast = AsyncMock()
            ws.count = MagicMock(return_value=2)
            try:
                await service.join_quiz_session("MYJLOI", user)
            except Exception:
                pass  # what follows the announcement is not under test
        joined = [c for c in ws.broadcast.await_args_list if c.kwargs.get("event") == "participant_joined"]
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0].kwargs["payload"]["gender"], "female")

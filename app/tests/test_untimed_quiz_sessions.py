from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from fastapi import HTTPException

from app.models.quiz.real_time_quiz.quiz_session import SessionStatus
from app.repositories.quiz.quiz_session_repo import QuizSessionRepository
from app.services.quiz.quiz_session import QuizSessionService


NOW = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def session(**overrides):
    defaults = dict(
        id=7,
        quiz_id=3,
        status=SessionStatus.running,
        duration_minutes=30,
        started_at=None,
        deadline_at=None,
        finished_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class StartSessionTests(IsolatedAsyncioTestCase):
    """A session with no duration gets no deadline."""

    async def test_a_duration_sets_a_deadline(self):
        repo = QuizSessionRepository(AsyncMock())
        quiz_session = session(duration_minutes=30)

        await repo.start_session(quiz_session)

        self.assertEqual(quiz_session.status, SessionStatus.running)
        self.assertEqual(
            quiz_session.deadline_at,
            quiz_session.started_at + timedelta(minutes=30),
        )

    async def test_no_duration_leaves_the_deadline_open(self):
        repo = QuizSessionRepository(AsyncMock())
        quiz_session = session(duration_minutes=None)

        await repo.start_session(quiz_session)

        self.assertIsNone(quiz_session.deadline_at)
        # The expiry sweep only looks at sessions that have a deadline, so an
        # untimed one is never closed behind the student's back.
        self.assertIsNotNone(quiz_session.started_at)


class ResumeInsteadOfRestartTests(IsolatedAsyncioTestCase):
    """Starting a quiz twice returns the session already in progress."""

    def service(self):
        service = QuizSessionService.__new__(QuizSessionService)
        service.db = AsyncMock()
        service.session_repo = AsyncMock()
        service.participant_repo = AsyncMock()
        service.question_repo = AsyncMock()
        return service

    async def test_an_unfinished_untimed_session_is_handed_back(self):
        service = self.service()
        service.session_repo.get_open_single_player_session.return_value = 42
        service.get_single_player_quiz_info = AsyncMock(
            return_value={"session_id": 42, "quiz_id": 3}
        )

        result = await service.start_single_player_quiz(3, SimpleNamespace(id=1), None)

        self.assertEqual(result["session_id"], 42)
        self.assertTrue(result["resumed"])
        service.session_repo.create.assert_not_awaited()

    async def test_without_one_a_new_session_is_created(self):
        service = self.service()
        service.session_repo.get_open_single_player_session.return_value = None
        service.session_repo.create.return_value = session(id=9, duration_minutes=None)
        service._generate_unique_join_code = AsyncMock(return_value="ABC123")
        service.question_repo.list_with_details.return_value = [{"id": 1}]

        result = await service.start_single_player_quiz(3, SimpleNamespace(id=1, username="a"), None)

        self.assertEqual(result["session_id"], 9)
        self.assertFalse(result["resumed"])
        self.assertIsNone(result["duration_minutes"])
        service.session_repo.create.assert_awaited_once()


class OnlyUntimedSessionsReopenTests(IsolatedAsyncioTestCase):
    """Limit qo'yilgan sessiyaga qaytib bo'lmaydi."""

    async def test_the_query_asks_only_for_sessions_without_a_deadline(self):
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: None))
        repo = QuizSessionRepository(db)

        await repo.get_open_single_player_session(user_id=1, quiz_id=3)

        sql = str(db.execute.await_args.args[0])
        # Vaqt limitli sessiya "ochiq" deb hisoblanmasligi kerak: uni davom
        # ettirish ketilgan paytda ham yurgan soatni qaytarib berish bo'lardi.
        self.assertIn("deadline_at IS NULL", sql)
        self.assertNotIn("deadline_at >", sql)
        self.assertIn("status", sql)


class FinishTests(IsolatedAsyncioTestCase):
    """Finishing closes the session and cannot be replayed."""

    def service(self, attempt):
        service = QuizSessionService.__new__(QuizSessionService)
        service.db = AsyncMock()
        service.session_repo = AsyncMock()
        service.participant_repo = AsyncMock()
        service.attempt_repo = AsyncMock()
        service.quiz_repo = AsyncMock()
        service.session_repo.player_session.return_value = session()
        service.participant_repo.get_by_session_user.return_value = SimpleNamespace(id=5)
        service.attempt_repo.get_or_create.return_value = attempt
        return service

    async def test_a_finished_attempt_is_not_re_scored(self):
        attempt = SimpleNamespace(id=1, finished=True, finished_at=NOW, score=8)
        service = self.service(attempt)

        with self.assertRaises(HTTPException) as caught:
            await service.finish_single_player_quiz(7, 1, [])

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(attempt.score, 8)
        service.db.commit.assert_not_awaited()

    async def test_finishing_closes_the_session(self):
        attempt = SimpleNamespace(id=1, finished=False, finished_at=None, score=0)
        service = self.service(attempt)
        quiz_session = service.session_repo.player_session.return_value
        service._build_attempt_result = AsyncMock(return_value={"total_questions": 5})

        await service.finish_single_player_quiz(7, 1, [])

        self.assertTrue(attempt.finished)
        # Left running, the sweep would later overwrite finished_at with the
        # deadline — and an untimed session would never be closed at all.
        self.assertEqual(quiz_session.status, SessionStatus.finished)
        self.assertIsNotNone(quiz_session.finished_at)

"""View model behind the Mini App analysis page.

It composes existing session services: the finished-attempt totals, the per-topic
statistic, the owner-scoped error analysis rows, and — for a room — the standing.
"""

from app.services.quiz.multiplayer import MultiplayerQuizService
from app.models.quiz.real_time_quiz.quiz_session import SessionType

# Questions carry a free-text difficulty, so order the known levels and keep the
# rest in the order they appear rather than dropping them.
DIFFICULTY_ORDER = ("oson", "orta", "qiyin")


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower().replace("‘", "").replace("'", "").replace("`", "")


def _difficulty_breakdown(questions):
    buckets: dict[str, dict] = {}
    for question in questions:
        label = (question["difficulty"] or "Belgilanmagan").strip()
        bucket = buckets.setdefault(
            _normalize(label),
            {"level": label, "total": 0, "correct": 0},
        )
        bucket["total"] += 1
        if question["user_select_option_is_correct"] is True:
            bucket["correct"] += 1

    def sort_key(item):
        key = item[0]
        return (DIFFICULTY_ORDER.index(key) if key in DIFFICULTY_ORDER else len(DIFFICULTY_ORDER), key)

    return [
        {**bucket, "percent": round(100 * bucket["correct"] / bucket["total"])}
        for _, bucket in sorted(buckets.items(), key=sort_key)
    ]


def _topic_breakdown(topic_statistic):
    rows = []
    for row in topic_statistic or []:
        total = int(row["total_questions"] or 0)
        if not total:
            continue
        correct = int(row["correct_answers"] or 0)
        rows.append(
            {
                "topic": row["topic_name"] or "Mavzusiz",
                "total": total,
                "correct": correct,
                "percent": round(100 * correct / total),
            }
        )
    return sorted(rows, key=lambda row: (row["percent"], -row["total"]))


def _question_rows(questions):
    return [
        {
            "id": question["id"],
            "question_text": question["question_text"],
            "table_markdown": question["table_markdown"],
            "topic": question["topic"],
            "difficulty": question["difficulty"],
            "images": question["images"] or [],
            "options": question["options"] or [],
            "selected_option": question["user_select_option"],
            "is_correct": question["user_select_option_is_correct"] is True,
            "answered": question["user_select_option"] is not None,
        }
        for question in questions
    ]


async def _room_standing(service, session, user_id):
    leaderboard = await service.leaderboard(session)
    scores = [
        int(row["correct_answers"] or 0)
        for row in leaderboard
        if row["total_questions"]
    ]
    rank = next(
        (index for index, row in enumerate(leaderboard, 1) if row["user_id"] == user_id),
        None,
    )
    return {
        "rank": rank,
        "participants": len(leaderboard),
        "average_correct": round(sum(scores) / len(scores)) if scores else None,
        "top": [
            {
                "display_name": row["display_name"],
                "correct_answers": int(row["correct_answers"] or 0),
                "total_questions": int(row["total_questions"] or 0),
                "is_me": row["user_id"] == user_id,
            }
            for row in leaderboard[:3]
        ],
    }


async def build_attempt_analysis(db, session_id: int, user_id: int) -> dict:
    service = MultiplayerQuizService(db)
    result = await service.get_finished_attempt_result(session_id, user_id)
    questions = await service.single_player_error_analysis(session_id, user_id)
    session = await service.session_repo.player_session(session_id)

    total = int(result["total_questions"] or 0)
    answered = int(result["answered_questions"] or 0)
    payload = {
        "session_id": session_id,
        "quiz_title": result["quiz_title"],
        "subject": result.get("subject"),
        "total_questions": total,
        "answered_questions": answered,
        "correct_answers": int(result["correct_answers"] or 0),
        "wrong_answers": int(result["wrong_answers"] or 0),
        "unanswered_questions": max(total - answered, 0),
        "percentage": result["percentage"],
        "spend_time": int(result["spend_time"] or 0),
        "topics": _topic_breakdown(result.get("topic_statistic")),
        "difficulty": _difficulty_breakdown(questions),
        "questions": _question_rows(questions),
        "room": None,
    }
    if session is not None and session.session_type != SessionType.individual:
        payload["room"] = await _room_standing(service, session, user_id)
    return payload

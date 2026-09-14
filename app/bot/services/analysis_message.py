"""Shared Telegram analysis message for a finished attempt.

Single-player and room results carry the same body; a room additionally has a
leaderboard, so passing one adds the rank, the top placings and the room average.
"""

import logging
from html import escape

from app.bot.keyboards.inline import analysis_webapp_keyboard
from app.bot.utils.progress import progress_bar

logger = logging.getLogger(__name__)

# A one-question topic scores 0% or 100% and says nothing about the student,
# so it never reaches the weak/strong lists.
MIN_TOPIC_QUESTIONS = 2
WEAK_TOPIC_LIMIT = 3
STRONG_TOPIC_LIMIT = 2
RANK_PREVIEW_LIMIT = 3
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def analysis_keyboard(session_id: int):
    """The Mini App button, or nothing when no HTTPS Web App URL is available."""
    try:
        return analysis_webapp_keyboard(session_id)
    except ValueError:
        logger.warning("No HTTPS Web App URL for session %s analysis button", session_id)
        return None


def _topic_rows(topic_statistic):
    rows = []
    for row in topic_statistic or []:
        total = int(row["total_questions"] or 0)
        if total < MIN_TOPIC_QUESTIONS:
            continue
        correct = int(row["correct_answers"] or 0)
        rows.append(
            {
                "topic_name": row["topic_name"] or "Mavzusiz",
                "total": total,
                "correct": correct,
                "percent": round(100 * correct / total),
            }
        )
    return rows


def select_topic_highlights(topic_statistic):
    """Weakest topics first, then the ones fully answered — both already capped."""
    rows = _topic_rows(topic_statistic)
    weak = sorted(
        (row for row in rows if row["percent"] < 100),
        key=lambda row: (row["percent"], -row["total"]),
    )[:WEAK_TOPIC_LIMIT]
    strong = sorted(
        (row for row in rows if row["percent"] == 100),
        key=lambda row: -row["total"],
    )[:STRONG_TOPIC_LIMIT]
    return weak, strong


def _biggest_loss(topic_statistic):
    """Topic that cost the most questions, counting wrong and unanswered alike."""
    rows = _topic_rows(topic_statistic)
    losses = [(row["total"] - row["correct"], row) for row in rows]
    losses = [entry for entry in losses if entry[0] > 0]
    if not losses:
        return None
    missed, row = max(losses, key=lambda entry: (entry[0], entry[1]["total"]))
    return {**row, "missed": missed}


def _topic_line(row):
    return f"• {escape(row['topic_name'][:60])} — {row['correct']}/{row['total']} · {row['percent']}%"


def _rank_of(leaderboard, user_id):
    for position, row in enumerate(leaderboard, 1):
        if row["user_id"] == user_id:
            return position
    return None


def _rank_lines(leaderboard, user_id, rank):
    """Top three, plus the reader's own row when they placed below it."""
    positions = list(range(1, min(RANK_PREVIEW_LIMIT, len(leaderboard)) + 1))
    if rank and rank not in positions:
        positions.append(rank)

    lines = []
    for position in positions:
        row = leaderboard[position - 1]
        medal = MEDALS.get(position, f"{position}.")
        total = int(row["total_questions"] or 0)
        correct = int(row["correct_answers"] or 0)
        if row["user_id"] == user_id:
            name = "<b>Siz</b>"
        else:
            name = escape(row["display_name"][:60])
        lines.append(f"{medal} {name} — {correct}/{total}")
    return lines


def _room_average(leaderboard):
    scores = [
        int(row["correct_answers"] or 0)
        for row in leaderboard
        if row["total_questions"]
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores))


def format_analysis_message(result, leaderboard=(), user_id=None) -> str:
    """Without a leaderboard this is the single-player message; with one it gains
    the room rank, the top placings and the room average."""
    total = int(result["total_questions"] or 0)
    correct = int(result["correct_answers"] or 0)
    answered = int(result["answered_questions"] or 0)
    percent = round(result["percentage"] or 0)
    minutes, seconds = divmod(int(result["spend_time"] or 0), 60)
    wrong = result.get("wrong_answers")
    if wrong is None:
        wrong = max(answered - correct, 0)
    rank = _rank_of(leaderboard, user_id) if leaderboard else None

    lines = [
        "📊 <b>Test tahlili tayyor</b>",
        "",
        f"📚 {escape((result.get('subject') or 'Umumiy')[:80])}",
        f"📝 <b>{escape(result['quiz_title'][:180])}</b>",
    ]
    if rank:
        lines.append(f"👥 Xonada: <b>{rank}-o‘rin</b> / {len(leaderboard)} ta")
    lines.extend(
        [
            "",
            f"🎯 Natija: <b>{correct}/{total} · {percent}%</b>",
            f"{progress_bar(percent)} {percent}%",
            "",
            f"✅ To‘g‘ri: <b>{correct}</b>   ❌ Xato: <b>{int(wrong)}</b>",
            f"⚪️ Javobsiz: <b>{max(total - answered, 0)}</b>   ⏱ <b>{minutes:02}:{seconds:02}</b>",
        ]
    )

    if leaderboard:
        lines.extend(["", *_rank_lines(leaderboard, user_id, rank)])

    weak, strong = select_topic_highlights(result.get("topic_statistic"))
    if weak:
        lines.extend(["", "🔻 <b>Zaif mavzular</b>", *(_topic_line(row) for row in weak)])
    if strong:
        lines.extend(["", "🟢 <b>Kuchli mavzular</b>", *(_topic_line(row) for row in strong)])

    footer = []
    loss = _biggest_loss(result.get("topic_statistic"))
    if loss:
        footer.append(
            f"💡 Eng ko‘p yo‘qotish — <b>{escape(loss['topic_name'][:60])}</b>: "
            f"{loss['total']} tadan {loss['missed']} tasi."
        )
    average = _room_average(leaderboard)
    if average is not None:
        footer.append(f"Xonadagi o‘rtacha natija — {average}/{total}.")
    if footer:
        lines.extend(["", " ".join(footer)])

    return "\n".join(lines)

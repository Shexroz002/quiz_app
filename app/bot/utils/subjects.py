"""The subject catalogue as the bot shows it: display icons and the loader.

Both the registration picker and the AI quiz flow read subjects from here, so a
subject looks the same wherever it appears.
"""

from app.core.database.base import AsyncSessionLocal
from app.services.subject.subject_service import SubjectService

#: Keyword -> icon, matched against a lower-cased subject name; first hit wins.
#: Only a fallback: a subject row that carries its own ``icon`` keeps it.
SUBJECT_ICONS = {
    "matematika": "📐",
    "algebra": "📐",
    "geometriya": "📐",
    "fizika": "⚛️",
    "kimyo": "🧪",
    "biologiya": "🧬",
    "tarix": "🏛️",
    "geografiya": "🌍",
    "ona tili": "📖",
    "adabiyot": "📖",
    "ingliz": "🔤",
}


def subject_icon(subject: str | None) -> str:
    normalized_subject = (subject or "").lower()
    return next(
        (icon for keyword, icon in SUBJECT_ICONS.items() if keyword in normalized_subject),
        "📘",
    )


def _display_icon(stored: str | None, name: str) -> str:
    """The icon a Telegram button shows.

    ``subjects.icon`` holds web icon names for the frontend ("zap", "calculator"),
    which Telegram would print as literal text. Only a non-ASCII value is a real
    emoji and can be shown as-is; anything else falls back to the keyword map.
    """
    candidate = (stored or "").strip()
    if candidate and not candidate.isascii():
        return candidate
    return subject_icon(name)


async def load_subjects() -> list[dict]:
    """Every subject with a display icon.

    Sorted by id: the repository does not order its rows, and an unstable order
    would reshuffle the buttons between two views of the same list.
    """
    async with AsyncSessionLocal() as db:
        subjects = await SubjectService(db).list()
    return sorted(
        (
            {
                "id": subject.id,
                "name": subject.name,
                "icon": _display_icon(subject.icon, subject.name),
            }
            for subject in subjects
        ),
        key=lambda row: row["id"],
    )

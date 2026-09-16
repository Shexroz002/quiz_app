from collections import Counter
ALLOWED_SUBJECTS = (
    "Matematika",
    "Fizika",
    "Kimyo",
    "Biologiya",
    "Tarix",
    "Geografiya",
    "Ona tili va adabiyoti",
    "Ingliz tili",
)

_CANONICAL = {name.casefold(): name for name in ALLOWED_SUBJECTS}


_ALIASES = {
    "algebra": "Matematika",
    "geometriya": "Matematika",
    "trigonometriya": "Matematika",
    "stereometriya": "Matematika",
    "arifmetika": "Matematika",
    "mexanika": "Fizika",
    "optika": "Fizika",
    "termodinamika": "Fizika",
    "elektr": "Fizika",
    "organik kimyo": "Kimyo",
    "anorganik kimyo": "Kimyo",
    "anatomiya": "Biologiya",
    "botanika": "Biologiya",
    "zoologiya": "Biologiya",
    "genetika": "Biologiya",
    "vatan tarixi": "Tarix",
    "jahon tarixi": "Tarix",
    "ona tili": "Ona tili va adabiyoti",
    "o'zbek tili": "Ona tili va adabiyoti",
    "adabiyot": "Ona tili va adabiyoti",
    "english": "Ingliz tili",
    "english language": "Ingliz tili",
}


def _clean(value) -> str:
    """Lower-case, collapse whitespace and unify the apostrophes Uzbek text uses."""
    text = str(value or "")
    for apostrophe in ("‘", "’", "`", "ʻ"):
        text = text.replace(apostrophe, "'")
    return " ".join(text.split()).casefold()


def canonical_subject(value) -> str | None:
    """Return the catalogue name for ``value``, or ``None`` when it cannot be resolved."""
    text = _clean(value)
    if not text:
        return None
    if text in _CANONICAL:
        return _CANONICAL[text]
    if text in _ALIASES:
        return _ALIASES[text]
    # "Matematika (algebra)" and "9-sinf matematika" still name their subject.
    for key, name in (*_CANONICAL.items(), *_ALIASES.items()):
        if key in text:
            return name
    return None


def resolve_quiz_subject(data: dict, fallback=None) -> str:

    resolved = canonical_subject(data.get("subject"))
    if resolved:
        return resolved

    votes = Counter(
        name
        for name in (
            canonical_subject(question.get("subject"))
            for question in data.get("questions") or []
        )
        if name
    )
    if votes:
        return votes.most_common(1)[0][0]

    resolved = canonical_subject(fallback)
    if resolved:
        return resolved

    raise ValueError("Test fani aniqlanmadi. Boshqa fayl yoki aniqroq mavzu bilan urinib ko'ring.")

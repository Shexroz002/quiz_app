"""Prompts and response schemas for quiz generation.

Both providers are called with structured output on -- Gemini with
``response_schema``, Mistral with ``response_format: json_schema`` -- so the
reply can only ever be schema-shaped JSON. Rules that restate the schema
("return valid JSON", "no code fences", the full output example) buy nothing and
are left out; the prompts carry only what a schema cannot say.
"""

from app.services.ai.subjects import ALLOWED_SUBJECTS

_SUBJECT_LIST = "\n".join(f"   - {name}" for name in ALLOWED_SUBJECTS)

#: Injected into every prompt that has to name a subject.
_SUBJECT_RULE = f"""   The subject MUST be copied from this list, character for character:
{_SUBJECT_LIST}
   Never invent another subject and never translate or re-spell these names.
   A narrower topic (for example "Algebra", "Mexanika" or "Grammatika") belongs
   in "meta.topic", never in a "subject" field.
   If the source does not clearly match one of them, pick the closest one."""

#: The PDF carries no usable image ids, so questions point at placeholders.
_PLACEHOLDER_IMAGE_RULE = """Images: use the image URL when the source has one,
   otherwise a placeholder such as ["[image_1]", "[image_2]"]. No image: []."""

#: The OCR step hands over real file ids; inventing one breaks the saved quiz.
_OCR_IMAGE_RULE = """Images: put only the exact image ids returned by the OCR
   system, preserved character for character, for example ["img-2.png"] or
   ["img-2.png", "img-3.jpeg"]. Never generate, recreate or invent image data.
   No image: []."""

_EXTRACTION_PROMPT = """
You are an AI system that extracts structured quiz data from a PDF file.
Analyze every test question in the provided PDF and fill the response schema.

For a value the source does not give, use "" for a text field and [] for an array.

RULES:
1. Extract all questions and keep the original language of the question text.
2. Give every question a unique incremental numeric id, starting from 1.
3. Set the subject on the root object and on every question.
__SUBJECT_RULE__
4. Write the quiz description in Uzbek, maximum 235 characters.
5. Convert a table inside a question to Markdown and put it in "table_markdown".
6. __IMAGE_RULE__
7. Mark the correct option with "is_correct": true and every other option false.
   When the correct answer is not recoverable, leave all options false.
8. "meta" is written in Uzbek and carries the question's difficulty and topic.
9. Write every mathematics, physics and chemistry formula as LaTeX inside $...$
   -- "$E=mc^2$", "$\\frac{a}{b}$", "$\\sqrt{x}$", "$\\pi$", "^\\circ" -- never as
   a plain-text approximation. Escape each backslash for JSON: a single
   backslash in the output is always a bug.
"""


def _extraction_prompt(image_rule: str) -> str:
    return (
        _EXTRACTION_PROMPT
        .replace("__SUBJECT_RULE__", _SUBJECT_RULE)
        .replace("__IMAGE_RULE__", image_rule)
    )


QUIZ_PROMPT = _extraction_prompt(_PLACEHOLDER_IMAGE_RULE)
QUIZ_PROMPT_MISTRAL = _extraction_prompt(_OCR_IMAGE_RULE)


#: One definition for both providers: Gemini wants the same JSON Schema with
#: upper-case type names, which ``_as_gemini`` derives below.
QUIZ_SCHEMA_MISTRAL = {
    "type": "object",
    "properties": {
        "quiz_title": {"type": "string"},
        "subject": {"type": "string", "enum": list(ALLOWED_SUBJECTS)},
        "description": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "question": {"type": "string"},
                    "images": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "subject": {"type": "string", "enum": list(ALLOWED_SUBJECTS)},
                    "table_markdown": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": "string"},
                                "is_correct": {"type": "boolean"}
                            },
                            "required": ["id", "text", "is_correct"]
                        }
                    },
                    "meta": {
                        "type": "object",
                        "properties": {
                            "difficulty": {"type": "string"},
                            "topic": {"type": "string"}
                        }
                    }
                },
                "required": [
                    "id",
                    "question",
                    "images",
                    "subject",
                    "table_markdown",
                    "options",
                    "meta"
                ]
            }
        }
    },
    "required": ["quiz_title", "subject", "description", "questions"]
}


def _as_gemini(node):
    """The same schema in Gemini's dialect: only the type names are upper-cased."""
    if isinstance(node, dict):
        return {
            key: value.upper() if key == "type" and isinstance(value, str) else _as_gemini(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_as_gemini(item) for item in node]
    return node


QUIZ_SCHEMA = _as_gemini(QUIZ_SCHEMA_MISTRAL)


def ai_generator_by_description(subject: str, description: str, question_count: int) -> str:
    """The prompt for a quiz generated from a topic the student typed.

    No difficulty and no image source reach this call, so the prompt sets both
    itself: the difficulty mix is left to the model and "images" stays empty.
    """
    return f"""
You are an AI system that generates structured academic test questions.

INPUTS:
- SUBJECT: {subject}
- DESCRIPTION: {description}
- QUESTION_COUNT: {question_count}

RULES:
1. Generate exactly {question_count} questions about SUBJECT, covering what
   DESCRIPTION asks for. No duplicate or near-duplicate questions.
2. Every question has exactly 4 options, exactly one of them "is_correct": true.
   Wrong options must be plausible and educational, never filler.
3. Give every question a unique incremental numeric id, starting from 1.
4. ALL text MUST be written in Uzbek -- quiz_title, description, question,
   options and every "meta" value. Never switch to English or another language.
5. "meta" carries difficulty, topic and subject. "difficulty" is exactly one of:
   - "oson"  -> to'g'ridan-to'g'ri, oddiy tushunish darajasi
   - "o'rta" -> biroz fikrlash, formuladan foydalanish
   - "qiyin" -> murakkab, bir nechta bosqichli yechim
   Use all three across the quiz instead of one level for every question.
6. "meta.subject" is SUBJECT copied character for character. SUBJECT is always
   one of the platform's subjects:
{_SUBJECT_LIST}
   Never replace it with a narrower topic name and never translate it.
7. Write every mathematics, physics and chemistry formula as LaTeX inside $...$
   and escape each backslash for JSON. Use LaTeX only where a formula needs it.
8. "images" is always [] -- a generated question has no source image.
"""

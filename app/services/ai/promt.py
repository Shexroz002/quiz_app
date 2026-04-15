QUIZ_PROMPT = """
You are an AI system that extracts structured quiz data from a PDF file.

TASK:
Analyze all test questions in the provided PDF and return them in the exact JSON structure defined below.

OUTPUT RULES:
1. Return valid JSON only.
2. Do not include markdown, comments, explanations, or extra text.
3. Do not wrap the JSON in code fences.
4. The response must start with { and end with }.
5. Follow the schema exactly. Do not add, remove, or rename fields.
6. If a value is missing in the source:
   - use "" for text fields
   - use [] for arrays
   - use null only when the value is truly unknown

EXTRACTION RULES:
1. Extract all questions from the PDF.
2. Preserve the original language of the question text.
3. Assign a unique incremental numeric id to each question.
4. Detect the subject automatically and set it in:
   - root "subject"
   - each question "subject"
5. Write the quiz description in Uzbek, maximum 235 characters.
6. If a question contains a table, convert it to Markdown and store it in "table_markdown".
7. If a question contains images:
   - use image URLs if available
   - otherwise use placeholders like ["[image_1]", "[image_2]"]
8. Identify the correct answer if possible:
   - set "is_correct": true only for the correct option
   - set all other options to false
   - if unknown, set all options to false
9. The "meta" field must be in Uzbek and may include useful details such as difficulty and topic.

FORMULA RULES:
1. All mathematics, physics, and chemistry formulas must be written in LaTeX.
2. Preserve formulas as digital text, not plain-text approximations.
3. All LaTeX backslashes must be escaped for JSON.
   Examples:
   - $\\frac{a}{b}$
   - $\\sqrt{x}$
   - $\\pi$
   - ^\\circ
4. Never output single backslashes in JSON.

Before returning the result, internally ensure the JSON is syntactically valid.

OUTPUT JSON STRUCTURE:

{
  "quiz_title": "...",
  "subject": "...",
  "description": "...",
  "questions": [
    {
      "id": 1,
      "question": "Quyidagi formulani tanlang: $E=mc^2$",
      "images": ["[image_1]"],
      "subject": "...",
      "table_markdown": "...",
      "options": [
        {
          "id": "A",
          "text": "$E=mc^2$",
          "is_correct": true
        },
        {
          "id": "B",
          "text": "$E=\\frac{1}{2}mv^2$",
          "is_correct": false
        }
      ],
      "meta": {
        "difficulty": "oson",
        "topic": "..."
      }
    }
  ]
}
"""

QUIZ_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "quiz_title": {"type": "STRING"},
        "subject": {"type": "STRING"},
        "description": {"type": "STRING"},
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "INTEGER"},
                    "question": {"type": "STRING"},
                    "images": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    },
                    "subject": {"type": "STRING"},
                    "table_markdown": {"type": "STRING"},
                    "options": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "id": {"type": "STRING"},
                                "text": {"type": "STRING"},
                                "is_correct": {"type": "BOOLEAN"}
                            },
                            "required": ["id", "text", "is_correct"]
                        }
                    },
                    "meta": {
                        "type": "OBJECT",
                        "properties": {
                            "difficulty": {"type": "STRING"},
                            "topic": {"type": "STRING"}
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



def ai_generator_by_description(subject: str, description: str, question_count: int) -> str:
    text_prompt = f"""
    You are an AI system that generates structured academic test questions from user input.

    TASK:
    Generate a quiz based on:
    - selected subject
    - user-written description
    - requested number of questions
    - selected difficulty

    INPUTS:
    - SUBJECT: {subject}
    - QUESTION_COUNT: {question_count}
    - DESCRIPTION: {description}

    STRICT OUTPUT RULES (VERY IMPORTANT):
    1. Output MUST be valid JSON only.
    2. Do NOT include explanations, comments, markdown, or extra text outside JSON.
    3. Do NOT wrap JSON inside code blocks.
    4. The response must start with `{{` and end with `}}`.
    5. Follow the JSON schema EXACTLY. Do not add or remove fields.
    6. Generate exactly {question_count} questions.

    LANGUAGE RULES (VERY STRICT):
    1. ALL output text MUST be written ONLY in Uzbek language.
    2. DO NOT use English or any other language in ANY field.
    3. This includes:
       - title
       - description
       - question_text
       - options.text
       - answer_explain
       - meta fields (difficulty, topic, subject)
    4. Even short labels, explanations, and descriptions MUST be in Uzbek.
    5. If SUBJECT is given in Uzbek, DO NOT translate it.

    DIFFICULTY DISTRIBUTION RULES:
    1. You MUST strictly follow difficulty distribution:

       IF counts are provided:
       - Generate exactly EASY_COUNT easy questions
       - Generate exactly MEDIUM_COUNT medium questions
       - Generate exactly HARD_COUNT hard questions

       IF percentages are provided:
       - Calculate counts based on QUESTION_COUNT
       - Distribute questions accordingly
       - Ensure total equals QUESTION_COUNT

    2. Difficulty levels must be:
       - "oson"
       - "o‘rta"
       - "qiyin"

    3. Assign difficulty per question inside `meta.difficulty`.

    4. Difficulty meaning:
       - oson → oddiy tushunish darajasi, to‘g‘ridan-to‘g‘ri savollar
       - o‘rta → biroz fikrlash, formuladan foydalanish
       - qiyin → murakkab tahlil, bir nechta bosqichli yechim

    CONTENT RULES:
    1. All questions must belong to the given SUBJECT.
    2. All questions must match the DESCRIPTION.
    3. All questions must match the selected DIFFICULTY.
    4. Avoid duplicate and near-duplicate questions.
    5. Each question must have exactly 4 options.
    6. Only one option must have `"is_correct": true`.
    7. Incorrect options must be realistic and educational.

    FORMULA RULES:
    1. ALL mathematical, physics, and chemistry formulas MUST be written in LaTeX format.
    2. All LaTeX backslashes MUST be escaped for JSON.
    3. Wrap formulas in question text with `$...$`.
    4. Wrap formulas in explanations with `\\( ... \\)`.
    5. Use LaTeX only when necessary.

    STRUCTURE RULES:
    1. Each question MUST have unique incremental numeric `id`, starting from 1.
    2. `meta` must contain:
       - difficulty
       - topic
       - subject
    3. `meta` values must be written in Uzbek language.
    4. Use SUBJECT exactly as provided.

    FINAL INSTRUCTIONS:
    - Use SUBJECT as fixed input.
    - Use DIFFICULTY as fixed input.
    - Use DESCRIPTION to determine topic coverage, style, and scope.
    - Generate exactly {question_count} questions.
    - Return valid JSON only.
    - Ensure ALL textual content is strictly in Uzbek language.
    """

    return text_prompt
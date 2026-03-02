QUIZ_PROMPT = """
You are an AI system that extracts structured test data from a PDF file.
TASK:
Analyze ALL test questions contained in the provided PDF and convert them into the EXACT structured JSON format defined below.

STRICT OUTPUT RULES (VERY IMPORTANT):
1. Output MUST be valid JSON only.
2. Do NOT include explanations, comments, markdown, or extra text.
3. Do NOT wrap JSON inside code blocks.
4. The response must start with `{` and end with `}`.
5. Follow the JSON schema EXACTLY. Do not add or remove fields.
6. If a field does not exist in the source, return:
   - empty string "" for text fields
   - empty array [] for lists
   - null only if value is truly unknown.

CONTENT RULES:
1. ALL mathematical, physics, and chemistry formulas MUST be written in LaTeX format.
    All LaTeX backslashes MUST be escaped for JSON.
    Example:
        $\frac{a}{b}$ → "$\\frac{a}{b}$"
2. Preserve formulas as digital text (never plain text approximations).

3. If the question contains tables, convert them into Markdown table format and store inside `table_markdown`.

4. Extract image references if present:
   - Use image URLs if available.
   - Otherwise generate placeholders like:
     ["[image_1]", "[image_2]"]

5. Identify the correct answer whenever possible:
   - Set `"is_correct": true` only for the correct option.
   - Others must be false.

6. Detect subject automatically (fizika, matematika, kimyo, bialogiya, etc.).

7. Keep original language of the question text.

8. Each question MUST have unique incremental numeric `id`.


9. The `meta` field can include any additional information you find relevant (e.g., difficulty, topic) and must be in uzbek language.
10. Before sending the answer, you MUST internally validate that the JSON is syntactically correct.

JSON ESCAPING RULES (STRICT):
- Every backslash in LaTeX MUST be double escaped (\\).
- Never output single backslashes.
- Escape sequences like \s, \c, \m are INVALID in JSON.
- Valid examples:
  \frac → \\frac
  \sqrt → \\sqrt
  \pi → \\pi
  ^\circ → ^\\circ
  \mathcal → \\mathcal

OUTPUT JSON SCHEMA (DO NOT MODIFY STRUCTURE):

{
    "quiz_title": "Fizika Testi",
    "questions": [
        {
            "id": 1,
            "question": "Quyidagi formulani LaTeX formatida yozing: $E=mc^2$",
            "images": [
                "image_1",
                "image_2"
            ],
            "subject": "physics",
            "table_markdown": "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |",
            "options": [
                {
                    "id": "A",
                    "text": "$E=mc^2$",
                    "is_correct": true
                },
                {
                    "id": "B",
                    "text": "E=mc^2",
                    "is_correct": false
                },
                {
                    "id": "C",
                    "text": "$E=\\frac{1}{2}mv^2$",
                    "is_correct": false
                },
                {
                    "id": "D",
                    "text": "E=\\sqrt{mc^2}",
                    "is_correct": false
                }
            ],
            "meta": {
                "difficulty": "easy",
                "topic": "Relativity"
            }
        }
    ]
}

"""

QUIZ_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "quiz_title": {"type": "STRING"},
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "id": {"type": "INTEGER"},
                    "question": {"type": "STRING"},
                    "images": {"type": "ARRAY", "items": {"type": "STRING"}},
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
                "required": ["id", "question", "options"]
            }
        }
    },
    "required": ["quiz_title", "questions"]
}
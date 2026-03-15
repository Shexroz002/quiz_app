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
  "quiz_title": "Fizika Testi",
  "subject": "physics",
  "description": "Bu fizika fanidan test savollari to‘plami.",
  "questions": [
    {
      "id": 1,
      "question": "Quyidagi formulani tanlang: $E=mc^2$",
      "images": ["[image_1]"],
      "subject": "physics",
      "table_markdown": "",
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
        "topic": "Nisbiylik"
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
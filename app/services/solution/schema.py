"""Structured-output schemas for the solution model.

The model fills the schema field by field, in ``propertyOrdering`` order. The
order is part of the design: the steps come before the answer, and the answer
before ``chosen_option``, so the model commits to a derivation before it looks
at the options.
"""

_STR = {"type": "STRING"}
_NULL_STR = {"type": "STRING", "nullable": True}

_BOARD_LINE = {
    "type": "OBJECT",
    "properties": {
        "tex": _STR,
        "role": {"type": "STRING", "enum": ["formula", "step", "result"]},
    },
    "required": ["tex", "role"],
    "propertyOrdering": ["tex", "role"],
}

_STEP = {
    "type": "OBJECT",
    "properties": {
        "title": _STR,
        "say": _STR,
        "board": {"type": "ARRAY", "items": _BOARD_LINE},
        "summary": _STR,
        "tip": _NULL_STR,
        "simpler": {"type": "ARRAY", "items": _STR},
        "rule": _NULL_STR,
    },
    "required": ["title", "say", "board", "summary", "simpler"],
    "propertyOrdering": ["title", "say", "board", "summary", "tip", "simpler", "rule"],
}

SOLUTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "problem_ok": {"type": "BOOLEAN"},
        "problem_note": _NULL_STR,
        "kind": {"type": "STRING", "enum": ["math", "physics", "word"]},
        "asked": _STR,
        "plan": {"type": "ARRAY", "items": _STR},
        "values": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": _STR,
                    "label": _STR,
                    "value": _STR,
                    "color": {"type": "INTEGER"},
                },
                "required": ["name", "label", "value", "color"],
            },
        },
        "given": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "symbol": _STR,
                    "value": _STR,
                    "unit": _STR,
                    "label": _STR,
                    "color": {"type": "INTEGER"},
                },
                "required": ["symbol", "value", "unit", "label", "color"],
            },
        },
        "find": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"symbol": _STR, "label": _STR, "unit": _STR},
                "required": ["symbol", "label", "unit"],
            },
        },
        "formula": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {
                "name": _STR,
                "tex": _STR,
                "legend": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {"symbol": _STR, "meaning": _STR, "unit": _STR},
                        "required": ["symbol", "meaning", "unit"],
                    },
                },
            },
            "required": ["name", "tex", "legend"],
        },
        "tape": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {
                "total": _STR,
                "parts": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {"label": _STR, "expr": _STR, "weight": {"type": "NUMBER"}},
                        "required": ["label", "expr", "weight"],
                    },
                },
            },
            "required": ["total", "parts"],
        },
        "steps": {"type": "ARRAY", "items": _STEP},
        "answer": {
            "type": "OBJECT",
            "properties": {"tex": _STR, "value": _STR, "words": _STR, "unit": _NULL_STR},
            "required": ["tex", "value", "words"],
        },
        "check": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {"say": _STR, "tex": _STR},
            "required": ["say", "tex"],
        },
        "shortcut": {
            "type": "OBJECT",
            "nullable": True,
            "properties": {
                "title": _STR,
                "say": _STR,
                "board": {"type": "ARRAY", "items": _STR},
            },
            "required": ["title", "say", "board"],
        },
        "real_life": _NULL_STR,
        "chosen_option": _NULL_STR,
        "hints": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "option": _STR,
                    "headline": _STR,
                    "right_tex": _STR,
                    "wrong_tex": _STR,
                    "why": _STR,
                    "tip": _STR,
                },
                "required": ["option", "headline", "right_tex", "wrong_tex", "why", "tip"],
            },
        },
    },
    "required": [
        "problem_ok", "kind", "asked", "plan", "values", "given", "find",
        "steps", "answer", "hints",
    ],
    "propertyOrdering": [
        "problem_ok", "problem_note", "kind", "asked", "plan", "values", "given", "find",
        "formula", "tape", "steps", "answer", "check", "shortcut", "real_life",
        "chosen_option", "hints",
    ],
}

RECOGNIZE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "readable": {"type": "BOOLEAN"},
        "text": _STR,
        "subject": {"type": "STRING", "enum": ["matematika", "fizika", "boshqa"]},
        "multiple": {"type": "BOOLEAN"},
    },
    "required": ["readable", "text", "subject", "multiple"],
    "propertyOrdering": ["readable", "text", "subject", "multiple"],
}

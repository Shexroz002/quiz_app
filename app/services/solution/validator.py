"""Checks a model reply before anything is stored or shown.

Two kinds of rules:

- **hard** — the app cannot render the reply, or it would mislead (a missing
  step, an unknown colour, an option that does not exist). The reply is sent
  back for repair and dropped if it still fails.
- **soft** — the reply works but breaks a reading rule (a sentence too long,
  a title too wordy). Sent back for repair once; kept if the repair is no better.
"""

import re
from dataclasses import dataclass, field

_MACRO = re.compile(r"\\hl([a-z])\{")
_COLOUR_OF = {"a": 1, "b": 2, "c": 3}
#: Control characters a broken escape leaves behind: a lone "\v" or "\f" in the
#: model's JSON arrives as a vertical tab or a form feed instead of a command.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MACRO_OUTSIDE_MATH = re.compile(r"\\hl[a-z]\{")
_FORBIDDEN_COLOUR = re.compile(r"\\(textcolor|color|colorbox)\b")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_INLINE_MATH = re.compile(r"\$[^$]*\$")

MAX_STEPS = 8
SAY_MAX_SENTENCES = 2
SAY_MAX_WORDS = 22  # the prompt asks for 18; a little slack before it counts
TITLE_MAX_WORDS = 6


@dataclass
class Verdict:
    """What the validator found, split by severity."""

    hard: list[str] = field(default_factory=list)
    soft: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hard and not self.soft

    @property
    def usable(self) -> bool:
        return not self.hard

    def all(self) -> list[str]:
        return self.hard + self.soft


def _words(text: str) -> int:
    # Inline maths counts as one word: "$x_2 = -\frac12$" is one thing to read.
    return len(_INLINE_MATH.sub("M", text).split())


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(_INLINE_MATH.sub("M", text.strip())) if s]


_BREAK = re.compile(r"\s*\n\s*")


def _one_line(text):
    # Prose is one or two sentences; a line break inside it is an artefact and
    # would split a sentence on screen.
    return _BREAK.sub(" ", text).strip() if isinstance(text, str) else text


_DECIMAL_DOT = re.compile(r"(?<=\d)\.(?=\d)")


def _comma_tex(tex):
    # Uzbek schools write 1,5. In LaTeX a bare comma adds a space after it,
    # so the decimal comma is braced: 1{,}5.
    return _DECIMAL_DOT.sub("{,}", tex) if isinstance(tex, str) else tex


def _comma_prose(text):
    if not isinstance(text, str):
        return text
    parts = re.split(r"(\$[^$]*\$)", text)
    return "".join(
        _comma_tex(part) if part.startswith("$") else _DECIMAL_DOT.sub(",", part) for part in parts
    )


def normalize(data: dict) -> dict:
    """Fixes what is safe to fix silently, so it never costs a repair round."""
    data["asked"] = _one_line(data.get("asked"))
    data["real_life"] = _one_line(data.get("real_life"))
    for step in data.get("steps") or []:
        for key in ("say", "tip", "summary", "title"):
            step[key] = _one_line(step.get(key))
        step["simpler"] = [_one_line(t) for t in step.get("simpler") or []]
    for hint in data.get("hints") or []:
        for key in ("headline", "why", "tip"):
            hint[key] = _one_line(hint.get(key))
    for step in data.get("steps") or []:
        for line in step.get("board") or []:
            line["tex"] = _comma_tex((line.get("tex") or "").strip().strip("$").strip())
        for key in ("say", "summary", "tip"):
            step[key] = _comma_prose(step.get(key))
        step["simpler"] = [_comma_prose(t) for t in step.get("simpler") or []]
    tape = data.get("tape")
    if isinstance(tape, dict):
        for part in tape.get("parts") or []:
            part["expr"] = _comma_tex(part.get("expr"))
    for value in data.get("values") or []:
        value["value"] = _DECIMAL_DOT.sub(",", value.get("value") or "")
    data["asked"] = _comma_prose(data.get("asked"))
    answer = data.get("answer") or {}
    if answer.get("tex"):
        answer["tex"] = _comma_tex(answer["tex"].strip().strip("$").strip())
    formula = data.get("formula")
    if formula and formula.get("tex"):
        formula["tex"] = formula["tex"].strip().strip("$").strip()
    for hint in data.get("hints") or []:
        for key in ("right_tex", "wrong_tex"):
            hint[key] = (hint.get(key) or "").strip().strip("$").strip()
        hint["option"] = (hint.get("option") or "").strip().upper()
    if isinstance(data.get("chosen_option"), str):
        data["chosen_option"] = data["chosen_option"].strip().upper() or None
    return data


def _tex_fields(data: dict) -> list[str]:
    out: list[str] = []
    for step in data.get("steps") or []:
        out += [line.get("tex") or "" for line in step.get("board") or []]
    out.append((data.get("answer") or {}).get("tex") or "")
    if data.get("formula"):
        out.append(data["formula"].get("tex") or "")
    if data.get("check"):
        out.append(data["check"].get("tex") or "")
    for hint in data.get("hints") or []:
        out += [hint.get("right_tex") or "", hint.get("wrong_tex") or ""]
    return out


def _prose_fields(data: dict) -> list[tuple[str, str]]:
    out = [("asked", data.get("asked") or "")]
    for i, step in enumerate(data.get("steps") or [], 1):
        out.append((f"step {i} say", step.get("say") or ""))
        out += [(f"step {i} simpler", t) for t in step.get("simpler") or []]
        out.append((f"step {i} tip", step.get("tip") or ""))
    out.append(("real_life", data.get("real_life") or ""))
    for hint in data.get("hints") or []:
        out += [("hint", hint.get(k) or "") for k in ("headline", "why", "tip")]
    return out


def validate(data: dict, *, option_labels: list[str] | None = None) -> Verdict:
    """Checks a normalised reply. ``option_labels`` is given for bank questions."""
    v = Verdict()

    if data.get("problem_ok") is False:
        if not (data.get("problem_note") or "").strip():
            v.hard.append("problem_ok is false but problem_note is empty")
        return v

    if data.get("kind") not in ("math", "physics", "word"):
        v.hard.append("kind must be math, physics or word")

    steps = data.get("steps") or []
    plan = data.get("plan") or []
    if not 1 <= len(steps) <= MAX_STEPS:
        v.hard.append(f"use 1-{MAX_STEPS} steps, not {len(steps)}")
    if len(plan) != len(steps):
        v.hard.append(f"plan has {len(plan)} items but there are {len(steps)} steps; one plan item per step")

    for i, step in enumerate(steps, 1):
        if not (step.get("title") or "").strip():
            v.hard.append(f"step {i}: title is empty")
        elif len(step["title"].split()) > TITLE_MAX_WORDS:
            v.soft.append(f"step {i}: title has more than {TITLE_MAX_WORDS} words")
        say = (step.get("say") or "").strip()
        if not say:
            v.hard.append(f"step {i}: say is empty")
        else:
            sentences = _sentences(say)
            if len(sentences) > SAY_MAX_SENTENCES:
                v.soft.append(f"step {i}: say has {len(sentences)} sentences, at most {SAY_MAX_SENTENCES}")
            for s in sentences:
                if _words(s) > SAY_MAX_WORDS:
                    v.soft.append(f"step {i}: a sentence in say has {_words(s)} words, keep it under 18")
                    break
        board = [line for line in step.get("board") or [] if (line.get("tex") or "").strip()]
        if not board:
            v.hard.append(f"step {i}: board is empty")
        if not (step.get("summary") or "").strip():
            v.hard.append(f"step {i}: summary is empty")
        simpler = [s for s in step.get("simpler") or [] if s.strip()]
        if not simpler:
            v.hard.append(f"step {i}: simpler is empty")
        elif len(simpler) > 5:
            v.soft.append(f"step {i}: simpler has {len(simpler)} sentences, at most 4")

    answer = data.get("answer") or {}
    if not (answer.get("tex") or "").strip():
        v.hard.append("answer.tex is empty")
    if not (answer.get("words") or "").strip():
        v.soft.append("answer.words is empty: say how the answer is read aloud")

    colours = [c.get("color") for c in (data.get("values") or []) + (data.get("given") or [])]
    if any(c not in (1, 2, 3) for c in colours):
        v.hard.append("every color must be 1, 2 or 3")
    if len(colours) != len(set(colours)):
        v.hard.append("two values share a color; each value needs its own")
    letters = {m for tex in _tex_fields(data) for m in _MACRO.findall(tex)}
    if letters - set(_COLOUR_OF):
        v.hard.append(f"unknown colour mark \\hl{sorted(letters - set(_COLOUR_OF))[0]}; use \\hla, \\hlb or \\hlc")
    used = {_COLOUR_OF[m] for m in letters if m in _COLOUR_OF}
    if used - set(colours):
        v.hard.append(f"colour {sorted(used - set(colours))[0]} is marked but no value has that color")
    if any(_FORBIDDEN_COLOUR.search(tex) for tex in _tex_fields(data)):
        v.hard.append("do not use \\color or \\textcolor; mark values with \\hla, \\hlb, \\hlc")
    if any("$" in tex for tex in _tex_fields(data)):
        v.hard.append("tex fields are pure LaTeX: remove every $ sign, put words in \\text{...}")
    if any(_CONTROL.search(text) or "\n" in text for text in _tex_fields(data)):
        v.hard.append("a tex field contains a line break or control character; escape backslashes as \\\\")
    for name, text in _prose_fields(data):
        if _CONTROL.search(text):
            v.hard.append(f"{name} contains a control character; escape backslashes as \\\\")
            break
        if _MACRO_OUTSIDE_MATH.search(_INLINE_MATH.sub("", text)):
            v.hard.append(f"{name}: colour marks are allowed only inside $...$")
            break

    if data.get("kind") == "physics":
        if not data.get("given"):
            v.hard.append("physics: given is empty")
        if not data.get("find"):
            v.hard.append("physics: find is empty")
        if any(not (g.get("unit") or "").strip() for g in data.get("given") or []):
            v.soft.append("physics: a given value has no unit")

    if option_labels is not None:
        chosen = data.get("chosen_option")
        if chosen is not None and chosen not in option_labels:
            v.hard.append(f"chosen_option {chosen!r} is not one of {option_labels}")
        hinted = {h.get("option") for h in data.get("hints") or []}
        if hinted - set(option_labels):
            v.hard.append(f"hint for an option that does not exist: {sorted(hinted - set(option_labels))}")
        missing = set(option_labels) - {chosen} - hinted
        if chosen and missing:
            v.soft.append(f"no hint for option(s) {sorted(missing)}")

    return v

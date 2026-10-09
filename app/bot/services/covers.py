"""Cover images for a quiz published to a channel or group.

A channel feed is scrolled past, so the post leads with a picture that says
what the quiz is before a word is read: the subject's own colour, its own
symbols scattered behind the title, and the title itself. Everything is drawn
from the quiz, so a new quiz never reuses another one's picture.
"""

import logging
import random
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

WIDTH, HEIGHT = 1280, 720
FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
BOLD_FONT = FONT_DIR / "DejaVuSans-Bold.ttf"
REGULAR_FONT = FONT_DIR / "DejaVuSans.ttf"

#: Subject keyword -> (background, accent, the marks scattered behind the title).
#: Keyed by keyword so "Ona tili va adabiyoti" and "Ona tili" both land here.
THEMES = {
    "matematika": ("#0B1B3A", "#3B82F6", "∑ √ ∫ π ∞ ≠ ≤ x² a+b ÷ ×"),
    "algebra": ("#0B1B3A", "#3B82F6", "∑ √ ∫ π ∞ ≠ ≤ x² a+b ÷ ×"),
    "geometriya": ("#0B1B3A", "#3B82F6", "∠ △ ◯ π ≅ ∥ ⊥ r² a+b"),
    "fizika": ("#1A1033", "#8B5CF6", "π ∫ Δ λ Ω ≈ ∞ θ v² E=mc²"),
    "kimyo": ("#06241C", "#10B981", "H₂O CO₂ NaCl O₂ → ± H₂SO₄ Fe"),
    "biologiya": ("#06282B", "#14B8A6", "DNA RNA ATP ♀ ♂ O₂ C₆H₁₂O₆ →"),
    "tarix": ("#2B1A06", "#D97706", "MCMXVII XIX XX 1917 1991 § ★ ∴"),
    "geografiya": ("#052A3A", "#06B6D4", "N S E W 41°N 69°E ▲ ≈ °"),
    "ona tili": ("#2E0A16", "#F43F5E", "« » Aa Bb ... ? ! — ;"),
    "adabiyot": ("#2E0A16", "#F43F5E", "« » Aa Bb ... ? ! — ;"),
    "ingliz": ("#121633", "#6366F1", "Aa Bb The ing 's ? ! “Hi”"),
}

#: A subject nobody wrote a theme for still gets a real cover.
FALLBACK_THEME = ("#141A22", "#64748B", "? ! ✓ ★ … ∴ Aa 1 2 3")


def theme_for(subject: str | None):
    normalized = (subject or "").lower()
    return next(
        (value for keyword, value in THEMES.items() if keyword in normalized),
        FALLBACK_THEME,
    )


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


@lru_cache(maxsize=8)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _background(accent: str, dark: str, glyphs: str, seed: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), _rgb(dark))

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        [WIDTH - 420, HEIGHT * 0.5 - 420, WIDTH + 420, HEIGHT * 0.5 + 420],
        fill=(*_rgb(accent), 170),
    )
    image = Image.alpha_composite(
        image.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(150))
    ).convert("RGB")

    marks = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(marks)
    # Seeded by the quiz, so the same quiz always draws the same background and
    # two quizzes in one subject do not look like the same picture twice.
    rng = random.Random(seed)
    for glyph in glyphs.split() * 4:
        font = _font(str(REGULAR_FONT), rng.randint(34, 86))
        draw.text(
            (rng.randint(-20, WIDTH), rng.randint(-20, HEIGHT)),
            glyph,
            font=font,
            fill=(255, 255, 255, rng.randint(18, 42)),
        )
    image = Image.alpha_composite(image.convert("RGBA"), marks).convert("RGB")

    # Grain from the same seeded stream, so one quiz always draws one picture.
    # ``Image.effect_noise`` would be random on every call; a small tile scaled
    # up is both repeatable and much cheaper than a full-size one.
    tile = (WIDTH // 4, HEIGHT // 4)
    grain = Image.frombytes(
        "L", tile, bytes(rng.randrange(26) for _ in range(tile[0] * tile[1]))
    ).resize((WIDTH, HEIGHT), Image.BILINEAR)
    image.paste(Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255)), (0, 0), grain)
    return image


def _wrapped(draw, text: str, font, limit: float, rows: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        probe = f"{line} {word}".strip()
        if draw.textlength(probe, font=font) > limit and line:
            lines.append(line)
            line = word
        else:
            line = probe
    lines.append(line)
    return lines[:rows]


def render_cover(
    subject: str | None,
    title: str,
    question_count: int,
    minutes: int | None,
    seed: int = 0,
) -> bytes:
    """The quiz as a 1280x720 JPEG, ready for ``send_photo``."""
    dark, accent, glyphs = theme_for(subject)
    image = _background(accent, dark, glyphs, seed)

    # The text side is darkened so the title reads over any background.
    shade = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    edge = int(WIDTH * 0.72)
    for x in range(edge):
        shade_draw.line([(x, 0), (x, HEIGHT)], fill=(0, 0, 0, int(150 * (1 - x / edge))))
    image = Image.alpha_composite(image.convert("RGBA"), shade).convert("RGB")

    draw = ImageDraw.Draw(image, "RGBA")
    label_font = _font(str(BOLD_FONT), 34)
    title_font = _font(str(BOLD_FONT), 70)
    meta_font = _font(str(REGULAR_FONT), 34)

    label = (subject or "Test").upper()
    label_width = draw.textlength(label, font=label_font)
    draw.rounded_rectangle([76, 84, 76 + label_width + 36, 142], 29, fill=(*_rgb(accent), 235))
    draw.text((94, 96), label, font=label_font, fill="#0B0B12")

    y = 232
    for row in _wrapped(draw, title, title_font, WIDTH * 0.56, rows=3):
        draw.text((78, y), row, font=title_font, fill="#FFFFFF")
        y += 84

    draw.line([(80, HEIGHT - 148), (80, HEIGHT - 92)], fill=_rgb(accent), width=6)
    draw.text((104, HEIGHT - 142), f"{question_count} savol", font=meta_font, fill="#FFFFFF")
    if minutes:
        draw.text((104, HEIGHT - 100), f"~{minutes} daqiqa", font=meta_font, fill="#C7CBD6")

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def safe_cover(subject, title, question_count, minutes, seed=0) -> bytes | None:
    """A cover is decoration: if drawing fails, the quiz is still published."""
    try:
        return render_cover(subject, title, question_count, minutes, seed)
    except Exception:
        logger.exception("Could not draw a cover for %r", title)
        return None

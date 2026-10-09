"""Cover images for a quiz published to a channel or group.

A channel feed is scrolled past, so the post leads with a picture that says
what the quiz is before a word is read: the subject drawn as its own scene --
an atom, a flask, a globe -- the formulas a student recognises, and the topics
this particular quiz covers. Everything comes from the quiz, so two quizzes
never share a picture, and a subject nobody drew a scene for still gets a
proper cover from the scattered-symbol fallback at the bottom of this file.
"""

import logging
import math
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


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


@lru_cache(maxsize=16)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


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


def _glow(image: Image.Image, center, radius: int, color: str, alpha: int = 150):
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    x, y = center
    ImageDraw.Draw(layer).ellipse(
        [x - radius, y - radius, x + radius, y + radius], fill=(*_rgb(color), alpha)
    )
    return Image.alpha_composite(
        image.convert("RGBA"), layer.filter(ImageFilter.GaussianBlur(radius * 0.55))
    ).convert("RGB")


def _orbit(image: Image.Image, center, radii, angle: int, colour: str, electron=None):
    """One tilted electron path, drawn flat then rotated into place."""
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = center
    rx, ry = radii
    draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=(*_rgb(colour), 190), width=3)
    if electron is not None:
        ex = cx + rx * math.cos(math.radians(electron))
        ey = cy + ry * math.sin(math.radians(electron))
        draw.ellipse([ex - 9, ey - 9, ex + 9, ey + 9], fill=(*_rgb(colour), 255))
    layer = layer.rotate(angle, center=center, resample=Image.BICUBIC)
    return Image.alpha_composite(image.convert("RGBA"), layer).convert("RGB")


def _wave(draw, start: int, end: int, baseline: int, colour: str, amplitude: int = 16):
    draw.line(
        [(x, baseline + amplitude * math.sin((x - start) / 46)) for x in range(start, end, 4)],
        fill=_rgb(colour), width=4, joint="curve",
    )


def _dot_grid(draw, spacing: int = 26, alpha: int = 24) -> None:
    for x in range(spacing, WIDTH, spacing):
        for y in range(spacing, HEIGHT, spacing):
            draw.point((x, y), fill=(255, 255, 255, alpha))


def _chip(draw, position, text, font, palette, padding=(16, 9)):
    x, y = position
    width = draw.textlength(text, font=font)
    draw.rounded_rectangle(
        [x, y, x + width + padding[0] * 2, y + font.size + padding[1] * 2], 10,
        fill=_rgb(palette["card"]), outline=_rgb(palette["edge"]), width=2,
    )
    draw.text((x + padding[0], y + padding[1]), text, font=font, fill="#E8E6F5")


# ---------------------------------------------------------------- pill marks
def _atom_mark(draw, center, colour, radius=9):
    cx, cy = center
    draw.ellipse([cx - radius, cy - radius * 0.45, cx + radius, cy + radius * 0.45],
                 outline=_rgb(colour), width=2)
    draw.ellipse([cx - radius * 0.45, cy - radius, cx + radius * 0.45, cy + radius],
                 outline=_rgb(colour), width=2)
    draw.ellipse([cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5], fill=_rgb(colour))


def _pi_mark(draw, center, colour):
    draw.text((center[0] - 8, center[1] - 14), "π", font=_font(str(BOLD_FONT), 24),
              fill=_rgb(colour))


def _flask_mark(draw, center, colour):
    cx, cy = center
    draw.line([(cx - 4, cy - 9), (cx - 4, cy - 2), (cx - 9, cy + 8), (cx + 9, cy + 8),
               (cx + 4, cy - 2), (cx + 4, cy - 9)], fill=_rgb(colour), width=2)
    draw.line([(cx - 6, cy - 9), (cx + 6, cy - 9)], fill=_rgb(colour), width=2)


def _helix_mark(draw, center, colour):
    cx, cy = center
    for shift in (-4, 4):
        draw.line([(cx + shift * math.cos(t / 3), cy - 9 + t)
                   for t in range(0, 19)], fill=_rgb(colour), width=2)
    for y in (-5, 1, 7):
        draw.line([(cx - 4, cy + y), (cx + 4, cy + y)], fill=_rgb(colour), width=2)


def _column_mark(draw, center, colour):
    cx, cy = center
    draw.line([(cx - 9, cy - 8), (cx + 9, cy - 8)], fill=_rgb(colour), width=2)
    draw.line([(cx - 9, cy + 9), (cx + 9, cy + 9)], fill=_rgb(colour), width=2)
    for x in (-4, 0, 4):
        draw.line([(cx + x, cy - 6), (cx + x, cy + 7)], fill=_rgb(colour), width=2)


def _globe_mark(draw, center, colour):
    cx, cy = center
    draw.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], outline=_rgb(colour), width=2)
    draw.ellipse([cx - 4, cy - 9, cx + 4, cy + 9], outline=_rgb(colour), width=2)
    draw.line([(cx - 9, cy), (cx + 9, cy)], fill=_rgb(colour), width=2)


def _book_mark(draw, center, colour):
    cx, cy = center
    draw.line([(cx, cy - 7), (cx, cy + 8)], fill=_rgb(colour), width=2)
    draw.line([(cx, cy - 7), (cx - 9, cy - 4), (cx - 9, cy + 9), (cx, cy + 8)],
              fill=_rgb(colour), width=2)
    draw.line([(cx, cy - 7), (cx + 9, cy - 4), (cx + 9, cy + 9), (cx, cy + 8)],
              fill=_rgb(colour), width=2)


def _bubble_mark(draw, center, colour):
    cx, cy = center
    draw.rounded_rectangle([cx - 9, cy - 8, cx + 9, cy + 4], 4, outline=_rgb(colour), width=2)
    draw.line([(cx - 3, cy + 4), (cx - 5, cy + 9), (cx + 2, cy + 4)], fill=_rgb(colour), width=2)


def _list_mark(draw, center, colour):
    cx, cy = center
    for offset in (-7, 0, 7):
        draw.line([(cx - 9, cy + offset), (cx + 9, cy + offset)], fill=_rgb(colour), width=2)


def _clock_mark(draw, center, colour):
    cx, cy = center
    draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], outline=_rgb(colour), width=2)
    draw.line([(cx, cy), (cx, cy - 6)], fill=_rgb(colour), width=2)
    draw.line([(cx, cy), (cx + 5, cy + 3)], fill=_rgb(colour), width=2)

# ------------------------------------------------------------------- scenes
#: Every scene is drawn into the same right-hand area, so one layout fits all.
SCENE_BOX = (700, 90, 1230, 620)


def _physics_scene(image, palette):
    centre = (940, 320)
    image = _glow(image, centre, 150, palette["accent"], alpha=70)
    for angle, electron in ((0, 20), (62, 150), (124, 275)):
        image = _orbit(image, centre, (232, 96), angle, palette["soft"], electron)
    image = _glow(image, centre, 46, "#C4B5FD", alpha=220)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse([centre[0] - 26, centre[1] - 26, centre[0] + 26, centre[1] + 26],
                 fill=_rgb("#DDD6FE"))
    draw.ellipse([1168, 300, 1188, 320], fill=_rgb(palette["warm"]))
    _wave(draw, 726, 1186, 592, palette["warm"])
    return image


def _math_scene(image, palette):
    image = _glow(image, (960, 330), 170, palette["accent"], alpha=60)
    draw = ImageDraw.Draw(image, "RGBA")
    left, right, base, top = 740, 1200, 540, 140
    for x in range(left, right, 46):                      # koordinata to'ri
        draw.line([(x, top), (x, base)], fill=(255, 255, 255, 14), width=1)
    for y in range(top, base, 46):
        draw.line([(left, y), (right, y)], fill=(255, 255, 255, 14), width=1)
    draw.line([(left, base), (right, base)], fill=_rgb(palette["soft"]), width=3)
    draw.line([(790, top), (790, base)], fill=_rgb(palette["soft"]), width=3)
    draw.polygon([(right, base), (right - 14, base - 7), (right - 14, base + 7)],
                 fill=_rgb(palette["soft"]))
    draw.polygon([(790, top), (783, top + 14), (797, top + 14)], fill=_rgb(palette["soft"]))

    curve = [(x, 300 + 0.0048 * (x - 1000) ** 2) for x in range(812, 1196, 4)]
    curve = [(x, y) for x, y in curve if y < base - 8]
    draw.line(curve, fill=_rgb(palette["warm"]), width=4, joint="curve")
    for x in (868, 1000, 1132):
        point = next(((px, py) for px, py in curve if abs(px - x) < 3), None)
        if point:
            draw.ellipse([point[0] - 8, point[1] - 8, point[0] + 8, point[1] + 8],
                         fill=_rgb(palette["accent"]))
    return image


def _chemistry_scene(image, palette):
    image = _glow(image, (930, 360), 160, palette["accent"], alpha=70)
    draw = ImageDraw.Draw(image, "RGBA")
    cx, cy = 900, 330
    draw.line([(cx - 22, cy - 120), (cx - 22, cy - 40), (cx - 92, cy + 110),
               (cx + 92, cy + 110), (cx + 22, cy - 40), (cx + 22, cy - 120)],
              fill=_rgb(palette["soft"]), width=4, joint="curve")
    draw.line([(cx - 40, cy - 120), (cx + 40, cy - 120)], fill=_rgb(palette["soft"]), width=5)
    draw.polygon([(cx - 70, cy + 68), (cx + 70, cy + 68), (cx + 92, cy + 110),
                  (cx - 92, cy + 110)], fill=(*_rgb(palette["warm"]), 150))
    for bx, by, br in ((cx - 30, cy + 40, 9), (cx + 14, cy + 18, 7), (cx + 40, cy + 54, 11),
                       (cx - 8, cy - 10, 6)):
        draw.ellipse([bx - br, by - br, bx + br, by + br], outline=_rgb(palette["soft"]), width=2)

    hx, hy, r = 1120, 236, 62                              # benzol halqasi
    points = [(hx + r * math.cos(math.radians(60 * i - 30)),
               hy + r * math.sin(math.radians(60 * i - 30))) for i in range(6)]
    draw.line(points + [points[0]], fill=_rgb(palette["soft"]), width=4, joint="curve")
    draw.ellipse([hx - 30, hy - 30, hx + 30, hy + 30], outline=_rgb(palette["warm"]), width=3)
    return image


def _biology_scene(image, palette):
    image = _glow(image, (980, 330), 165, palette["accent"], alpha=65)
    draw = ImageDraw.Draw(image, "RGBA")
    top, bottom, cx = 130, 560, 1060                       # DNK spirali
    left_strand, right_strand = [], []
    for y in range(top, bottom, 4):
        phase = (y - top) / 58
        left_strand.append((cx + 62 * math.sin(phase), y))
        right_strand.append((cx - 62 * math.sin(phase), y))
    draw.line(left_strand, fill=_rgb(palette["soft"]), width=5, joint="curve")
    draw.line(right_strand, fill=_rgb(palette["warm"]), width=5, joint="curve")
    for index in range(top + 18, bottom, 36):
        phase = (index - top) / 58
        draw.line([(cx + 62 * math.sin(phase), index), (cx - 62 * math.sin(phase), index)],
                  fill=(*_rgb(palette["soft"]), 150), width=3)

    draw.ellipse([756, 262, 916, 422], outline=_rgb(palette["soft"]), width=4)   # hujayra
    draw.ellipse([812, 318, 862, 368], fill=(*_rgb(palette["accent"]), 220))
    for ox, oy in ((790, 300), (880, 390), (870, 300)):
        draw.ellipse([ox - 10, oy - 6, ox + 10, oy + 6], outline=_rgb(palette["warm"]), width=2)
    return image


def _history_scene(image, palette):
    image = _glow(image, (960, 300), 160, palette["accent"], alpha=60)
    draw = ImageDraw.Draw(image, "RGBA")
    cx, top, bottom = 960, 150, 470                        # ustun
    draw.rounded_rectangle([cx - 96, top, cx + 96, top + 26], 6, fill=_rgb(palette["soft"]))
    draw.rounded_rectangle([cx - 80, top + 26, cx + 80, top + 50], 4,
                           fill=(*_rgb(palette["soft"]), 190))
    for offset in (-54, -18, 18, 54):
        draw.rounded_rectangle([cx + offset - 13, top + 54, cx + offset + 13, bottom - 34], 6,
                               fill=(*_rgb(palette["soft"]), 150))
    draw.rounded_rectangle([cx - 88, bottom - 30, cx + 88, bottom], 6, fill=_rgb(palette["soft"]))

    y = 560                                                 # vaqt o'qi
    draw.line([(740, y), (1190, y)], fill=_rgb(palette["warm"]), width=4)
    for index, x in enumerate(range(770, 1180, 100)):
        height = 16 if index % 2 == 0 else 9
        draw.line([(x, y - height), (x, y + height)], fill=_rgb(palette["warm"]), width=3)
    draw.ellipse([962, y - 11, 984, y + 11], fill=_rgb(palette["accent"]))
    return image


def _geography_scene(image, palette):
    centre = (960, 320)
    image = _glow(image, centre, 165, palette["accent"], alpha=70)
    draw = ImageDraw.Draw(image, "RGBA")
    cx, cy, r = centre[0], centre[1], 168
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=_rgb(palette["soft"]), width=4)
    for ry in (52, 108):                                    # parallellar
        draw.ellipse([cx - r, cy - ry, cx + r, cy + ry], outline=(*_rgb(palette["soft"]), 140),
                     width=2)
    draw.line([(cx - r, cy), (cx + r, cy)], fill=(*_rgb(palette["soft"]), 170), width=2)
    for rx in (56, 116):                                    # meridianlar
        draw.ellipse([cx - rx, cy - r, cx + rx, cy + r], outline=(*_rgb(palette["soft"]), 140),
                     width=2)
    draw.line([(cx, cy - r), (cx, cy + r)], fill=(*_rgb(palette["soft"]), 170), width=2)

    px, py = cx + 54, cy - 48                               # belgi
    draw.ellipse([px - 20, py - 20, px + 20, py + 20], fill=_rgb(palette["warm"]))
    draw.polygon([(px - 12, py + 12), (px + 12, py + 12), (px, py + 36)],
                 fill=_rgb(palette["warm"]))
    draw.ellipse([px - 7, py - 7, px + 7, py + 7], fill=_rgb("#0B1620"))
    _wave(draw, 740, 1180, 568, palette["warm"], amplitude=12)
    return image


def _language_scene(image, palette):
    image = _glow(image, (960, 340), 165, palette["accent"], alpha=65)
    draw = ImageDraw.Draw(image, "RGBA")
    cx, cy = 965, 352                                       # ochiq kitob
    draw.polygon([(cx - 8, cy - 104), (cx - 214, cy - 62), (cx - 214, cy + 92), (cx - 8, cy + 56)],
                 fill=(*_rgb(palette["soft"]), 55), outline=_rgb(palette["soft"]))
    draw.polygon([(cx + 8, cy - 104), (cx + 214, cy - 62), (cx + 214, cy + 92), (cx + 8, cy + 56)],
                 fill=(*_rgb(palette["soft"]), 32), outline=_rgb(palette["soft"]))
    draw.line([(cx, cy - 102), (cx, cy + 56)], fill=_rgb(palette["soft"]), width=5)
    for index in range(5):                                  # satrlar
        y = cy - 56 + index * 26
        draw.line([(cx - 190, y + 14), (cx - 32, y)], fill=(*_rgb(palette["soft"]), 110), width=3)
        draw.line([(cx + 32, y), (cx + 190, y + 14)], fill=(*_rgb(palette["soft"]), 110), width=3)
    quote_font = _font(str(BOLD_FONT), 132)
    draw.text((722, 118), "«", font=quote_font, fill=(*_rgb(palette["warm"]), 210))
    draw.text((1126, 430), "»", font=quote_font, fill=(*_rgb(palette["warm"]), 210))
    return image


def _english_scene(image, palette):
    image = _glow(image, (960, 320), 165, palette["accent"], alpha=65)
    draw = ImageDraw.Draw(image, "RGBA")
    big = _font(str(BOLD_FONT), 64)
    draw.rounded_rectangle([744, 150, 1024, 316], 28, fill=(*_rgb(palette["soft"]), 60),
                           outline=_rgb(palette["soft"]), width=4)
    draw.polygon([(800, 316), (788, 364), (856, 316)], fill=_rgb(palette["soft"]))
    draw.text((808, 196), "Aa", font=big, fill="#FFFFFF")

    draw.rounded_rectangle([900, 372, 1176, 528], 28, fill=(*_rgb(palette["warm"]), 70),
                           outline=_rgb(palette["warm"]), width=4)
    draw.polygon([(1120, 528), (1132, 574), (1064, 528)], fill=_rgb(palette["warm"]))
    draw.text((966, 414), "Hi!", font=big, fill="#FFFFFF")
    return image


# ------------------------------------------------------------------ registry
#: Subject keyword -> the scene drawn for it. Keyed by keyword so "Ona tili va
#: adabiyoti" and a bare "Adabiyot" land on the same page.
SCENES = {
    "fizika": {
        "label": "FIZIKA", "mark": _atom_mark, "scene": _physics_scene,
        "ink": "#0D0A1A", "accent": "#8B5CF6", "soft": "#A78BFA", "warm": "#FBBF24",
        "card": "#171229", "edge": "#2A2347", "pill": "#1A1333", "pill_edge": "#4C1D95",
        "chips": ("F = ma", "E = mc²", "p = mv", "U = IR"),
    },
    "matematika": {
        "label": "MATEMATIKA", "mark": _pi_mark, "scene": _math_scene,
        "ink": "#080F20", "accent": "#3B82F6", "soft": "#93C5FD", "warm": "#FBBF24",
        "card": "#111A2E", "edge": "#1F2E4A", "pill": "#0E1A33", "pill_edge": "#1D4ED8",
        "chips": ("a² + b² = c²", "∫ f(x)dx", "(a+b)²", "π ≈ 3.14"),
    },
    "kimyo": {
        "label": "KIMYO", "mark": _flask_mark, "scene": _chemistry_scene,
        "ink": "#04160F", "accent": "#10B981", "soft": "#6EE7B7", "warm": "#FBBF24",
        "card": "#0C2119", "edge": "#17392B", "pill": "#0A1F17", "pill_edge": "#047857",
        "chips": ("H₂O", "CO₂ + H₂O", "NaCl", "pH = 7"),
    },
    "biologiya": {
        "label": "BIOLOGIYA", "mark": _helix_mark, "scene": _biology_scene,
        "ink": "#041818", "accent": "#14B8A6", "soft": "#5EEAD4", "warm": "#FDE047",
        "card": "#0A2322", "edge": "#15403D", "pill": "#082020", "pill_edge": "#0F766E",
        "chips": ("DNA", "ATP", "C₆H₁₂O₆", "O₂ → CO₂"),
    },
    "tarix": {
        "label": "TARIX", "mark": _column_mark, "scene": _history_scene,
        "ink": "#17100A", "accent": "#D97706", "soft": "#FCD34D", "warm": "#F97316",
        "card": "#241910", "edge": "#45301B", "pill": "#201609", "pill_edge": "#B45309",
        "chips": ("1917", "1991", "XIX asr", "MCMXVII"),
    },
    "geografiya": {
        "label": "GEOGRAFIYA", "mark": _globe_mark, "scene": _geography_scene,
        "ink": "#05141D", "accent": "#06B6D4", "soft": "#67E8F9", "warm": "#FBBF24",
        "card": "#0B2230", "edge": "#164150", "pill": "#08202C", "pill_edge": "#0E7490",
        "chips": ("41°N", "69°E", "N · S · E · W", "1:100 000"),
    },
    "ona tili": {
        "label": "ONA TILI", "mark": _book_mark, "scene": _language_scene,
        "ink": "#1A0710", "accent": "#F43F5E", "soft": "#FDA4AF", "warm": "#FBBF24",
        "card": "#28101A", "edge": "#4A1F2C", "pill": "#230C16", "pill_edge": "#9F1239",
        "chips": ("Ot", "Fe'l", "Sifat", "« ... »"),
    },
    "ingliz": {
        "label": "INGLIZ TILI", "mark": _bubble_mark, "scene": _english_scene,
        "ink": "#0A0D1F", "accent": "#6366F1", "soft": "#A5B4FC", "warm": "#FBBF24",
        "card": "#141833", "edge": "#262C52", "pill": "#111530", "pill_edge": "#4338CA",
        "chips": ("Present Perfect", "-ing", "'s", "\u201cHello\u201d"),
        "chips_at": ((744, 104), (1118, 86), (744, 596), (1016, 596)),
    },
}
SCENES["algebra"] = SCENES["geometriya"] = SCENES["matematika"]
SCENES["adabiyot"] = SCENES["ona tili"]

CHIP_SLOTS = ((762, 128), (1046, 70), (752, 452), (1060, 436))


def scene_for(subject: str | None):
    normalized = (subject or "").lower()
    return next((value for keyword, value in SCENES.items() if keyword in normalized), None)


def _scene_cover(palette, title, question_count, minutes, topics, seed) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), _rgb(palette["ink"]))
    draw = ImageDraw.Draw(image, "RGBA")
    _dot_grid(draw)
    draw.line([(24, 0), (24, HEIGHT)], fill=(255, 255, 255, 22), width=2)
    draw.line([(WIDTH - 24, 0), (WIDTH - 24, HEIGHT)], fill=(255, 255, 255, 22), width=2)

    image = palette["scene"](image, palette)
    draw = ImageDraw.Draw(image, "RGBA")

    chip_font = _font(str(REGULAR_FONT), 22)
    for text, position in zip(palette["chips"], palette.get("chips_at", CHIP_SLOTS)):
        _chip(draw, position, text, chip_font, palette)

    label_font = _font(str(BOLD_FONT), 21)
    label = palette["label"]
    width = draw.textlength(label, font=label_font)
    draw.rounded_rectangle([76, 74, 76 + width + 62, 120], 23,
                           fill=_rgb(palette["pill"]), outline=_rgb(palette["pill_edge"]), width=2)
    palette["mark"](draw, (100, 97), palette["soft"])
    draw.text((118, 85), label, font=label_font, fill=_rgb(palette["soft"]))

    title_font = _font(str(BOLD_FONT), 66)
    y = 172
    for row in _wrapped(draw, title, title_font, 560, rows=2):
        draw.text((78, y), row, font=title_font, fill="#FFFFFF")
        y += 76

    tail_font = _font(str(BOLD_FONT), 40)
    draw.text((80, y + 16), "bo'yicha", font=tail_font, fill=_rgb(palette["soft"]))
    tail_x = 80 + draw.textlength("bo'yicha", font=tail_font) + 22
    badge_width = draw.textlength("test", font=tail_font)
    draw.rounded_rectangle([tail_x, y + 8, tail_x + badge_width + 36, y + 70], 18,
                           fill=_rgb(palette["warm"]))
    draw.text((tail_x + 18, y + 18), "test", font=tail_font, fill=_rgb(palette["ink"]))

    number_font = _font(str(BOLD_FONT), 32)
    unit_font = _font(str(REGULAR_FONT), 17)
    cards = [(_list_mark, str(question_count), "savol")]
    if minutes:
        cards.append((_clock_mark, f"~{minutes}", "daqiqa"))
    for index, (mark, value, unit) in enumerate(cards):
        x = 78 + index * 168
        draw.rounded_rectangle([x, 512, x + 150, 598], 20,
                               fill=_rgb(palette["card"]), outline=_rgb(palette["edge"]), width=2)
        draw.rounded_rectangle([x + 16, 534, x + 58, 576], 12, fill=_rgb(palette["pill"]))
        mark(draw, (x + 37, 555), palette["soft"])
        draw.text((x + 72, 528), value, font=number_font, fill="#FFFFFF")
        draw.text((x + 73, 566), unit, font=unit_font, fill="#8B8AA3")

    if topics:
        draw.line([(78, 646), (WIDTH - 78, 646)], fill=(255, 255, 255, 26), width=2)
        topic_font = _font(str(BOLD_FONT), 17)
        x = 78
        for index, topic in enumerate(list(topics)[:5]):
            if index:
                draw.text((x, 672), "•", font=topic_font, fill=_rgb(palette["accent"]))
                x += 26
            draw.text((x, 672), topic, font=topic_font, fill="#8B8AA3")
            x += draw.textlength(topic, font=topic_font) + 26
            if x > WIDTH - 180:
                break
    return image


# --------------------------------------------------- fallback for a new subject
#: Subject keyword -> (background, accent, marks scattered behind the title).
THEMES = {
    "matematika": ("#0B1B3A", "#3B82F6", "∑ √ ∫ π ∞ ≠ ≤ x² a+b ÷ ×"),
    "fizika": ("#1A1033", "#8B5CF6", "π ∫ Δ λ Ω ≈ ∞ θ v² E=mc²"),
    "kimyo": ("#06241C", "#10B981", "H₂O CO₂ NaCl O₂ → ± H₂SO₄ Fe"),
    "biologiya": ("#06282B", "#14B8A6", "DNA RNA ATP ♀ ♂ O₂ C₆H₁₂O₆ →"),
    "tarix": ("#2B1A06", "#D97706", "MCMXVII XIX XX 1917 1991 § ★ ∴"),
    "geografiya": ("#052A3A", "#06B6D4", "N S E W 41°N 69°E ▲ ≈ °"),
    "ona tili": ("#2E0A16", "#F43F5E", "« » Aa Bb ... ? ! — ;"),
    "adabiyot": ("#2E0A16", "#F43F5E", "« » Aa Bb ... ? ! — ;"),
    "ingliz": ("#121633", "#6366F1", "Aa Bb The ing 's ? ! \u201cHi\u201d"),
}

#: A subject nobody wrote a theme for still gets a real cover.
FALLBACK_THEME = ("#141A22", "#64748B", "? ! ✓ ★ … ∴ Aa 1 2 3")


def theme_for(subject: str | None):
    normalized = (subject or "").lower()
    return next(
        (value for keyword, value in THEMES.items() if keyword in normalized),
        FALLBACK_THEME,
    )


def _glyph_background(accent: str, dark: str, glyphs: str, seed: int) -> Image.Image:
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
    rng = random.Random(seed)
    for glyph in glyphs.split() * 4:
        font = _font(str(REGULAR_FONT), rng.randint(34, 86))
        draw.text((rng.randint(-20, WIDTH), rng.randint(-20, HEIGHT)), glyph,
                  font=font, fill=(255, 255, 255, rng.randint(18, 42)))
    image = Image.alpha_composite(image.convert("RGBA"), marks).convert("RGB")

    tile = (WIDTH // 4, HEIGHT // 4)
    grain = Image.frombytes(
        "L", tile, bytes(rng.randrange(26) for _ in range(tile[0] * tile[1]))
    ).resize((WIDTH, HEIGHT), Image.BILINEAR)
    image.paste(Image.new("RGB", (WIDTH, HEIGHT), (255, 255, 255)), (0, 0), grain)
    return image


def _glyph_cover(subject, title, question_count, minutes, seed) -> Image.Image:
    dark, accent, glyphs = theme_for(subject)
    image = _glyph_background(accent, dark, glyphs, seed)

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
    return image


def render_cover(subject, title, question_count, minutes, seed=0, topics=()) -> bytes:
    """The quiz as a 1280x720 JPEG, ready for ``send_photo``."""
    palette = scene_for(subject)
    image = (
        _scene_cover(palette, title, question_count, minutes, topics, seed)
        if palette
        else _glyph_cover(subject, title, question_count, minutes, seed)
    )
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88, optimize=True)
    return buffer.getvalue()


def safe_cover(subject, title, question_count, minutes, seed=0, topics=()) -> bytes | None:
    """A cover is decoration: if drawing fails, the quiz is still published."""
    try:
        return render_cover(subject, title, question_count, minutes, seed, topics)
    except Exception:
        logger.exception("Could not draw a cover for %r", title)
        return None

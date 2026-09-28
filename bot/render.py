"""Card renderer (1080x1350, Pillow). Text + shapes only, no stock photos — same approach as
the K-beauty bot, so there's never a copyright question about a hotel or attraction photo.

This is a working first pass so `python -m bot demo` produces real cards for every series today.
The bespoke per-series layouts (도시 101 / 동네 비교 / 호텔 픽 / 코스 / TOP 10 cards from the
기획서) land in a later pass — see 진행 순서 step 7. For now every kind shares one clean template:
a cover slide + up to 4 content slides, each with a heading and short bullets.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
W, H = 1080, 1350
PAD = 84

NAVY = "#15233F"
CREAM = "#F6EFE3"
TEAL = "#1F8A84"
RED = "#E0483A"
INK_ON_CREAM = "#15233F"

KIND_LABEL = {
    "city101": "CITY 101", "area": "WHERE TO STAY", "hotel": "HOTEL PICKS",
    "transport": "GETTING AROUND", "route": "ROUTE", "season": "SEASON GUIDE",
    "words": "SPEAK LIKE A LOCAL", "weekly": "TRENDING THIS WEEK", "recap": "LAST MONTH",
}
KIND_ACCENT = {
    "city101": TEAL, "area": RED, "hotel": RED, "transport": TEAL,
    "route": RED, "season": TEAL, "words": RED, "weekly": TEAL, "recap": RED,
}


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _base(bg: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), bg)
    return im, ImageDraw.Draw(im)


def _footer(d: ImageDraw.ImageDraw, brand: str, number: int, accent: str, ink: str) -> None:
    f = _font("DMSans-SemiBold.ttf", 30)
    d.text((PAD, H - 74), brand.upper(), font=f, fill=ink)
    tag = f"No.{number:03d}"
    tw = d.textlength(tag, font=f)
    d.text((W - PAD - tw, H - 74), tag, font=f, fill=accent)


def _cover(topic, number: int, brand: str) -> Image.Image:
    accent = KIND_ACCENT.get(topic.kind, TEAL)
    im, d = _base(NAVY)
    label = KIND_LABEL.get(topic.kind, topic.kind.upper())
    d.text((PAD, 110), label, font=_font("DMSans-SemiBold.ttf", 34), fill=accent)
    d.line((PAD, 160, PAD + 90, 160), fill=accent, width=6)
    title_font = _font("DMSerifDisplay-Regular.ttf", 84 if len(topic.title) < 22 else 64)
    lines = _wrap(d, topic.title, title_font, W - PAD * 2)
    y = 420 - (len(lines) - 1) * 48
    for line in lines:
        d.text((PAD, y), line, font=title_font, fill=CREAM)
        y += 96
    _footer(d, brand, number, accent, CREAM)
    return im


def _content_slide(heading: str, body_lines: list[str], number: int, brand: str, accent: str,
                    bullet: bool = True) -> Image.Image:
    im, d = _base(CREAM)
    d.text((PAD, 96), heading.upper(), font=_font("DMSans-SemiBold.ttf", 32), fill=accent)
    d.line((PAD, 144, PAD + 90, 144), fill=accent, width=5)
    body_font = _font("DMSans-Regular.ttf", 38)
    y = 210
    for raw in body_lines:
        prefix = "•  " if bullet else ""
        wrapped = _wrap(d, (prefix + raw), body_font, W - PAD * 2)
        for i, line in enumerate(wrapped):
            indent = PAD if i == 0 else PAD + 30
            d.text((indent, y), line, font=body_font, fill=INK_ON_CREAM)
            y += 50
        y += 26
        if y > H - 160:
            break
    _footer(d, brand, number, accent, INK_ON_CREAM)
    return im


# ---------------------------------------------------------------------------
# per-kind slide content: [(heading, [body lines], bullet?)]
# ---------------------------------------------------------------------------
def _slides_for(topic) -> list[tuple[str, list[str], bool]]:
    d = topic.data
    k = topic.kind
    if k == "city101":
        from .sources.agoda import hotels_for
        hotels = hotels_for(d["key"], d)
        return [
            ("Why go", [d.get("why", "")], False),
            ("When to go", [d.get("when", "")], False),
            ("Getting there", [d.get("getting_there", "")], False),
            ("Do this", d.get("things", []), True),
            ("Where to stay", [f"{h['tier'].title()}: {h['name']}" for h in hotels], True),
        ]
    if k == "hotel":
        lines = [f"{h['tier'].title()} — {h['name']} · {h.get('note', '')}" for h in d.get("example_hotels", [])]
        return [("Where to stay", lines or ["Example picks coming soon."], True)]
    if k == "area":
        lines = [f"{p['name']} — {p.get('note', '')}" for p in d.get("picks", [])]
        return [("Neighborhoods compared", lines, True)]
    if k == "transport":
        return [
            ("What it covers", [d.get("covers", "")], False),
            ("Worth it?", [d.get("worth_it", "")], False),
        ]
    if k == "route":
        return [
            ("The route", [f"{d.get('days', '?')} days"], False),
            ("Stop by stop", d.get("stops", []), True),
        ]
    if k == "season":
        return [
            ("When", [d.get("months", "")], False),
            ("Know this", [d.get("note", "")], False),
        ]
    if k == "words":
        lines = [f"{p['local']} ({p['romanized']}) — {p['meaning']}" for p in d.get("phrases", [])]
        return [("Phrases", lines, True)]
    return [("", [str(d)], False)]


def render_topic(topic, number: int, cfg, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    brand = cfg.brand_name
    accent = KIND_ACCENT.get(topic.kind, TEAL)
    paths = [out_dir / "1.jpg"]
    _cover(topic, number, brand).save(paths[0], quality=92)
    i = 2
    for heading, lines, bullet in _slides_for(topic):
        if not any(str(x).strip() for x in lines):
            continue
        p = out_dir / f"{i}.jpg"
        _content_slide(heading, lines, number, brand, accent, bullet=bullet).save(p, quality=92)
        paths.append(p)
        i += 1
    return paths


def render_pin(topic, number: int, cfg, target: Path) -> None:
    """A single 2:3 Pinterest image (reuse the cover art)."""
    im = _cover(topic, number, cfg.brand_name)
    pin = im.resize((1000, 1500))
    target.parent.mkdir(parents=True, exist_ok=True)
    pin.save(target, quality=92)


def contact_sheet(image_paths: list[Path], out_path: Path, cols: int = 5) -> Path:
    """A small grid of every slide made today, for the workflow's preview artifact."""
    if not image_paths:
        return out_path
    thumb_w = 220
    ims = [Image.open(p) for p in image_paths]
    thumb_h = int(thumb_w * ims[0].height / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * thumb_h), "white")
    for i, im in enumerate(ims):
        t = im.resize((thumb_w, thumb_h))
        sheet.paste(t, ((i % cols) * thumb_w, (i // cols) * thumb_h))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path

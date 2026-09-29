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


def _footer(d: ImageDraw.ImageDraw, brand: str, number: int, accent: str, ink: str, page: str = "") -> None:
    f = _font("DMSans-SemiBold.ttf", 30)
    d.text((PAD, H - 84), brand.upper(), font=f, fill=ink)
    tag = f"No.{number:03d}" + (f"  ·  {page}" if page else "")
    tw = d.textlength(tag, font=f)
    d.text((W - PAD - tw, H - 84), tag, font=f, fill=accent)


def _route_motif(d: ImageDraw.ImageDraw, x: int, y: int, w: int, ink: str) -> None:
    """Two dots joined by a dotted arc — the logo's route motif."""
    h = int(w * 0.42)
    step, dash = 16, 8
    a = 180
    while a < 360:
        d.arc((x, y - h, x + w, y + h), a, min(a + dash, 360), fill=ink, width=8)
        a += step
    d.ellipse((x - 26, y - 26, x + 26, y + 26), fill=TEAL)
    d.ellipse((x + w - 26, y - 26, x + w + 26, y + 26), fill=RED)


def _subtitle(topic) -> str:
    d = topic.data
    if topic.kind in ("city101", "hotel"):
        return {"Korea": "SOUTH KOREA", "Japan": "JAPAN"}.get(d.get("country", ""), d.get("country", "").upper())
    if topic.kind == "route":
        return f"{d.get('days', '')} DAYS".strip()
    if topic.kind == "transport":
        return d.get("country", "").upper()
    if topic.kind == "words":
        return d.get("language", "").upper()
    return ""


def _cover(topic, number: int, brand: str, total: int = 0) -> Image.Image:
    accent = KIND_ACCENT.get(topic.kind, TEAL)
    im, d = _base(NAVY)
    label = KIND_LABEL.get(topic.kind, topic.kind.upper())
    d.text((PAD, 120), label, font=_font("DMSans-SemiBold.ttf", 40), fill=accent)
    d.line((PAD, 178, PAD + 110, 178), fill=accent, width=7)
    sub = _subtitle(topic)
    for size in (190, 160, 130, 108, 92, 80):
        title_font = _font("DMSerifDisplay-Regular.ttf", size)
        lines = _wrap(d, topic.title, title_font, W - PAD * 2)
        if len(lines) * size * 1.08 <= 560:
            break
    line_h = int(size * 1.08)
    y = 330
    for line in lines:
        d.text((PAD, y), line, font=title_font, fill=CREAM)
        y += line_h
    if sub:
        d.text((PAD, y + 26), sub, font=_font("DMSans-SemiBold.ttf", 44), fill=accent)
    _route_motif(d, PAD + 30, 1010, W - PAD * 2 - 60, CREAM)
    d.text((PAD, H - 250), "Swipe  \u2192", font=_font("DMSans-Medium.ttf", 38), fill=CREAM)
    _footer(d, brand, number, accent, CREAM)
    return im


def _split_label(raw: str) -> tuple[str, str]:
    for sep in (": ", " \u2014 "):
        if sep in raw:
            head, tail = raw.split(sep, 1)
            if len(head) <= 16 and len(head.split()) <= 2:
                return head, tail
    return "", raw


def _layout(d, items: list[str], bullet: bool, avail: int):
    """Largest font size (<= 54) at which every item fits in `avail` px of height."""
    for size in ((54, 50, 46, 42, 38, 34) if bullet else (72, 64, 58, 54, 50, 46, 42, 38, 34)):
        font = _font("DMSans-Regular.ttf", size)
        bold = _font("DMSans-Bold.ttf", int(size * 0.62))
        indent = 96 if bullet else 0
        rows, total = [], 0
        for raw in items:
            label, text = _split_label(raw) if bullet else ("", raw)
            lines = _wrap(d, text, font, W - PAD * 2 - indent)
            h = len(lines) * int(size * 1.34) + (int(size * 0.7) if label else 0)
            rows.append((label, lines, h))
            total += h + int(size * 0.7)
        if total <= avail:
            return size, font, bold, rows
    return size, font, bold, rows


def _content_slide(heading: str, body_lines: list[str], number: int, brand: str, accent: str,
                    bullet: bool = True, page: str = "") -> Image.Image:
    im, d = _base(CREAM)
    d.text((PAD, 110), heading.upper(), font=_font("DMSans-SemiBold.ttf", 40), fill=accent)
    d.line((PAD, 168, PAD + 110, 168), fill=accent, width=7)
    items = [str(x) for x in body_lines if str(x).strip()]
    size, font, bold, rows = _layout(d, items, bullet, H - 250 - 250)
    y = 250
    for n, (label, lines, h) in enumerate(rows, start=1):
        x = PAD
        if bullet:
            cy = y + int(size * 0.62)
            d.ellipse((PAD, cy - 30, PAD + 60, cy + 30), fill=accent)
            d.text((PAD + 30, cy), str(n), font=_font("DMSans-Bold.ttf", 34), fill=CREAM, anchor="mm")
            x = PAD + 96
        ty = y
        if label:
            d.text((x, ty), label.upper(), font=bold, fill=accent)
            ty += int(size * 0.7)
        for line in lines:
            d.text((x, ty), line, font=font, fill=INK_ON_CREAM)
            ty += int(size * 1.34)
        y += h + int(size * 0.7)
    _footer(d, brand, number, accent, INK_ON_CREAM, page)
    return im


def _cta_slide(topic, number: int, cfg, accent: str, page: str) -> Image.Image:
    im, d = _base(NAVY)
    d.text((PAD, 120), "SAVE THIS FOR YOUR TRIP", font=_font("DMSans-SemiBold.ttf", 40), fill=accent)
    d.line((PAD, 178, PAD + 110, 178), fill=accent, width=7)
    big = _font("DMSerifDisplay-Regular.ttf", 104)
    y = 360
    for line in ("Full guide,", "sources and", "booking links"):
        d.text((PAD, y), line, font=big, fill=CREAM)
        y += 122
    d.text((PAD, y + 40), "\u2192  link in our bio", font=_font("DMSans-SemiBold.ttf", 52), fill=accent)
    d.text((PAD, y + 130), f"@{cfg.handle}", font=_font("DMSans-Medium.ttf", 44), fill=CREAM)
    _footer(d, cfg.brand_name, number, accent, CREAM, page)
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
    slides = [(h, l, b) for h, l, b in _slides_for(topic) if any(str(x).strip() for x in l)]
    total = len(slides) + 2  # cover + content + closing
    paths = []
    p = out_dir / "1.jpg"
    _cover(topic, number, brand).save(p, quality=93)
    paths.append(p)
    for i, (heading, lines, bullet) in enumerate(slides, start=2):
        p = out_dir / f"{i}.jpg"
        _content_slide(heading, lines, number, brand, accent, bullet=bullet, page=f"{i}/{total}").save(p, quality=93)
        paths.append(p)
    p = out_dir / f"{total}.jpg"
    _cta_slide(topic, number, cfg, accent, f"{total}/{total}").save(p, quality=93)
    paths.append(p)
    return paths


def render_pin(topic, number: int, cfg, target: Path) -> None:
    """A single 2:3 Pinterest image (reuse the cover art)."""
    im = _cover(topic, number, cfg.brand_name)
    pin = Image.new("RGB", (W, int(W * 1.5)), NAVY)
    pin.paste(im, (0, (pin.height - H) // 2))
    pin = pin.resize((1000, 1500))
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

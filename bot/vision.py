"""Asks a vision model whether a candidate cover photo is usable. It never writes any post text —
it only says yes/no about a photo that already came from a licensed source, so the "no invented
facts" rule for captions and cards still holds.

Provider: Google Gemini (free tier is plenty for a handful of photos a day). The key is the
GEMINI_API_KEY secret; the model name is in config.toml [vision] so it can be changed when Google
retires a model. Without a key the caller falls back to the title-word ranking in kto_photos.py.
"""
from __future__ import annotations

import base64
import io
import json

from PIL import Image

from .util import scrub

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROMPT = (
    "This photo may become the cover of a travel post about {place} ({city}, South Korea). "
    "Answer with JSON only: "
    '{{"shows_place": true/false (does it plausibly show or represent {place}, not some other place), '
    '"identifiable_faces": true/false (any person\'s face clearly recognizable), '
    '"crowd": true/false (many people dominate the picture), '
    '"prominent_text_or_logos": true/false, '
    '"quality": 1-5 (sharp, well composed, good as a background under text)}}'
)


def _jpeg_b64(im: Image.Image, max_side: int = 768) -> str:
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def judge(im: Image.Image, place: str, city: str, key: str, model: str, session=None) -> dict | None:
    """The model's verdict as a dict, or None if the call failed."""
    import requests
    session = session or requests
    body = {
        "contents": [{"parts": [
            {"text": PROMPT.format(place=place, city=city)},
            {"inline_data": {"mime_type": "image/jpeg", "data": _jpeg_b64(im)}},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    try:
        r = session.post(ENDPOINT.format(model=model), json=body, timeout=60,
                         headers={"x-goog-api-key": key})   # header, not ?key=, so it never lands in a URL
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as exc:
        raise RuntimeError(scrub(str(exc), key)) from None


def acceptable(v: dict) -> bool:
    return bool(v.get("shows_place")) and not v.get("identifiable_faces") and not v.get("crowd") \
        and int(v.get("quality", 0) or 0) >= 3

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


FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.8-flash")
_working: dict[str, str] = {}      # key-independent cache: configured model -> the one that answered


def judge(im: Image.Image, place: str, city: str, key: str, model: str, session=None) -> dict | None:
    """The model's verdict as a dict. If Google has retired the configured model (404), the fallbacks
    are tried in order and the one that works is remembered for the rest of the run."""
    last = None
    for m in dict.fromkeys([_working.get(model, model), model, *FALLBACK_MODELS]):
        try:
            verdict = _judge_with(im, place, city, key, m, session)
            _working[model] = m
            return verdict
        except _ModelGone as exc:
            last = exc
    raise RuntimeError(str(last))


class _ModelGone(Exception):
    pass


def _judge_with(im: Image.Image, place: str, city: str, key: str, model: str, session=None) -> dict:
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
        if getattr(r, "status_code", 200) == 404:
            raise _ModelGone(f"model {model} not found")
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except _ModelGone:
        raise
    except Exception as exc:
        raise RuntimeError(scrub(str(exc), key)) from None


def acceptable(v: dict) -> bool:
    """Faces and crowds are fine (the photos are already published under KOGL Type 1);
    what matters is that it shows the right place and looks good."""
    return bool(v.get("shows_place")) and int(v.get("quality", 0) or 0) >= 3

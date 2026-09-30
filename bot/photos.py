"""Optional cover photos. content/photos.toml lists them, photos/ holds the files.
A topic with no photo entry (or a missing file) simply renders the plain navy cover."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PHOTOS_DIR = ROOT / "photos"
AUTO_PATH = ROOT / "data" / "photos_auto.json"   # written by bot/sources/kto_photos.py
ALLOWED_LICENSES = ("unsplash", "kogl-1", "own", "cc0", "cc-by", "pexels")


def load_photos(path: Path | None = None) -> dict[str, dict]:
    """Hand-made content/photos.toml entries, over the automatic picks in data/photos_auto.json."""
    table: dict[str, dict] = {}
    if AUTO_PATH.exists():
        try:
            table.update(json.loads(AUTO_PATH.read_text()))
        except Exception:
            pass
    path = path or ROOT / "content" / "photos.toml"
    if path.exists():
        try:
            with open(path, "rb") as fh:
                entries = tomllib.load(fh).get("photo", [])
            table.update({e["key"]: e for e in entries if e.get("key") and e.get("file")})
        except Exception:
            pass
    return table


def photo_for(topic, photos_dir: Path | None = None, table: dict | None = None) -> dict | None:
    """The photo entry for this topic (with 'path' added), or None."""
    table = load_photos() if table is None else table
    key = topic.data.get("key")
    entry = table.get(key)
    if not entry:
        return None
    p = (photos_dir or PHOTOS_DIR) / entry["file"]
    if not p.exists():
        return None
    return {**entry, "path": p}


def cover_image(path: Path, size: tuple[int, int]) -> Image.Image:
    """Center-crop to fill `size` (no stretching)."""
    im = Image.open(path).convert("RGB")
    w, h = size
    scale = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))

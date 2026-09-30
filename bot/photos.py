"""Optional cover photos. content/photos.toml lists them, photos/ holds the files.
A topic with no photo entry (or a missing file) simply renders the plain navy cover."""
from __future__ import annotations

import tomllib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PHOTOS_DIR = ROOT / "photos"
ALLOWED_LICENSES = ("unsplash", "kogl-1", "own", "cc0", "cc-by", "pexels")


def load_photos(path: Path | None = None) -> dict[str, dict]:
    path = path or ROOT / "content" / "photos.toml"
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as fh:
            entries = tomllib.load(fh).get("photo", [])
    except Exception:
        return {}
    return {e["key"]: e for e in entries if e.get("key") and e.get("file")}


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

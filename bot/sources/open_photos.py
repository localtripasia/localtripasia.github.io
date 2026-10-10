"""Openly licensed photos for places outside Korea (Japan), from two sources:

* Wikimedia Commons (no key): only CC0, public domain and CC BY (credit required). Share-alike (BY-SA),
  non-commercial and no-derivatives licenses are skipped, since the cards edit the photo (crop + text).
  Wikimedia asks API clients for a descriptive User-Agent, which USER_AGENT is.
* Pexels (PEXELS_API_KEY, free): Pexels license allows commercial use and editing; credit is optional but
  given. Used first when the key is set because its photos are usually sharper.

Candidates come back shaped like the Korea Tourism items (galTitle / galWebImageUrl / galPhotographer /
galContentId) plus _credit / _license / _source, so bot/sources/kto_photos.py vets and saves them with the
same code (size check, Gemini "is this really the place" check, one photo per kind of subject).
"""
from __future__ import annotations

import html
import re

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
PEXELS_API = "https://api.pexels.com/v1/search"
USER_AGENT = "LocalTripBot/1.0 (https://localtripasia.github.io; travel guide, contact via site)"
OK_LICENSES = ("cc0", "public domain", "pd", "cc by 1.0", "cc by 2.0", "cc by 2.5", "cc by 3.0", "cc by 4.0")
BAD_WORDS = ("sa", "nc", "nd")           # cc by-sa / by-nc / by-nd
EXTRA_WORDS = ("street", "food", "night", "market")


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value or ""))).strip()


def _latin(name: str, fallback: str) -> str:
    """The card font has no CJK/Hangul glyphs, so a non-Latin name falls back to the site name."""
    ok = name and all(ord(c) < 0x250 for c in name) and "http" not in name.lower() and "/" not in name
    return name if ok else fallback


def license_ok(short: str) -> bool:
    s = (short or "").lower().replace("-", " ").strip()
    if not s:
        return False
    if s.startswith("cc by"):
        parts = s.split()
        if any(p in BAD_WORDS for p in parts[2:]):
            return False
    return any(s == ok or s.startswith(ok) for ok in OK_LICENSES) and "nc" not in s.split()


def commons_search(query: str, session, limit: int = 30) -> list[dict]:
    params = {"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
              "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
              "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1600}
    r = session.get(COMMONS_API, params=params, headers={"User-Agent": USER_AGENT}, timeout=(20, 40))
    r.raise_for_status()
    out = []
    for page in ((r.json().get("query") or {}).get("pages") or {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        short = (meta.get("LicenseShortName") or {}).get("value", "")
        if info.get("mime") != "image/jpeg" or not license_ok(short):
            continue
        if min(info.get("width", 0), info.get("height", 0)) < 800:
            continue
        who = _latin(_text((meta.get("Artist") or {}).get("value", "")), "Wikimedia Commons contributor")
        if len(who) > 40:
            who = who[:37].rstrip() + "..."
        title = _text(page.get("title", "")).removeprefix("File:").rsplit(".", 1)[0]
        out.append({"galTitle": title, "galWebImageUrl": info.get("thumburl") or info.get("url"),
                    "galPhotographer": who, "galContentId": f"commons-{page.get('pageid')}",
                    "_credit": f"Photo: {who} / Wikimedia Commons ({short})", "_license": "cc-by" if "by" in short.lower() else "cc0",
                    "_source": info.get("descriptionurl", "https://commons.wikimedia.org/")})
    return out


def pexels_search(query: str, key: str, session, limit: int = 30) -> list[dict]:
    r = session.get(PEXELS_API, params={"query": query, "per_page": limit}, headers={"Authorization": key},
                    timeout=(20, 40))
    r.raise_for_status()
    out = []
    for p in r.json().get("photos", []):
        src = p.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url or min(p.get("width", 0), p.get("height", 0)) < 800:
            continue
        who = _latin((p.get("photographer") or "").strip(), "Pexels photographer")
        out.append({"galTitle": p.get("alt") or query, "galWebImageUrl": url, "galPhotographer": who,
                    "galContentId": f"pexels-{p.get('id')}", "_credit": f"Photo: {who} / Pexels",
                    "_license": "pexels", "_source": p.get("url", "https://www.pexels.com/")})
    return out


def find_candidates(data: dict, cfg, session=None, diverse: bool = False, cap: int = 80) -> list[dict]:
    """Pexels and Commons results for the place's English search words, interleaved and de-duplicated."""
    import requests
    session = session or requests
    name = data.get("title") or data.get("name") or ""
    city = str(data.get("city") or "").replace("-", " ")
    base = data.get("en") or (name if not city or city.lower() in name.lower() else f"{name} {city}").strip()
    queries = [base] + ([f"{base} {w}" for w in EXTRA_WORDS] if diverse else [])
    pools: list[list[dict]] = []
    for q in queries:
        for fn in (lambda: pexels_search(q, cfg.pexels_key, session) if cfg.pexels_key else [],
                   lambda: commons_search(q, session)):
            try:
                pools.append(fn())
            except Exception:
                continue
    merged, seen = [], set()
    for i in range(max((len(p) for p in pools), default=0)):
        for pool in pools:
            if i < len(pool) and pool[i]["galContentId"] not in seen:
                seen.add(pool[i]["galContentId"])
                merged.append(pool[i])
    return merged[:cap]

"""Cover photos from the Korea Tourism Organization's photo API (한국관광공사_관광사진 정보_GW).
Every photo there is under 공공누리 Type 1 (free use incl. commercial and modification, credit required),
which is why it is the automatic photo source for Korean places.
https://www.data.go.kr/data/15101914/openapi.do

The bot picks the first search result that is large enough, downloads it to photos/, and records the
photographer in data/photos_auto.json (bot/photos.py merges it with the hand-made content/photos.toml,
which always wins — put a photo there to override or veto the automatic pick).

Needs the KTO_API_KEY secret (the data.go.kr service key). Without it this does nothing.
NOTE: the request/response field names below follow the TourAPI 4.0 photo-gallery spec but were
written before a key existed, so the first real run should be a preview (dry run) — see the tests
for the response shape this expects.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote

from PIL import Image

from ..photos import AUTO_PATH, PHOTOS_DIR
from ..util import log, notice, scrub, warn

API = "https://apis.data.go.kr/B551011/PhotoGalleryService1/gallerySearchList1"
MIN_SIDE = 900          # px, so the cover doesn't look blurry after cropping to 1080x1350
CREDIT_SUFFIX = "Korea Tourism Organization (KOGL Type 1)"


def _credit(photographer: str) -> str:
    """Card text is set in a Latin-only font, so a Hangul photographer name would render as boxes:
    then credit the organization only (KOGL Type 1 needs the source, not a personal name)."""
    name = photographer.replace("한국관광공사", "").strip()
    if not name or re.search(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]", name):
        return f"Photo: {CREDIT_SUFFIX}"
    return f"Photo: {name} / {CREDIT_SUFFIX}"


def _clean(text: str, key: str) -> str:
    """Remove the key from an error message in every form it can appear in (raw, decoded, URL-encoded)."""
    for form in {key, unquote(key), quote(unquote(key), safe=""), quote(key, safe="")}:
        text = scrub(text, form)
    return text


def _items(payload: dict) -> list[dict]:
    body = (payload.get("response") or {}).get("body") or {}
    items = (body.get("items") or {})
    if isinstance(items, str):          # the API returns "" when there is nothing
        return []
    item = items.get("item", [])
    return [item] if isinstance(item, dict) else list(item)


def search(keyword: str, key: str, session=None, rows: int = 30) -> list[dict]:
    import requests
    session = session or requests
    params = {"serviceKey": unquote(key), "numOfRows": rows, "pageNo": 1, "MobileOS": "ETC",
              "MobileApp": "LocalTrip", "keyword": keyword, "_type": "json"}
    r = session.get(API, params=params, timeout=30)
    r.raise_for_status()
    return _items(r.json())


def _download(url: str, session=None) -> Image.Image | None:
    import requests
    session = session or requests
    r = session.get(url.replace("http://", "https://"), timeout=60)
    r.raise_for_status()
    im = Image.open(io.BytesIO(r.content))
    return im if min(im.size) >= MIN_SIDE else None


def ensure_photo(topic, cfg, session=None, photos_dir: Path | None = None, auto_path: Path | None = None) -> bool:
    """Make sure this topic has a photo when it can. True if a photo is available afterwards."""
    from ..photos import photo_for
    if photo_for(topic, photos_dir):
        return True
    key = cfg.kto_key
    ko = topic.data.get("ko")
    if not key or not ko or topic.data.get("country") != "Korea":
        return False
    photos_dir = photos_dir or PHOTOS_DIR
    auto_path = auto_path or AUTO_PATH
    try:
        for item in search(ko, key, session):
            url = item.get("galWebImageUrl")
            who = (item.get("galPhotographer") or "").strip()
            if not url or not who:
                continue
            try:
                im = _download(url, session)
            except Exception:
                continue
            if im is None:
                continue
            name = f"auto-{topic.data['key']}.jpg"
            photos_dir.mkdir(parents=True, exist_ok=True)
            im.convert("RGB").save(photos_dir / name, quality=92)
            table = json.loads(auto_path.read_text()) if auto_path.exists() else {}
            table[topic.data["key"]] = {
                "key": topic.data["key"], "file": name,
                "credit": _credit(who),
                "source": "https://www.data.go.kr/data/15101914/openapi.do",
                "license": "kogl-1", "title": item.get("galTitle", ""), "content_id": item.get("galContentId", ""),
            }
            auto_path.parent.mkdir(parents=True, exist_ok=True)
            auto_path.write_text(json.dumps(table, ensure_ascii=False, indent=2))
            notice("사진", f"확보: {topic.data['key']} <- {item.get('galTitle', '')} / {who} ({im.size[0]}x{im.size[1]})")
            log(f"사진 확보: {topic.data['key']} ← {item.get('galTitle', '')} ({who})")
            return True
        notice("사진", f"'{ko}' 결과 없음 또는 모두 작음")
        warn(f"'{ko}' 로 쓸 만한 관광공사 사진을 찾지 못했어요 (사진 없이 진행)")
    except Exception as exc:
        notice("사진", f"API 오류: {_clean(str(exc), key)[:300]}")
        warn(f"관광공사 사진 API 오류 (사진 없이 진행): {_clean(str(exc), key)}")
    return False

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

from .. import vision
from ..photos import AUTO_PATH, GALLERY_PATH, PHOTOS_DIR
from ..util import log, notice, scrub, warn

API = "https://apis.data.go.kr/B551011/PhotoGalleryService1/gallerySearchList1"
GALLERY_SIZE = 6       # cover photo + 5 photo slides
MIN_GALLERY = 4        # fewer than this and the photo tour is skipped that day
MAX_JUDGED = 6         # at most this many AI checks per place (keeps a run cheap and fast)
MIN_SIDE = 900          # px, so the cover doesn't look blurry after cropping to 1080x1350
CREDIT_SUFFIX = "Korea Tourism Organization (KOGL Type 1)"


def _credit(photographer: str) -> str:
    """Card text is set in a Latin-only font, so a Hangul photographer name would render as boxes:
    then credit the organization only (KOGL Type 1 needs the source, not a personal name)."""
    name = photographer.replace("한국관광공사", "").strip()
    if not name or re.search(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]", name):
        return f"Photo: {CREDIT_SUFFIX}"
    return f"Photo: {name} / {CREDIT_SUFFIX}"


# Photos with crowds or identifiable faces are a privacy/relevance risk on a public account, so words in
# a photo's title/keywords that suggest people push it to the back; scenery words bring it forward.
AVOID = ("미사", "예배", "공연", "행사", "축제", "퍼레이드", "인물", "모델", "체험", "시위", "집회", "내부", "관람", "경기", "마라톤", "콘서트", "공연장")
PREFER = ("거리", "전경", "야경", "풍경", "골목", "경관", "외관", "전망", "공원", "야외", "건축")


def _rank(item: dict) -> tuple[int, int]:
    text = f"{item.get('galTitle', '')} {item.get('galSearchKeyword', '')}"
    return (1 if any(w in text for w in AVOID) else 0, 0 if any(w in text for w in PREFER) else 1)


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


def _get(session, url, tries: int = 3, **kw):
    """GET with retries: the KTO server is slow to connect from some networks (seen: connect timeouts)."""
    import time
    last = None
    for i in range(tries):
        try:
            r = session.get(url, **kw)
            r.raise_for_status()
            return r
        except Exception as exc:          # timeouts, resets, 5xx: wait and try again
            last = exc
            if i < tries - 1:
                time.sleep(3 * (i + 1) if not getattr(session, "fast", False) else 0)
    raise last


def search(keyword: str, key: str, session=None, rows: int = 30) -> list[dict]:
    import requests
    session = session or requests
    params = {"serviceKey": unquote(key), "numOfRows": rows, "pageNo": 1, "MobileOS": "ETC",
              "MobileApp": "LocalTrip", "keyword": keyword, "_type": "json"}
    r = _get(session, API, params=params, timeout=(20, 40))
    return _items(r.json())


SIZES: list[int] = []      # short side of every downloaded candidate in the latest run (for notices)
ERRORS: list[str] = []


def _download(url: str, session=None) -> Image.Image | None:
    import requests
    session = session or requests
    r = _get(session, url.replace("http://", "https://"), timeout=(20, 60))
    im = Image.open(io.BytesIO(r.content))
    SIZES.append(min(im.size))
    return im if min(im.size) >= MIN_SIDE else None


def find_results(data: dict, key: str, session=None) -> tuple[str, list[dict]]:
    """Try the place's search words in order (ko, ko without a trailing 동, then ko_alt); first non-empty wins."""
    ko = data["ko"]
    for kw in dict.fromkeys([ko, ko.removesuffix("동")] + list(data.get("ko_alt", []))):
        results = search(kw, key, session)
        if results:
            return kw, results
    return "", []


LAST_STATS: dict[str, int] = {}     # why candidates were skipped in the latest _vetted run (for run notices)
EXTRA_WORDS = ("거리", "먹거리", "쇼핑", "야경")   # added to the place name so results are not all one landmark


def find_all(data: dict, key: str, session=None, cap: int = 80) -> list[dict]:
    """Results for the place's main search word plus a few topical variants, merged and de-duplicated."""
    kw, first = find_results(data, key, session)
    if not kw:
        return []
    merged, seen = list(first), {i.get("galContentId") or i.get("galWebImageUrl") for i in first}
    for extra in EXTRA_WORDS:
        try:
            more = search(f"{kw} {extra}", key, session)
        except Exception:
            continue
        for item in more:
            ident = item.get("galContentId") or item.get("galWebImageUrl")
            if ident not in seen:
                seen.add(ident)
                merged.append(item)
    return merged[:cap]


def _vetted(topic, cfg, session=None, vision_session=None, max_judged: int = MAX_JUDGED, diverse: bool = False):
    """Yield (item, image, verdict) for candidate photos that pass every check, best-ranked first.
    verdict is None when no AI key is set (then only size and title-word ranking apply)."""
    key, ko = cfg.kto_key, topic.data["ko"]
    results = find_all(topic.data, key, session) if diverse else find_results(topic.data, key, session)[1]
    judged, seen, used = 0, set(), {}
    LAST_STATS.clear()
    SIZES.clear()
    ERRORS.clear()
    LAST_STATS.update(candidates=len(results), download_failed=0, too_small=0, wrong_place=0, low_quality=0, same_kind=0, accepted=0)
    for item in sorted(results, key=_rank):
        url = item.get("galWebImageUrl")
        who = (item.get("galPhotographer") or "").strip()
        if not url or not who or url in seen:
            continue
        seen.add(url)
        try:
            im = _download(url, session)
        except Exception as exc:
            LAST_STATS["download_failed"] += 1
            if len(ERRORS) < 3:
                ERRORS.append(f"{type(exc).__name__}: {str(exc)[:80]}")
            continue
        if im is None:
            LAST_STATS["too_small"] += 1
            continue
        verdict = None
        if cfg.gemini_key:
            if judged >= max_judged:
                return
            judged += 1
            try:
                verdict = vision.judge(im, topic.data.get("title") or topic.data.get("name") or ko, "Seoul",
                                       cfg.gemini_key, cfg.vision.get("model", "gemini-3.5-flash-lite"), vision_session)
            except Exception as exc:
                notice("사진", f"AI 확인 오류 (제목 순위만으로 진행): {_clean(str(exc), cfg.gemini_key)[:200]}")
            if verdict is not None and not vision.acceptable(verdict):
                LAST_STATS["wrong_place" if not verdict.get("shows_place") else "low_quality"] += 1
                log(f"사진 탈락: {item.get('galTitle', '')} {verdict}")
                continue
            if diverse and verdict is not None:
                cat = str(verdict.get("category", "other"))
                if used.get(cat, 0) >= (2 if cat == "other" else 1):   # one photo per kind of subject
                    LAST_STATS["same_kind"] += 1
                    log(f"사진 중복 종류로 건너뜀: {item.get('galTitle', '')} ({cat})")
                    continue
                used[cat] = used.get(cat, 0) + 1
        LAST_STATS["accepted"] += 1
        yield item, im, verdict


def _entry(topic, item, name, verdict) -> dict:
    return {"key": topic.data["key"], "file": name, "credit": _credit((item.get("galPhotographer") or "").strip()),
            "source": "https://www.data.go.kr/data/15101914/openapi.do", "license": "kogl-1",
            "title": item.get("galTitle", ""), "content_id": item.get("galContentId", ""),
            "ai_checked": verdict is not None, "category": (verdict or {}).get("category", "")}


def _usable(topic, cfg) -> bool:
    return bool(cfg.kto_key and topic.data.get("ko") and topic.data.get("country") == "Korea")


def ensure_photo(topic, cfg, session=None, photos_dir: Path | None = None, auto_path: Path | None = None,
                 vision_session=None) -> bool:
    """Make sure this topic has a cover photo when it can. True if a photo is available afterwards."""
    from ..photos import photo_for
    if photo_for(topic, photos_dir):
        return True
    if not _usable(topic, cfg):
        return False
    photos_dir = photos_dir or PHOTOS_DIR
    auto_path = auto_path or AUTO_PATH
    try:
        for item, im, verdict in _vetted(topic, cfg, session, vision_session):
            name = f"auto-{topic.data['key']}.jpg"
            photos_dir.mkdir(parents=True, exist_ok=True)
            im.convert("RGB").save(photos_dir / name, quality=92)
            table = json.loads(auto_path.read_text()) if auto_path.exists() else {}
            table[topic.data["key"]] = _entry(topic, item, name, verdict)
            auto_path.parent.mkdir(parents=True, exist_ok=True)
            auto_path.write_text(json.dumps(table, ensure_ascii=False, indent=2))
            notice("사진", f"확보: {topic.data['key']} <- {item.get('galTitle', '')} ({im.size[0]}x{im.size[1]}) AI확인={'예' if verdict else '아니오'}")
            log(f"사진 확보: {topic.data['key']} ← {item.get('galTitle', '')}")
            return True
        notice("사진", f"'{topic.data['ko']}' 결과 없음, 모두 작음, 또는 AI가 모두 탈락시킴 (사진 없이 진행)")
        warn(f"'{topic.data['ko']}' 로 쓸 만한 관광공사 사진을 찾지 못했어요 (사진 없이 진행)")
    except Exception as exc:
        notice("사진", f"API 오류: {_clean(str(exc), cfg.kto_key)[:300]}")
        warn(f"관광공사 사진 API 오류 (사진 없이 진행): {_clean(str(exc), cfg.kto_key)}")
    return False


def ensure_gallery(topic, cfg, n: int = GALLERY_SIZE, session=None, photos_dir: Path | None = None,
                   gallery_path: Path | None = None, vision_session=None) -> list[dict]:
    """Up to n vetted photos of this place for a photo-tour post (saved as photos/gallery-<key>-N.jpg).
    Reuses an existing gallery; returns [] when the place has none or the API is not set up."""
    photos_dir = photos_dir or PHOTOS_DIR
    gallery_path = gallery_path or GALLERY_PATH
    table = json.loads(gallery_path.read_text()) if gallery_path.exists() else {}
    have = [e for e in table.get(topic.data["key"], []) if (photos_dir / e["file"]).exists()]
    if len(have) >= MIN_GALLERY or not _usable(topic, cfg):
        return have
    have = []
    try:
        for item, im, verdict in _vetted(topic, cfg, session, vision_session, max_judged=n * 5, diverse=True):
            name = f"gallery-{topic.data['key']}-{len(have) + 1}.jpg"
            photos_dir.mkdir(parents=True, exist_ok=True)
            im.convert("RGB").save(photos_dir / name, quality=92)
            have.append(_entry(topic, item, name, verdict))
            if len(have) >= n:
                break
    except Exception as exc:
        notice("사진", f"갤러리 API 오류: {_clean(str(exc), cfg.kto_key)[:300]}")
    if len(have) >= MIN_GALLERY:
        table[topic.data["key"]] = have
        gallery_path.parent.mkdir(parents=True, exist_ok=True)
        gallery_path.write_text(json.dumps(table, ensure_ascii=False, indent=2))
        notice("사진", f"갤러리 {topic.data['key']}: {len(have)}장 확보 (" + ", ".join(e.get('category') or '?' for e in have) + ")")
    else:
        notice("사진", f"갤러리 {topic.data['key']}: 쓸 만한 사진 {len(have)}장뿐이라 포토 투어는 건너뛰어요 · 후보 통계 {dict(LAST_STATS)} · 짧은 변 크기(최대 8개) {sorted(SIZES)[-8:]} · 오류 예 {ERRORS}")
    return have if len(have) >= MIN_GALLERY else []

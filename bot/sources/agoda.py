"""Agoda Affiliate Long Tail Search API — hotel list + links per city.

Spec (read again before wiring the real call — field names below are best-guess placeholders,
NOT confirmed against the PDF, since that needs affiliate approval first to test against):
https://partners.agoda.com/Content/Documents/AffiliateLiteApi/Affiliate_Lite_API_V2.0.pdf

Until AGODA_SITE_ID / AGODA_API_KEY secrets exist, every call below returns an empty list and
callers fall back to the `example_hotels` written by hand in content/cities.toml — same pattern
the K-beauty bot used for AliExpress before that key existed. Nothing here ever invents a hotel
name, price or rating; a card either shows real API data or the labeled example, never a guess.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..util import log, warn

ROOT = Path(__file__).resolve().parent.parent.parent
CATALOG_PATH = ROOT / "data" / "agoda_catalog.json"


class AgodaClient:
    def __init__(self, site_id: str | None, api_key: str | None):
        self.site_id = site_id
        self.api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self.site_id and self.api_key)

    def search_city(self, city_name: str, country: str) -> list[dict]:
        """[{name, tier_guess, review_score, review_source, link}, ...] or [] when not wired up yet."""
        if not self.enabled:
            return []
        # TODO(step 8 in 진행 순서, after affiliate approval): call the Long Tail Search API here,
        # confirm the real request/response field names against the PDF above, and map results to
        # {name, review_score, review_source: "Agoda", link} — no price (config.toml [hotels] says why).
        warn("Agoda API 키는 있지만 실제 호출 코드는 아직 연결 전이에요 (TODO)")
        return []


def load_catalog() -> dict[str, list[dict]]:
    """{"seoul": [hotel, ...], ...} saved by the weekly job. {} if it hasn't run yet."""
    if not CATALOG_PATH.exists():
        return {}
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        warn(f"agoda_catalog.json 을 읽지 못했어요: {exc}")
        return {}


def save_catalog(data: dict[str, list[dict]]) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"agoda_catalog.json 저장: 도시 {len(data)}개")


def hotels_for(city_key: str, city_entry: dict) -> list[dict]:
    """Real catalog entries if we have them for this city, else the hand-written examples
    (tagged so the caption/card knows not to show a booking link for those)."""
    catalog = load_catalog()
    live = catalog.get(city_key, [])
    if live:
        return live
    return [{"name": h["name"], "tier": h["tier"], "note": h.get("note", ""), "link": None}
            for h in city_entry.get("example_hotels", [])]

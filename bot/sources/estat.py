"""Japan Tourism Agency accommodation survey (宿泊旅行統計調査), via the e-Stat API — used
in place of Rakuten's ranking API, which we can't use here: Rakuten's terms forbid linking
ranking-API results to a non-Rakuten booking site and forbid storing the response in a public
repo, and the ranking API itself has no per-prefecture breakdown (nationwide top 10 only).
https://www.e-stat.go.jp/api/en/api-info/api-guide
https://www.e-stat.go.jp/api/en/terms-of-use

e-Stat *does* require crediting the source when its numbers are shown (Article 7) — the weekly
card and linkpage entry both need a "Source: e-Stat (Japan Tourism Agency)" line; see
bot/weekly.py. Numbers are monthly (prefecture-level guest counts), so this is naturally a
"few months behind" trend, not a live ranking — the card should say which month it's showing.
"""
from __future__ import annotations

import json
from datetime import date as Date
from pathlib import Path

from ..util import log, warn

ROOT = Path(__file__).resolve().parent.parent.parent
API = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsData"


def prefecture_guest_counts(app_id: str | None, stats_data_id: str, session=None) -> list[dict] | None:
    """[{prefecture, month, guests}, ...] sorted by guests desc, or None if not configured/failed.

    TODO(5단계/6단계): confirm `stats_data_id` is the right 統計表ID for 宿泊旅行統計調査's
    prefecture x month table (config.toml [estat] has a placeholder), and map the getStatsData
    response's CLASS_OBJ / VALUE arrays to prefecture names + guest counts. Requests fewer than
    12 months back so a rate limit never blocks a scheduled run silently.
    """
    if not app_id:
        return None
    warn("e-Stat 앱 ID는 있지만 실제 호출 코드는 아직 연결 전이에요 (TODO)")
    return None


CACHE_PATH = ROOT / "data" / "estat_latest.json"


def save(data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"estat_latest.json 저장: {data.get('month', '?')}")


def load() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        warn(f"estat_latest.json 을 읽지 못했어요: {exc}")
        return None

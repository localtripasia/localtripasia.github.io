"""'This week locals are going' (Thursday post) — the one card that needs live data.

Korea : Naver search trend via NAVER API HUB (official, free up to 30,000 calls/month —
        NAVER_CLIENT_ID / NAVER_CLIENT_SECRET). Weekly search interest for destination keywords
        (content/keywords.toml), last full week (Mon-Sun) vs the week before.
Japan : Prefecture accommodation counts from e-Stat (bot/sources/estat.py), a few months behind
        since it's a government survey, not a live ranking — the card says which month.
The Monday-run weekly job saves data/trend_latest.json; the Thursday post reads it.
"""
from __future__ import annotations

import json
import tomllib
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

import requests

from .sources import estat
from .util import log, scrub, warn

NAVER_URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"  # NAVER API HUB (Naver Cloud)


def trend_path(cfg) -> Path:
    return cfg.root / "data" / "trend_latest.json"


def load_terms(cfg) -> list[dict]:
    path = cfg.content_dir / "keywords.toml"
    if not path.exists():
        return []
    with open(path, "rb") as fh:
        return [t for t in tomllib.load(fh).get("term", []) if t.get("keywords")]


def last_full_week(today: Date) -> tuple[Date, Date]:
    """Monday..Sunday of the last complete week before `today`."""
    end = today - timedelta(days=today.weekday() + 1)
    return end - timedelta(days=6), end


def naver_trends(cfg, today: Date, session=None) -> list[dict]:
    keys = cfg.naver_keys
    terms = load_terms(cfg)
    if not keys or not terms:
        return []
    http = session or requests
    anchor = terms[0]
    start_week, end = last_full_week(today)
    start = end - timedelta(days=34)
    this_days = {(end - timedelta(days=i)).isoformat() for i in range(7)}
    prev_days = {(end - timedelta(days=i)).isoformat() for i in range(7, 14)}
    others = terms[1:]
    out: dict[str, dict] = {}
    batches = [others[i:i + 4] for i in range(0, len(others), 4)] or [[]]
    for batch_others in batches:
        batch = [anchor] + batch_others
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(), "timeUnit": "date",
                "keywordGroups": [{"groupName": t["id"], "keywords": t["keywords"][:20]} for t in batch]}
        try:
            r = http.post(NAVER_URL, json=body, timeout=30, headers={
                "X-NCP-APIGW-API-KEY-ID": keys[0], "X-NCP-APIGW-API-KEY": keys[1], "Content-Type": "application/json"})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} {str(getattr(r, 'text', ''))[:120]}")
            results = r.json().get("results", [])
        except Exception as exc:
            warn(f"네이버 검색 트렌드를 가져오지 못했어요: {scrub(str(exc), *keys)[:160]}")
            return []
        sums = {}
        for res in results:
            data = res.get("data", [])
            sums[res.get("title")] = (sum(d["ratio"] for d in data if d.get("period") in this_days),
                                      sum(d["ratio"] for d in data if d.get("period") in prev_days))
        a_now = sums.get(anchor["id"], (0, 0))[0]
        for t in batch:
            now, prev = sums.get(t["id"], (0.0, 0.0))
            if t["id"] in out and t is anchor:
                continue
            out[t["id"]] = {
                "id": t["id"], "name": t["name"],
                "level": (now / a_now) if a_now else None, "this_week": round(now, 2), "last_week": round(prev, 2),
                "change": round((now / prev - 1) * 100) if prev else None,
            }
    rows = [r for r in out.values() if r["level"]]
    top = max((r["level"] for r in rows), default=0)
    for r in out.values():
        r["index"] = round(r["level"] / top * 100) if (r["level"] and top) else 0
    log(f"네이버 검색 트렌드: {len(rows)}개 목적지 ({start_week}~{end})")
    return sorted(out.values(), key=lambda r: -r["index"])


def japan_stays(cfg) -> dict | None:
    """{"month": "2026-07", "rows": [{prefecture, guests}, ...]} from the cached e-Stat pull, or None."""
    return estat.load()


def compute(cfg, today: Date, session=None) -> dict:
    start, end = last_full_week(today)
    japan = japan_stays(cfg)
    return {
        "week_start": start.isoformat(), "week_end": end.isoformat(), "made": today.isoformat(),
        "korea": naver_trends(cfg, today, session),
        "japan_month": (japan or {}).get("month"),
        "japan": (japan or {}).get("rows", [])[:10],
    }


def save(cfg, data: dict) -> None:
    p = trend_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def load(cfg) -> dict | None:
    p = trend_path(cfg)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def latest(cfg, today: Date, session=None) -> dict | None:
    """Saved weekly data if it's for last week; otherwise compute it now (and keep it)."""
    start, end = last_full_week(today)
    data = load(cfg)
    if data and data.get("week_end") == end.isoformat():
        return data
    try:
        data = compute(cfg, today, session)
    except Exception as exc:
        warn(f"이번 주 트렌드 계산 실패: {exc}")
        return data
    if data.get("korea") or data.get("japan"):
        save(cfg, data)
    return data

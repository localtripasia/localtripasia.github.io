"""Topic-based schedule.

Every series in config.toml [series] has a monthly target (per_month), a minimum gap in days
between two posts of that series (gap) and optionally a fixed weekday (day = "thu"). Each day
the bot posts the series that is furthest behind its target for this point in the month;
fixed-day series (weekly) go first on their day. If a series has nothing left to post, the
next one in line is tried (see plan_order's returned `steps`).

Series: city101 · area · hotel · transport · route · season · words · weekly · recap
  (what each one covers is in config.toml's comments and the 기획서 콘텐츠 시리즈 table)
"""
from __future__ import annotations

import calendar
import math
from collections import Counter
from datetime import date as Date

from .util import warn

SERIES_NAMES = ("city101", "area", "hotel", "transport", "route", "season", "words", "weekly", "recap")
DAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
FALLBACK_SERIES = "city101"  # always has something to say if everything else is exhausted


def series_cfg(cfg) -> dict[str, dict] | None:
    raw = cfg.raw.get("series")
    if not raw:
        return None
    out = {}
    for name, c in raw.items():
        name = str(name).strip().lower()
        if name not in SERIES_NAMES:
            warn(f"config.toml [series] 의 '{name}' 은 모르는 종류예요 (건너뜀)")
            continue
        c = c if isinstance(c, dict) else {"per_month": c}
        day = str(c.get("day", "")).strip().lower()[:3]
        out[name] = {"per_month": float(c.get("per_month", 0) or 0), "gap": int(c.get("gap", 0) or 0),
                     "day": DAYS.get(day)}
    return out


def series_of(post: dict) -> str:
    return post.get("source", "")


def posts_per_day(cfg) -> int:
    try:
        return max(1, int(cfg.posts_per_day))
    except (TypeError, ValueError):
        return 1


def plan_order(cfg, state, today: Date) -> tuple[str, list[str]] | None:
    """(this slot's series, the steps to try in order), or None when [series] isn't set."""
    sc = series_cfg(cfg)
    if not sc:
        return None
    ppd = posts_per_day(cfg)
    iso = today.isoformat()
    pubs = [p for p in state.published if p.get("date", "") <= iso]
    today_posts = [series_of(p) for p in pubs if p.get("date") == iso]
    month = today.strftime("%Y-%m")
    count = Counter(series_of(p) for p in pubs if p.get("date", "").startswith(month))
    last: dict[str, Date] = {}
    for p in pubs:
        try:
            d = Date.fromisoformat(p["date"])
        except (KeyError, ValueError):
            continue
        s_ = series_of(p)
        if s_ not in last or d > last[s_]:
            last[s_] = d
    slot = min(len(today_posts), ppd - 1)
    frac = (today.day - 1 + (slot + 1) / ppd) / calendar.monthrange(today.year, today.month)[1]
    fixed, ready, waiting = [], [], []
    for i, (name, c) in enumerate(sc.items()):
        if c["per_month"] <= 0:
            continue
        if c["day"] is not None:
            if today.weekday() == c["day"] and name not in today_posts:
                fixed.append(name)
            continue
        target = c["per_month"] * ppd
        gap = math.ceil(c["gap"] / ppd)
        deficit = target * frac - count[name]
        gap_ok = name not in today_posts and (name not in last or (today - last[name]).days >= gap)
        room = count[name] < math.ceil(target)
        (ready if gap_ok and room else waiting).append((-deficit, i, name))
    order = fixed + [n for *_, n in sorted(ready)] + [n for *_, n in sorted(waiting)]
    if FALLBACK_SERIES not in order:
        order.append(FALLBACK_SERIES)
    steps = list(dict.fromkeys(order))
    return order[0], steps


def month_summary(cfg, state, today: Date) -> str:
    sc = series_cfg(cfg) or {}
    month = today.strftime("%Y-%m")
    count = Counter(series_of(p) for p in state.published if p.get("date", "").startswith(month))
    ppd = posts_per_day(cfg)
    return " · ".join(f"{n} {count[n]}/{c['per_month'] * (1 if c['day'] is not None else ppd):g}"
                      for n, c in sc.items() if c["per_month"] > 0)

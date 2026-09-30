"""Loads content/*.toml (researched, sourced by hand) and picks today's topic.

Nothing here is written by AI at post time — every fact comes from content/*.toml, each entry
carries >= 2 sources, and a test checks that. Hotel names/links for "hotel" and "city101" cards
come from data/agoda_catalog.json (bot/sources/agoda.py, saved weekly); when that's empty
(no Agoda key yet, or nothing matched) the content entry's own `example_hotels` are shown
without a booking link, same as the K-beauty bot did for Olive Young products.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date as Date
from pathlib import Path

from .util import warn

ROOT = Path(__file__).resolve().parent.parent
KINDS = ("city101", "hood", "area", "hotel", "transport", "route", "season", "words", "recap")


@dataclass
class Library:
    cities: list[dict] = field(default_factory=list)
    areas: list[dict] = field(default_factory=list)
    hoods: list[dict] = field(default_factory=list)
    passes: list[dict] = field(default_factory=list)
    routes: list[dict] = field(default_factory=list)
    seasons: list[dict] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)

    def city(self, key: str) -> dict | None:
        return next((c for c in self.cities if c["key"] == key), None)


def content_dir(cfg) -> Path:
    return cfg.content_dir


def _read(base: Path, name: str) -> dict:
    path = base / name
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except Exception as exc:  # a typo in one file shouldn't stop every other post
        warn(f"{path.name} 을 읽지 못했어요 (그 시리즈는 건너뛰어요): {exc}")
        return {}


def load_library(cfg) -> Library:
    base = content_dir(cfg)
    return Library(
        cities=_read(base, "cities.toml").get("city", []),
        areas=_read(base, "areas.toml").get("area", []),
        hoods=_read(base, "hoods.toml").get("hood", []),
        passes=_read(base, "passes.toml").get("pass", []),
        routes=_read(base, "routes.toml").get("route", []),
        seasons=_read(base, "seasons.toml").get("season", []),
        words=_read(base, "words.toml").get("set", []),
    )


# ---------------------------------------------------------------------------
# what to post today
# ---------------------------------------------------------------------------
@dataclass
class Topic:
    kind: str            # city101 | hood | area | hotel | transport | route | season | words | recap
    key: str             # state key, e.g. city-seoul, area-seoul-myeongdong-hongdae-seongsu
    data: dict
    repeat: bool = False

    @property
    def title(self) -> str:
        if self.kind in ("city101", "hotel"):
            return self.data.get("name") or self.data.get("title", "")
        return self.data.get("title", "")

    @property
    def sources(self) -> list[str]:
        return list(self.data.get("sources") or [])


def entries_for(kind: str, lib: Library) -> list[dict]:
    return {
        "city101": lib.cities,
        "hotel": lib.cities,       # each city entry carries its own budget/mid/splurge picks
        "area": lib.areas,
        "hood": lib.hoods,
        "transport": lib.passes,
        "route": lib.routes,
        "season": lib.seasons,
        "words": lib.words,
    }.get(kind, [])


def key_of(kind: str, entry: dict) -> str:
    return f"{kind}-{entry['key']}"


def next_topic(kind: str, lib: Library, state, today: Date, cfg) -> Topic | None:
    """Least-recently-used entry for this kind; None when the library has nothing for it yet."""
    entries = entries_for(kind, lib)
    if not entries:
        return None
    last = state.last_used()
    repeat_after = cfg.repeat_after_days

    def age(entry: dict) -> int:
        k = key_of(kind, entry)
        if k not in last:
            return 10**9  # never posted: always first in line
        d = Date.fromisoformat(last[k])
        return (today - d).days

    ranked = sorted(entries, key=lambda e: -age(e))
    best = ranked[0]
    if age(best) < repeat_after and best is not ranked[0]:
        return None  # shouldn't happen, kept for clarity
    repeat = age(best) < 10**9  # posted before, just old enough to repeat
    return Topic(kind=kind, key=key_of(kind, best), data=best, repeat=repeat)


def find_topic(kind: str, key: str, lib: Library) -> Topic | None:
    for e in entries_for(kind, lib):
        if key_of(kind, e) == key:
            return Topic(kind=kind, key=key, data=e)
    return None


def remaining(lib: Library, state) -> dict[str, int]:
    used = state.used_keys()
    out: dict[str, int] = {}
    for kind in KINDS:
        entries = entries_for(kind, lib)
        out[kind] = sum(1 for e in entries if key_of(kind, e) not in used)
    return out

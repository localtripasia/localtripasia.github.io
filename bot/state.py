"""Remembers what has been posted (data/state.json, committed back by the workflow)."""
from __future__ import annotations

import json
from pathlib import Path

EMPTY = {"version": 1, "posts": []}


class State:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.data = json.loads(json.dumps(EMPTY))
        for k, v in EMPTY.items():
            self.data.setdefault(k, json.loads(json.dumps(v)))

    # ------------------------------------------------------------------
    @property
    def posts(self) -> list[dict]:
        return self.data["posts"]

    @property
    def published(self) -> list[dict]:
        return [p for p in self.posts if p.get("status") == "published"]

    def drop_unpublished(self) -> None:
        """Posts that were prepared but never went live are forgotten (their topic is retried)."""
        self.data["posts"] = self.published

    def next_number(self) -> int:
        return max((p["number"] for p in self.published), default=0) + 1

    def used_keys(self) -> set[str]:
        return {p["key"] for p in self.published}

    def last_used(self) -> dict[str, str]:
        """Most recent publish date per topic key (skin/city101/etc), for gap + repeat_after_days."""
        out: dict[str, str] = {}
        for p in self.published:
            out[p["key"]] = p["date"]
        return out

    def published_on(self, date: str) -> dict | None:
        for p in self.published:
            if p.get("date") == date:
                return p
        return None

    def pending(self) -> dict | None:
        for p in reversed(self.posts):
            if p.get("status") in ("prepared", "failed"):
                return p
        return None

    # ------------------------------------------------------------------
    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

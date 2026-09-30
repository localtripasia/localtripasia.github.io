"""Loads config.toml and secrets from environment variables."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    raw: dict
    root: Path = ROOT

    # ---- account ----------------------------------------------------------
    @property
    def account(self) -> dict:
        return self.raw.get("account", {})

    @property
    def handle(self) -> str:
        return self.account.get("handle", "your.handle").lstrip("@")

    @property
    def brand_name(self) -> str:
        return self.account.get("brand_name", "Local Trip")

    @property
    def tagline(self) -> str:
        return self.account.get("tagline", "")

    @property
    def timezone(self) -> str:
        return self.account.get("timezone", "Asia/Seoul")

    # ---- schedule / series --------------------------------------------------
    @property
    def series(self) -> dict:
        return self.raw.get("series", {})

    @property
    def posts_per_day(self) -> int:
        return int(self.raw.get("schedule", {}).get("posts_per_day", 1))

    @property
    def repeat_after_days(self) -> int:
        return int(self.raw.get("schedule", {}).get("repeat_after_days", 150))

    @property
    def reels(self) -> dict:
        return self.raw.get("reels", {})

    # ---- files --------------------------------------------------------------
    @property
    def state_file(self) -> Path:
        return self.root / "data" / "state.json"

    @property
    def content_dir(self) -> Path:
        return self.root / "content"

    # ---- affiliates -----------------------------------------------------------
    @property
    def hotels(self) -> dict:
        return self.raw.get("hotels", {})

    @property
    def agoda(self) -> dict:
        return self.raw.get("agoda", {})

    @property
    def tripcom(self) -> dict:
        return self.raw.get("tripcom", {})

    def tripcom_link(self, url: str | None = None, sub1: str = "") -> str:
        """Trip.com affiliate deep link. Falls back to the plain URL until alliance_id is set."""
        from urllib.parse import urlencode
        t = self.tripcom
        url = url or t.get("hotels_url", "https://www.trip.com/hotels/")
        if not t.get("alliance_id"):
            return url
        q = urlencode({"Allianceid": t["alliance_id"], "SID": t.get("sid", ""), "trip_sub1": sub1,
                       "trip_sub3": t.get("sub3", "")})
        return f"{url}{'&' if '?' in url else '?'}{q}"

    @property
    def klook(self) -> dict:
        return self.raw.get("klook", {})

    @property
    def estat(self) -> dict:
        return self.raw.get("estat", {})

    @property
    def naver(self) -> dict:
        return self.raw.get("naver", {})

    @property
    def copy(self) -> dict:
        return self.raw.get("copy", {})

    @property
    def instagram(self) -> dict:
        return self.raw.get("instagram", {})

    @property
    def pinterest(self) -> dict:
        return self.raw.get("pinterest", {})

    # ---- secrets (never printed, never logged) -------------------------------
    @property
    def ig_token(self) -> str | None:
        return os.environ.get("IG_ACCESS_TOKEN", "").strip() or None

    @property
    def ig_user_id(self) -> str | None:
        return os.environ.get("IG_USER_ID", "").strip() or None

    @property
    def agoda_site_id(self) -> str | None:
        return os.environ.get("AGODA_SITE_ID", "").strip() or (self.agoda.get("site_id") or None)

    @property
    def agoda_api_key(self) -> str | None:
        return os.environ.get("AGODA_API_KEY", "").strip() or None

    @property
    def tripcom_key(self) -> str | None:
        return os.environ.get("TRIPCOM_AFFILIATE_KEY", "").strip() or None

    @property
    def klook_key(self) -> str | None:
        return os.environ.get("INVOLVE_ASIA_KEY", "").strip() or None

    @property
    def gemini_key(self) -> str | None:
        return os.environ.get("GEMINI_API_KEY", "").strip() or None

    @property
    def vision(self) -> dict:
        return self.raw.get("vision", {})

    @property
    def kto_key(self) -> str | None:
        return os.environ.get("KTO_API_KEY", "").strip() or None

    @property
    def estat_app_id(self) -> str | None:
        return os.environ.get("ESTAT_APP_ID", "").strip() or None

    @property
    def naver_keys(self) -> tuple[str, str] | None:
        cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
        secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
        return (cid, secret) if cid and secret else None

    def secrets(self) -> list[str]:
        """Every secret value currently set, for util.scrub() before logging."""
        vals = [self.ig_token, self.agoda_api_key, self.tripcom_key, self.klook_key, self.estat_app_id, self.kto_key, self.gemini_key]
        if self.naver_keys:
            vals.extend(self.naver_keys)
        return [v for v in vals if v]


def load_config(path: Path | None = None) -> Config:
    path = path or (ROOT / "config.toml")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return Config(raw=raw)

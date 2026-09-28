"""Turns a Topic into caption + card text + affiliate buttons. No AI: every word here is
either copied from content/*.toml or a short fixed template, since the target audience reads
English and the facts are already written in English by hand (or by the monthly research pass).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .sources.agoda import hotels_for

DISCLOSURE = "#ad Contains affiliate links — we may earn a small commission at no extra cost to you."


@dataclass
class Copy:
    hook: str
    caption: str
    bullets: list[str] = field(default_factory=list)
    buttons: list[dict] = field(default_factory=list)
    article_blocks: list[tuple] = field(default_factory=list)  # (heading, str | list[str])
    sources: list[str] = field(default_factory=list)


def _agoda_button(cfg, city_key: str, city_name: str, hotel: dict | None = None) -> dict:
    site_id = cfg.agoda_site_id
    if site_id and hotel and hotel.get("link"):
        return {"label": "Agoda", "url": hotel["link"], "class": ""}
    # Before affiliate approval (or with no per-hotel link yet), fall back to the plain homepage —
    # a real, working link, just not a deep search link or an affiliate one. Swap in config.toml
    # [agoda] link_template once approved (see bot/sources/agoda.py).
    return {"label": "Agoda", "url": "https://www.agoda.com/", "class": ""}


def _tripcom_button(cfg) -> dict:
    return {"label": "Trip.com", "url": "https://www.trip.com/", "class": "teal"}


def _klook_button(cfg) -> dict:
    return {"label": "Klook", "url": "https://www.klook.com/", "class": "teal"}


def _hashtags(cfg, extra: list[str]) -> str:
    tags = list(cfg.copy.get("hashtags_common", [])) + extra
    return " ".join(dict.fromkeys(tags))


def _caption(hook: str, bullets: list[str], hashtags: str, has_buttons: bool) -> str:
    lines = [hook, ""] + [f"✓ {b}" for b in bullets]
    lines += ["", "Full guide + links in bio →"]
    if has_buttons:
        lines += ["", DISCLOSURE]
    lines += ["", hashtags]
    return "\n".join(lines)


def build_copy(topic, cfg) -> Copy:
    d = topic.data
    k = topic.kind

    if k == "city101":
        things = d.get("things", [])
        hook = f"{d['name']}: your first 48 hours"
        bullets = things[:3] or [d.get("why", "")]
        hotels = hotels_for(d["key"], d)
        buttons = [_agoda_button(cfg, d["key"], d["name"]), _tripcom_button(cfg)] if hotels else []
        blocks = [
            ("Why go", d.get("why", "")), ("When to go", d.get("when", "")),
            ("Getting there", d.get("getting_there", "")), ("Do this", things),
            ("Where to stay", [f"{h['tier'].title()}: {h['name']} — {h.get('note', '')}" for h in hotels]),
        ]
        return Copy(hook=hook, caption=_caption(hook, bullets, _hashtags(cfg, []), bool(buttons)),
                    bullets=bullets, buttons=buttons, article_blocks=blocks, sources=topic.sources)

    if k == "hotel":
        hotels = hotels_for(d["key"], d)
        hook = f"Where to stay in {d['name']}, by budget"
        bullets = [f"{h['tier'].title()}: {h['name']}" for h in hotels]
        buttons = [_agoda_button(cfg, d["key"], d["name"]), _tripcom_button(cfg)]
        blocks = [("Budget", [f"{h['name']} — {h.get('note', '')}" for h in hotels if h["tier"] == "budget"]),
                  ("Mid-range", [f"{h['name']} — {h.get('note', '')}" for h in hotels if h["tier"] == "mid"]),
                  ("Splurge", [f"{h['name']} — {h.get('note', '')}" for h in hotels if h["tier"] == "splurge"])]
        return Copy(hook=hook, caption=_caption(hook, bullets, _hashtags(cfg, cfg.copy.get("hashtags_hotel", [])), True),
                    bullets=bullets, buttons=buttons, article_blocks=blocks, sources=topic.sources)

    if k == "area":
        picks = d.get("picks", [])
        hook = d["title"]
        bullets = [f"{p['name']}: {p.get('note', '')}" for p in picks]
        return Copy(hook=hook, caption=_caption(hook, bullets, _hashtags(cfg, []), False), bullets=bullets,
                    buttons=[], article_blocks=[("Neighborhoods", bullets)], sources=topic.sources)

    if k == "transport":
        hook = d["title"]
        bullets = [d.get("worth_it", "")[:120]]
        buttons = [_klook_button(cfg)]
        blocks = [("What it covers", d.get("covers", "")), ("Worth it?", d.get("worth_it", ""))]
        return Copy(hook=hook, caption=_caption(hook, bullets, _hashtags(cfg, []), True), bullets=bullets,
                    buttons=buttons, article_blocks=blocks, sources=topic.sources)

    if k == "route":
        stops = d.get("stops", [])
        hook = d["title"]
        bullets = stops[:3]
        buttons = [_klook_button(cfg), _agoda_button(cfg, "", "")]
        blocks = [("The route", f"{d.get('days', '?')} days"), ("Stop by stop", stops)]
        return Copy(hook=hook, caption=_caption(hook, bullets, _hashtags(cfg, cfg.copy.get("hashtags_route", [])), True),
                    bullets=bullets, buttons=buttons, article_blocks=blocks, sources=topic.sources)

    if k == "season":
        hook = d["title"]
        bullets = [d.get("months", "")]
        blocks = [("When", d.get("months", "")), ("Know this", d.get("note", ""))]
        return Copy(hook=hook, caption=_caption(hook, bullets, _hashtags(cfg, []), False), bullets=bullets,
                    buttons=[], article_blocks=blocks, sources=topic.sources)

    if k == "words":
        phrases = d.get("phrases", [])
        hook = d["title"]
        bullets = [f"{p['local']} ({p['romanized']}) — {p['meaning']}" for p in phrases[:3]]
        blocks = [("Phrases", bullets)]
        return Copy(hook=hook, caption=_caption(hook, bullets, _hashtags(cfg, []), False), bullets=bullets,
                    buttons=[], article_blocks=blocks, sources=[])

    hook = d.get("title") or topic.title
    return Copy(hook=hook, caption=_caption(hook, [], _hashtags(cfg, []), False), sources=topic.sources)

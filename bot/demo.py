"""`python -m bot demo` — renders one sample post per series kind from content/*.toml,
with no API keys needed, so you can see the cards before anything is wired up."""
from __future__ import annotations

from datetime import date as Date
from pathlib import Path

from . import copy as copy_mod
from . import editorial
from .config import load_config
from .linkpage import build_link_page
from .pinterest import build_pinterest
from .render import contact_sheet, render_pin, render_topic
from .util import log

KIND_ORDER = ("city101", "hotel", "area", "transport", "route", "season", "words")


def _sample_topic(kind: str, lib: editorial.Library):
    entries = editorial.entries_for(kind, lib)
    if not entries:
        return None
    return editorial.Topic(kind=kind, key=editorial.key_of(kind, entries[0]), data=entries[0])


def run(out: Path) -> int:
    import shutil
    if out.exists():
        shutil.rmtree(out)
    cfg = load_config()
    lib = editorial.load_library(cfg)
    today = Date.today()
    records, all_paths = [], []
    number = 0
    for kind in KIND_ORDER:
        topic = _sample_topic(kind, lib)
        if topic is None:
            log(f"({kind}: content/*.toml 에 자료가 없어서 건너뜀)")
            continue
        number += 1
        cp = copy_mod.build_copy(topic, cfg)
        paths = render_topic(topic, number, cfg, out / "posts" / f"{number:03d}")
        contact_sheet(paths, out / f"preview_No{number}.jpg")
        (out / f"caption_No{number}.txt").write_text(cp.caption, encoding="utf-8")
        render_pin(topic, number, cfg, out / "pins" / f"{number:03d}.jpg")
        records.append({
            "number": number, "date": today.isoformat(), "source": topic.kind, "key": topic.key,
            "title": topic.title, "folder": f"{number:03d}", "slides": len(paths),
            "caption": cp.caption, "hook": cp.hook, "bullets": cp.bullets,
            "buttons": cp.buttons, "article_blocks": cp.article_blocks, "sources": cp.sources,
            "status": "published",
        })
        all_paths += paths
    build_link_page(records, cfg, out, updated=today.isoformat())
    build_pinterest(records, cfg, out, "https://your-name.github.io/")  # render_pin already wrote out/pins
    log(f"데모 완료 → {out}/ (카드 {len(all_paths)}장, 링크 페이지 index.html)")
    return 0

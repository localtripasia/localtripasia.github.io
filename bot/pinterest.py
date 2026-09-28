"""Pinterest without the API: an RSS feed + one landing page per post, on your GitHub Pages site.

Pinterest (business account, claimed website) checks the feed and publishes new items as Pins
within ~24 hours. Every Pin links to /p/NNN.html on your site: the full card content as an
article, its affiliate buttons (Agoda/Trip.com for hotels, Klook for tours/passes/eSIM) and its
sources. Every post has sources, since content/*.toml requires >= 2 per entry.
"""
from __future__ import annotations

import html
import shutil
from datetime import datetime, time as dtime
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ARTICLE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · {site}</title>
<meta name="description" content="{desc}">
{verify}<meta property="og:title" content="{title}">
<meta property="og:image" content="{image_abs}">
<meta property="og:description" content="{desc}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,600;9..40,700&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
:root{{--bg:#F6EFE3;--card:#FFFFFF;--ink:#15233F;--muted:#6B6157;--accent:#E0483A;--soft:#FBE3DF;--teal:#1F8A84;--teal-soft:#DCEEEC;--line:#E4D9C8}}
@media (prefers-color-scheme: dark){{:root{{--bg:#15233F;--card:#1D2E52;--ink:#F6EFE3;--muted:#B8C0D6;--accent:#F0776C;--soft:#3A2A32;--teal:#59C6BE;--teal-soft:#1E3A38;--line:#2C3C61}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'DM Sans',system-ui,-apple-system,sans-serif;line-height:1.55}}
.wrap{{max-width:620px;margin:0 auto;padding:28px 16px 56px}}
.back{{color:var(--muted);text-decoration:none;font-size:14px}}
img{{width:100%;height:auto;border-radius:18px;display:block;margin:16px 0}}
.tag{{display:inline-block;font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:4px 10px;border-radius:999px;background:var(--soft);color:var(--accent)}}
h1{{font-family:'DM Serif Display',serif;font-weight:400;font-size:32px;line-height:1.15;margin:12px 0 10px}}
h2{{font-family:'DM Serif Display',serif;font-weight:400;font-size:23px;margin:26px 0 6px}}
ul,ol{{padding-left:22px}}
li{{margin:4px 0}}
.btns{{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}}
.btns a{{flex:1 1 140px;text-align:center;padding:12px;border-radius:12px;font-weight:700;font-size:14px;text-decoration:none;background:var(--soft);color:var(--accent)}}
.btns a.teal{{background:var(--teal-soft);color:var(--teal)}}
.note{{font-size:13px;color:var(--muted)}}
details{{margin-top:22px;font-size:14px;color:var(--muted)}}
details a{{color:inherit}}
</style>
</head>
<body><div class="wrap">
<a class="back" href="../">← All posts from @{handle}</a>
<img src="../pins/{folder}.jpg" alt="{title}">
<span class="tag">{tag} · No.{number}</span>
<h1>{title}</h1>
{body}
{buttons}
{disclosure}
{sources}
</div></body></html>
"""


def _buttons_html(buttons: list[dict]) -> str:
    if not buttons:
        return ""
    esc = html.escape
    out = []
    for b in buttons:
        cls = ' class="teal"' if b.get("class") == "teal" else ""
        out.append(f'<a{cls} href="{esc(b["url"])}" target="_blank" rel="sponsored noopener">{esc(b["label"])} →</a>')
    return f'<div class="btns">{"".join(out)}</div>'


def _sources_html(sources: list[str]) -> str:
    if not sources:
        return ""
    esc = html.escape
    items = "".join(f'<li><a href="{esc(s)}" target="_blank" rel="noopener">{esc(s)}</a></li>' for s in sources[:6])
    return f"<details><summary>Sources</summary><ul>{items}</ul></details>"


def _article_page(p: dict, cfg, verify_tag: str, image_abs: str) -> str:
    esc = html.escape
    title = p.get("hook") or p["title"]
    desc = " ".join(p.get("bullets") or [])[:300] or title
    buttons = p.get("buttons") or []
    disclosure = ('<p class="note">#ad · Booking links are affiliate links: we may earn a small commission '
                  "if you book, at no extra cost to you. Prices and availability can change.</p>") if buttons else ""
    body = "".join(f"<h2>{esc(h)}</h2><p>{esc(t)}</p>" if isinstance(t, str) else
                   f"<h2>{esc(h)}</h2><ul>{''.join(f'<li>{esc(x)}</li>' for x in t)}</ul>"
                   for h, t in (p.get("article_blocks") or []))
    return ARTICLE.format(
        title=esc(title), site=esc(cfg.brand_name), desc=esc(desc[:300]), verify=verify_tag, image_abs=esc(image_abs),
        handle=esc(cfg.handle), folder=p.get("folder") or f"{p['number']:03d}", number=p["number"],
        tag=esc(p.get("source", "").replace("_", " ").title() or "Guide"), body=body,
        buttons=_buttons_html(buttons), disclosure=disclosure, sources=_sources_html(p.get("sources") or []),
    )


def build_pinterest(posts: list[dict], cfg, out_dir: Path, site_url: str, pins_dir: Path | None = None) -> None:
    """Writes out_dir/p/NNN.html, out_dir/feed.xml and copies pin images into out_dir/pins/."""
    esc = html.escape
    base = (site_url or "").rstrip("/") + "/"
    verify = cfg.pinterest.get("domain_verify", "")
    verify_tag = f'<meta name="p:domain_verify" content="{esc(verify)}">\n' if verify else ""
    (out_dir / "p").mkdir(parents=True, exist_ok=True)
    (out_dir / "pins").mkdir(parents=True, exist_ok=True)

    if pins_dir and pins_dir.exists():
        for f in pins_dir.glob("*.jpg"):
            shutil.copy2(f, out_dir / "pins" / f.name)

    ordered = sorted(posts, key=lambda p: p["number"], reverse=True)
    items = []
    tz = ZoneInfo(cfg.timezone)
    for p in ordered:
        folder = p.get("folder") or f"{p['number']:03d}"
        if not (out_dir / "pins" / f"{folder}.jpg").exists():
            continue  # posts from before Pinterest was set up
        title = p.get("hook") or p["title"]
        page = _article_page(p, cfg, verify_tag, f"{base}pins/{folder}.jpg")
        (out_dir / "p" / f"{folder}.html").write_text(page, encoding="utf-8")
        linked = bool(p.get("buttons"))
        desc = " ".join(f"{b}." for b in (p.get("bullets") or [])[:3]) + (" #ad affiliate links" if linked else "")
        items.append(_feed_item(p, base, folder, title, desc, tz, out_dir))
        if len(items) >= 25:
            break
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">'
        f"<channel><title>{esc(cfg.brand_name)}</title><link>{esc(base)}</link>"
        f"<description>{esc(cfg.tagline)}</description><language>en</language>"
        + "".join(items) + "</channel></rss>\n"
    )
    (out_dir / "feed.xml").write_text(feed, encoding="utf-8")


def _feed_item(p: dict, base: str, folder: str, title: str, desc: str, tz, out_dir: Path) -> str:
    esc = html.escape
    day = datetime.combine(datetime.fromisoformat(p["date"]).date(), dtime(12, 0), tz)
    return (
        "<item>"
        f"<title>{esc(title[:100])}</title>"
        f"<link>{esc(base)}p/{folder}.html</link>"
        f"<guid isPermaLink=\"true\">{esc(base)}p/{folder}.html</guid>"
        f"<description>{esc(desc[:480])}</description>"
        f"<pubDate>{format_datetime(day)}</pubDate>"
        f"<enclosure url=\"{esc(base)}pins/{folder}.jpg\" type=\"image/jpeg\" length=\"{(out_dir / 'pins' / f'{folder}.jpg').stat().st_size}\"/>"
        f"<media:content url=\"{esc(base)}pins/{folder}.jpg\" medium=\"image\" type=\"image/jpeg\"/>"
        "</item>"
    )


def verify_meta(cfg) -> str:
    verify = cfg.pinterest.get("domain_verify", "")
    return f'<meta name="p:domain_verify" content="{html.escape(verify)}">' if verify else ""

"""Builds the "link in bio" page (GitHub Pages): every post, newest first, with its number.

Every post links to its full guide (p/NNN.html); posts with a hotel/tour pick also show the
booking buttons right here so people don't have to tap through for the common case."""
from __future__ import annotations

import html
from pathlib import Path

from .pinterest import verify_meta

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · Guides & picks</title>
<meta name="description" content="{tagline}">
<meta name="robots" content="index,follow">
{verify}
<link rel="alternate" type="application/rss+xml" title="{title}" href="feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,600;9..40,700&family=DM+Serif+Display&display=swap" rel="stylesheet">
<style>
:root{{--bg:#F6EFE3;--card:#FFFFFF;--ink:#15233F;--muted:#6B6157;--accent:#E0483A;--soft:#FBE3DF;--teal:#1F8A84;--teal-soft:#DCEEEC;--line:#E4D9C8}}
@media (prefers-color-scheme: dark){{:root{{--bg:#15233F;--card:#1D2E52;--ink:#F6EFE3;--muted:#B8C0D6;--accent:#F0776C;--soft:#3A2A32;--teal:#59C6BE;--teal-soft:#1E3A38;--line:#2C3C61}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:'DM Sans',system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:560px;margin:0 auto;padding:40px 16px 64px}}
header{{text-align:center}}
.mark{{width:76px;height:76px;border-radius:50%;background:var(--accent);color:#fff;display:grid;place-items:center;font-family:'DM Serif Display',serif;font-size:34px;margin:0 auto 14px}}
h1{{font-family:'DM Serif Display',serif;font-weight:400;font-size:34px;line-height:1.1;margin:0}}
.handle{{color:var(--muted);margin:6px 0 0;font-size:15px}}
.handle a{{color:inherit}}
.tagline{{margin:10px 0 0;font-size:16px}}
.note{{font-size:13px;line-height:1.45;color:var(--muted);background:var(--card);border-radius:14px;padding:12px 14px;margin:22px 0 16px}}
.search{{width:100%;padding:14px 16px;border-radius:14px;border:1.5px solid var(--line);background:var(--card);color:var(--ink);font:inherit;font-size:16px}}
.search:focus{{outline:2px solid var(--accent);outline-offset:1px}}
ul{{list-style:none;padding:0;margin:14px 0 0;display:grid;gap:10px}}
li .card{{display:block;background:var(--card);border-radius:18px;padding:14px 16px;border:1px solid var(--line)}}
.btns{{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}}
.btns a{{display:block;flex:1 1 140px;max-width:100%;border:0;padding:10px 12px;border-radius:12px;font-weight:700;font-size:14px;line-height:1.25;text-align:center;background:var(--soft);color:var(--accent);text-decoration:none}}
.btns a.teal{{background:var(--teal-soft);color:var(--teal)}}
.num{{font-family:'DM Serif Display',serif;font-size:26px;min-width:66px;color:var(--accent);display:inline-block}}
.meta{{flex:1;min-width:0}}
.tag{{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:3px 8px;border-radius:999px;background:var(--soft);color:var(--accent)}}
.new{{margin-left:6px;background:var(--ink);color:var(--bg)}}
.name{{font-weight:600;font-size:16px;line-height:1.3;margin-top:5px}}
.brand{{font-size:13px;color:var(--muted);margin-top:2px}}
.brand a{{color:var(--accent);font-weight:600}}
.empty{{text-align:center;color:var(--muted);padding:36px 0}}
footer{{text-align:center;font-size:12px;color:var(--muted);margin-top:28px}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="mark" aria-hidden="true">{initial}</div>
  <h1>{title}</h1>
  <p class="handle"><a href="https://www.instagram.com/{handle}/">@{handle}</a></p>
  <p class="tagline">{tagline}</p>
</header>
<p class="note">Find the number from the post (like <b>No.12</b>) below. These are affiliate links: we may earn a small commission if you book, at no extra cost to you. Prices and availability can change.</p>
<input class="search" id="q" type="search" inputmode="search" placeholder="Search a number or place…" aria-label="Search posts">
<ul id="list">
{items}
</ul>
<p class="empty" id="empty" hidden>No match. Try just the number, like 12.</p>
<footer>Updated {updated}</footer>
</div>
<script>
const q=document.getElementById('q'),items=[...document.querySelectorAll('#list li')],empty=document.getElementById('empty');
q.addEventListener('input',()=>{{const v=q.value.toLowerCase().replace(/no\\.?\\s*/,'').trim();let n=0;
items.forEach(li=>{{const ok=!v||li.dataset.num===v||li.dataset.s.includes(v);li.hidden=!ok;if(ok)n++;}});empty.hidden=n>0;}});
</script>
</body>
</html>
"""


def _row(p: dict, newest: bool) -> str:
    esc = html.escape
    folder = p.get("folder") or f"{p['number']:03d}"
    tag = p.get("source", "").replace("_", " ").title() or "Guide"
    search = f"{p['number']} {p['title']}".lower()
    new_tag = '<span class="tag new">New</span>' if newest else ""
    btns = p.get("buttons") or []
    btns_html = ""
    if btns:
        out = []
        for b in btns:
            cls = ' class="teal"' if b.get("class") == "teal" else ""
            out.append(f'<a{cls} href="{esc(b["url"])}" target="_blank" rel="sponsored noopener">{esc(b["label"])} →</a>')
        btns_html = f'<span class="btns">{"".join(out)}</span>'
    return (
        f'<li data-num="{p["number"]}" data-s="{esc(search)}"><div class="card">'
        f'<span class="num">No.{p["number"]}</span> '
        f'<span class="meta"><span class="tag">{esc(tag)}</span>{new_tag}'
        f'<span class="name">{esc(p["title"])}</span>'
        f'<span class="brand">{esc(p.get("date", ""))} · <a href="p/{folder}.html">Read the guide</a></span>'
        f'{btns_html}</span></div></li>'
    )


def build_link_page(posts: list[dict], cfg, out_dir: Path, updated: str) -> Path:
    esc = html.escape
    ordered = sorted(posts, key=lambda p: p["number"], reverse=True)
    rows = [_row(p, i == 0) for i, p in enumerate(ordered)]
    if not rows:
        rows.append('<li class="empty">First posts are coming soon.</li>')
    page = TEMPLATE.format(
        title=esc(cfg.brand_name),
        tagline=esc(cfg.tagline),
        handle=esc(cfg.handle),
        initial=esc(cfg.brand_name[:1].upper() or "L"),
        items="\n".join(rows),
        updated=esc(updated),
        verify=verify_meta(cfg),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(page, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")
    return path

"""Command line entry point.

  python -m bot demo                 # preview cards with today's content (no keys needed)
  python -m bot check                # test Naver / Agoda / Instagram connections
  python -m bot prepare [--dry-run]  # today's post, picked by config.toml [series]
  python -m bot publish --site-url https://you.github.io/repo/
  python -m bot refresh-token --out token.txt
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import date as Date
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import copy as copy_mod
from . import editorial, reels, series
from .config import load_config
from .instagram import Instagram, wait_for_urls
from .linkpage import build_link_page
from .pinterest import build_pinterest
from .render import render_pin, render_topic
from .state import State
from .util import add_summary, log, scrub, set_output, warn


def _today(cfg, override: str | None) -> Date:
    if override:
        return Date.fromisoformat(override)
    return datetime.now(ZoneInfo(cfg.timezone)).date()


def _site_url(cfg) -> str:
    return os.environ.get("SITE_URL", "").strip() or cfg.pinterest.get("site_url", "")


def _post_record(topic, cp, number: int, today: Date, slides: int) -> dict:
    return {
        "number": number, "date": today.isoformat(), "source": topic.kind, "key": topic.key,
        "title": topic.title, "folder": f"{number:03d}", "slides": slides,
        "caption": cp.caption, "hook": cp.hook, "bullets": list(cp.bullets[:3]),
        "buttons": cp.buttons, "article_blocks": cp.article_blocks, "sources": cp.sources,
        "status": "prepared",
    }


def cmd_prepare(args, cfg=None) -> int:
    cfg = cfg or load_config()
    state = State(cfg.state_file)
    today = _today(cfg, args.date)
    set_output("has_post", "false")
    set_output("deploy", "false")
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)

    if args.source == "site":
        posts = state.published
        build_link_page(posts, cfg, out, updated=today.isoformat())
        build_pinterest(posts, cfg, out, _site_url(cfg), pins_dir=cfg.root / "pins")
        set_output("deploy", "true")
        log(f"링크 페이지만 준비했어요 (게시물 {len(posts)}개, 인스타 게시 없음).")
        add_summary(f"### 링크 페이지만 새로 올려요\n- 지금까지 게시물 {len(posts)}개\n- 인스타에는 아무것도 올리지 않아요.")
        return 0

    ppd = series.posts_per_day(cfg)
    done_today = sum(1 for p in state.published if p.get("date") == today.isoformat())
    if not args.dry_run and done_today >= ppd:
        log(f"{today} 에는 이미 {done_today}개 게시했어요 (하루 {ppd}개). 건너뜀.")
        return 0

    state.drop_unpublished()
    number = state.next_number()
    lib = editorial.load_library(cfg)

    forced = args.source if args.source in series.SERIES_NAMES else None
    if forced:
        plan, order = forced, [forced, series.FALLBACK_SERIES]
    else:
        planned = series.plan_order(cfg, state, today)
        plan, order = planned if planned else (series.FALLBACK_SERIES, [series.FALLBACK_SERIES])
    order = list(dict.fromkeys(order))
    log(f"오늘({today}) 계획: {plan} → 순서: {', '.join(order[:6])}")

    made = None
    for step in order:
        topic = editorial.next_topic(step, lib, state, today, cfg)
        if topic is None:
            continue
        try:
            cp = copy_mod.build_copy(topic, cfg)
            paths = render_topic(topic, number, cfg, out / "posts" / f"{number:03d}")
        except Exception as exc:
            warn(f"'{step}' 준비 중 오류, 다른 종류로 넘어가요: {exc}")
            continue
        made = {"topic": topic, "cp": cp, "paths": paths}
        if step != order[0]:
            log(f"'{order[0]}' 은 올릴 게 없어서 '{step}' 로 대신 올려요")
        break

    if not made:
        warn("오늘 올릴 게 없어요. content/ 폴더에 자료를 추가해주세요.")
        add_summary("### 오늘은 게시할 내용이 없어요\ncontent/ 폴더에 도시·동네·코스 자료를 추가해주세요.")
        return 0

    topic, cp, paths = made["topic"], made["cp"], made["paths"]
    post = _post_record(topic, cp, number, today, len(paths))
    try:
        render_pin(topic, number, cfg, (out / "pins" if args.dry_run else cfg.root / "pins") / f"{number:03d}.jpg")
    except Exception as exc:
        warn(f"핀터레스트 이미지를 만들지 못했어요 (인스타 게시는 계속): {exc}")

    reel_note = ""
    if reels.is_reel_day(cfg, today, getattr(args, "reel", None)):
        rec = reels.make_for_post(cfg, post, paths, out, manual=reels.settings(cfg)["mode"] == "manual")
        if rec:
            post["reel"] = rec
            site = _site_url(cfg).rstrip("/")
            reel_note = (f"- 릴스: {rec['seconds']}초 · 음악 {rec['track'] or '없음'} → 릴스 먼저, 이어서 카드뉴스 게시\n"
                         if rec["mode"] == "auto" else
                         f"- 릴스(수동): 음악 없는 영상 → {site + '/' if site else ''}{rec['video']} 를 받아 인스타 앱에서 음악을 붙여 올려주세요\n")

    build_link_page(state.published + [post], cfg, out, updated=today.isoformat())
    build_pinterest(state.published + [post], cfg, out, _site_url(cfg),
                    pins_dir=None if args.dry_run else cfg.root / "pins")
    if not args.dry_run:
        state.posts.append(post)
        state.save()
    set_output("has_post", "true")
    set_output("deploy", "false" if args.dry_run else "true")
    set_output("number", str(number))
    log(f"No.{number} 준비 완료 ({topic.kind}): {post['title']}")
    add_summary(
        f"### {'[미리보기] ' if args.dry_run else ''}No.{number} · {topic.kind}\n"
        f"- 제목: **{post['title']}**\n"
        + reel_note
        + f"\n카드 이미지는 이 페이지 아래 **Artifacts → preview-images** 에서 받을 수 있어요.\n\n"
        f"<details><summary>캡션 보기</summary>\n\n```\n{post['caption']}\n```\n</details>\n"
    )
    return 0


def cmd_publish(args, cfg=None, session=None, sleep=None) -> int:
    cfg = cfg or load_config()
    state = State(cfg.state_file)
    post = state.pending()
    if not post:
        log("게시할 준비된 글이 없어요.")
        return 0
    if not cfg.ig_token:
        warn("IG_ACCESS_TOKEN 이 없어서 인스타 게시는 건너뛰었어요 (카드·링크 페이지만 준비됨).")
        return 0
    site = args.site_url.rstrip("/") + "/"
    urls = [f"{site}posts/{post['folder']}/{i}.jpg" for i in range(1, post["slides"] + 1)]
    kw = {"sleep": sleep} if sleep else {}
    reel = post.get("reel") or {}
    reel_done = reel.get("status") == "published"
    try:
        wait_for_urls(urls, session=session, **kw)
        ig = Instagram(cfg.ig_token, cfg.instagram.get("api_host", "graph.instagram.com"),
                       cfg.instagram.get("api_version", "v24.0"), session=session, **kw)
        ig_id = cfg.ig_user_id or ig.account_id()[0]
        if reel.get("mode") == "auto" and not reel_done:
            reel_done = _publish_reel(cfg, ig, ig_id, post, site, state, session, kw)
        res = ig.publish_carousel(ig_id, urls, post["caption"])
    except Exception as exc:
        msg = scrub(str(exc), cfg.ig_token)
        if reel_done:
            post.update(status="published", carousel_error=msg[:300],
                        published_at=datetime.now(ZoneInfo(cfg.timezone)).isoformat(timespec="minutes"))
            state.save()
            add_summary(f"### ⚠️ 릴스는 올라갔는데 카드뉴스 게시 실패\n`{msg}`")
            return 1
        post.update(status="failed", error=msg[:300])
        state.save()
        print(f"::error::인스타 게시 실패: {msg}" if os.environ.get("GITHUB_ACTIONS") else f"인스타 게시 실패: {msg}")
        add_summary(f"### ❌ 인스타 게시 실패\n`{msg}`\n\n내일 같은 주제로 다시 시도해요.")
        return 1
    post.update(status="published", ig_media_id=res["media_id"], permalink=res["permalink"],
                published_at=datetime.now(ZoneInfo(cfg.timezone)).isoformat(timespec="minutes"))
    post.pop("error", None)
    state.save()
    add_summary(f"### ✅ 인스타 게시 완료: No.{post['number']}\n{res['permalink'] or res['media_id']}")
    return 0


def _publish_reel(cfg, ig, ig_id: str, post: dict, site: str, state, session, kw) -> bool:
    from .reels import reel_caption, settings
    reel = post["reel"]
    try:
        wait_for_urls([site + reel["video"]], session=session, kinds=("video/",), **kw)
        res = ig.publish_reel(ig_id, site + reel["video"], reel_caption(post["caption"]),
                              cover_url=site + reel["cover"], audio_name=settings(cfg)["audio_name"])
    except Exception as exc:
        msg = scrub(str(exc), cfg.ig_token)
        reel.update(status="failed", error=msg[:300])
        state.save()
        warn(f"릴스 게시 실패 (카드뉴스는 계속 올려요): {msg}")
        add_summary(f"### ⚠️ 릴스 게시 실패 (카드뉴스는 계속)\n`{msg}`")
        return False
    reel.update(status="published", media_id=res["media_id"], permalink=res["permalink"])
    reel.pop("error", None)
    state.save()
    add_summary(f"### 🎬 릴스 게시 완료\n{res['permalink'] or res['media_id']}")
    return True


def cmd_check(args, cfg=None) -> int:
    cfg = cfg or load_config()
    state = State(cfg.state_file)
    today = _today(cfg, None)
    ok = True
    lines = ["### 연결 점검"]

    if cfg.naver_keys:
        from .weekly import naver_trends
        try:
            rows = naver_trends(cfg, today)
            lines.append(f"- 네이버 검색 트렌드: 연결됨 ({len(rows)}개 목적지)")
        except Exception as exc:
            ok = False
            lines.append(f"- ❌ 네이버 API 오류: {exc}")
    else:
        lines.append("- 네이버 API: 키 없음 → '이번 주 현지인이 가는 곳'에서 한국 쪽이 빠져요")

    lines.append(f"- e-Stat(일본 숙박통계): {'앱 ID 있음' if cfg.estat_app_id else '앱 ID 없음 → 일본 쪽이 빠져요'}")
    lines.append(f"- 아고다: {'Site ID 있음' if cfg.agoda_site_id else '제휴 승인 전 → 일반 링크로 대신 나가요'}")
    lines.append(f"- 트립닷컴: {'키 있음' if cfg.tripcom_key else '제휴 승인 전 → 일반 링크로 대신 나가요'}")
    lines.append(f"- 클룩(Involve Asia): {'키 있음' if cfg.klook_key else '제휴 승인 전 → 일반 링크로 대신 나가요'}")

    if cfg.ig_token:
        try:
            ig = Instagram(cfg.ig_token, cfg.instagram.get("api_host", "graph.instagram.com"), cfg.instagram.get("api_version", "v24.0"))
            ig_id, username = ig.account_id()
            lines.append(f"- 인스타: @{username} 연결됨")
        except Exception as exc:
            ok = False
            lines.append(f"- ❌ 인스타 토큰 오류: {scrub(str(exc), cfg.ig_token)}")
    else:
        lines.append("- 인스타: 토큰 없음 → 게시 없이 미리보기만")

    lib = editorial.load_library(cfg)
    left = editorial.remaining(lib, state)
    lines.append(f"- 자료: 도시 {len(lib.cities)} · 동네비교 {len(lib.areas)} · 교통 {len(lib.passes)}"
                 f" · 코스 {len(lib.routes)} · 계절 {len(lib.seasons)} · 단어 {len(lib.words)}")
    lines.append(f"  - 아직 안 올린 것: " + " · ".join(f"{k} {v}" for k, v in left.items()))
    from .series import month_summary, series_cfg
    if series_cfg(cfg):
        lines.append(f"- 이번 달 진행 (올림/목표): {month_summary(cfg, state, today)}")
    lines.append(f"- 지금까지 게시: {len(state.published)}개")
    text = "\n".join(lines)
    log(text)
    add_summary(text)
    return 0 if ok else 1


def cmd_refresh_token(args) -> int:
    cfg = load_config()
    if not cfg.ig_token:
        print("IG_ACCESS_TOKEN 이 없어요.", file=sys.stderr)
        return 1
    ig = Instagram(cfg.ig_token, cfg.instagram.get("api_host", "graph.instagram.com"))
    data = ig.refresh_token()
    new = data["access_token"]
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{new}")
    Path(args.out).write_text(new, encoding="utf-8")
    days = int(data.get("expires_in", 0)) // 86400
    log(f"토큰 갱신 완료: 앞으로 약 {days}일 유효 ({'새 토큰' if new != cfg.ig_token else '같은 토큰 연장'})")
    return 0


def cmd_demo(args) -> int:
    from . import demo
    return demo.run(Path(args.out))


def cmd_weekly(args, cfg=None, session=None) -> int:
    """Monday job: save this week's Naver trend + e-Stat accommodation snapshot for the
    Thursday 'this week locals are going' post. Commits data/trend_latest.json."""
    from . import weekly
    cfg = cfg or load_config()
    today = _today(cfg, args.date)
    data = weekly.compute(cfg, today, session=session)
    weekly.save(cfg, data)
    log(f"이번 주 트렌드 저장: 한국 {len(data.get('korea', []))}개 · 일본 {len(data.get('japan', []))}개"
        f" (일본 자료 기준월: {data.get('japan_month') or '없음'})")
    add_summary(f"### 이번 주 트렌드\n- 한국(네이버): {len(data.get('korea', []))}개\n"
                f"- 일본(e-Stat, {data.get('japan_month') or '자료 없음'}): {len(data.get('japan', []))}개")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m bot")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("--out", default="site")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--source", default="auto", choices=["auto", *series.SERIES_NAMES, "site"])
    a.add_argument("--date", default=None, help="YYYY-MM-DD (테스트용)")
    a.add_argument("--reel", default="auto", choices=["auto", "yes", "no"])
    b = sub.add_parser("publish")
    b.add_argument("--site-url", required=True)
    sub.add_parser("check")
    r = sub.add_parser("refresh-token")
    r.add_argument("--out", required=True)
    dm = sub.add_parser("demo")
    dm.add_argument("--out", default="demo_output")
    w = sub.add_parser("weekly")
    w.add_argument("--date", default=None, help="YYYY-MM-DD (테스트용)")
    args = p.parse_args(argv)
    if getattr(args, "source", None) == "auto":
        args.source = None
    if getattr(args, "reel", None) == "auto":
        args.reel = None
    return {
        "prepare": cmd_prepare,
        "publish": cmd_publish,
        "check": cmd_check,
        "refresh-token": cmd_refresh_token,
        "demo": cmd_demo,
        "weekly": cmd_weekly,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())

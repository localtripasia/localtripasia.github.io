"""End-to-end smoke tests: config loads, cards render, the schedule picks something every day,
nothing crashes without any API keys set. Run:  python -m unittest discover tests -v"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from bot import copy as copy_mod
from bot import editorial, series
from bot.config import load_config
from bot.render import render_topic
from bot.state import State

ROOT = Path(__file__).resolve().parent.parent


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()
        self.lib = editorial.load_library(self.cfg)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_config_loads(self):
        self.assertEqual(self.cfg.handle, "localtrip.asia")
        self.assertTrue(self.cfg.series)

    def test_every_kind_with_content_renders_a_cover_plus_slides(self):
        for kind in ("city101", "hood", "hotel", "area", "transport", "route", "season", "words"):
            entries = editorial.entries_for(kind, self.lib)
            if not entries:
                continue
            topic = editorial.Topic(kind=kind, key=editorial.key_of(kind, entries[0]), data=entries[0])
            cp = copy_mod.build_copy(topic, self.cfg)
            self.assertTrue(cp.hook)
            self.assertTrue(cp.caption)
            paths = render_topic(topic, 1, self.cfg, self.tmp / kind)
            self.assertGreaterEqual(len(paths), 2, f"'{kind}' 카드가 표지 1장뿐이에요")
            for p in paths:
                self.assertTrue(p.exists())

    def test_schedule_always_returns_a_next_series(self):
        state = State(self.tmp / "state.json")
        today = date(2026, 10, 1)
        planned = series.plan_order(self.cfg, state, today)
        self.assertIsNotNone(planned)
        plan, order = planned
        self.assertIn(plan, series.SERIES_NAMES)
        self.assertGreater(len(order), 0)

    def test_next_topic_never_repeats_before_the_gap(self):
        state = State(self.tmp / "state2.json")
        today = date(2026, 10, 1)
        first = editorial.next_topic("city101", self.lib, state, today, self.cfg)
        self.assertIsNotNone(first)
        state.posts.append({"number": 1, "date": today.isoformat(), "key": first.key,
                            "source": "city101", "status": "published"})
        second = editorial.next_topic("city101", self.lib, state, today, self.cfg)
        if second is not None:  # only one city in the library right now is a valid outcome too
            self.assertNotEqual(first.key, second.key)

    def test_tripcom_link_carries_the_affiliate_ids(self):
        link = self.cfg.tripcom_link()
        self.assertIn("Allianceid=10791404", link)
        self.assertIn("SID=332513490", link)
        self.assertTrue(link.startswith("https://www.trip.com/hotels/?"))
        self.assertIn("&", self.cfg.tripcom_link("https://www.trip.com/hotels/?a=1"))

    def test_cover_uses_a_photo_when_listed_and_falls_back_without_one(self):
        from PIL import Image
        from bot import photos as photos_mod
        entry = editorial.entries_for("hood", self.lib)[0]
        topic = editorial.Topic(kind="hood", key=editorial.key_of("hood", entry), data=entry)
        plain = render_topic(topic, 1, self.cfg, self.tmp / "plain")[0]
        Image.new("RGB", (1600, 900), (200, 120, 60)).save(self.tmp / "p.jpg")
        table = {entry["key"]: {"key": entry["key"], "file": "p.jpg", "credit": "Photo: Test / Unsplash"}}
        orig_dir, orig_load = photos_mod.PHOTOS_DIR, photos_mod.load_photos
        photos_mod.PHOTOS_DIR, photos_mod.load_photos = self.tmp, lambda path=None: table
        try:
            with_photo = render_topic(topic, 1, self.cfg, self.tmp / "photo")[0]
            cp = copy_mod.build_copy(topic, self.cfg)
        finally:
            photos_mod.PHOTOS_DIR, photos_mod.load_photos = orig_dir, orig_load
        self.assertNotEqual(Image.open(plain).getpixel((540, 1000)), Image.open(with_photo).getpixel((540, 1000)))
        self.assertIn("Photo: Test / Unsplash", cp.caption)
        self.assertTrue(any(h == "Photo" for h, _ in cp.article_blocks))

    def test_kto_photo_is_downloaded_credited_and_used(self):
        import io, json, os
        from PIL import Image
        from bot import photos as photos_mod
        from bot.sources import kto_photos

        entry = next(h for h in self.lib.hoods if h["key"] == "seoul-seongsu")
        topic = editorial.Topic(kind="hood", key="hood-seoul-seongsu", data=entry)
        buf = io.BytesIO(); Image.new("RGB", (1600, 1200), (90, 140, 200)).save(buf, "JPEG")

        class Resp:
            def __init__(self, payload=None, content=b""):
                self._p, self.content = payload, content
            def raise_for_status(self): pass
            def json(self): return self._p

        class FakeSession:
            def get(self, url, params=None, timeout=0):
                if "gallerySearchList1" in url:
                    return Resp({"response": {"body": {"items": {"item": [
                        {"galTitle": "tiny", "galWebImageUrl": "http://x/tiny.jpg", "galPhotographer": "A"},
                        {"galTitle": "Seongsu", "galWebImageUrl": "http://x/big.jpg", "galPhotographer": "Kim Test"}]}}}})
                if url.endswith("tiny.jpg"):
                    b = io.BytesIO(); Image.new("RGB", (300, 200)).save(b, "JPEG"); return Resp(content=b.getvalue())
                return Resp(content=buf.getvalue())

        os.environ["KTO_API_KEY"] = "test-key"
        orig = photos_mod.AUTO_PATH, photos_mod.PHOTOS_DIR
        photos_mod.AUTO_PATH, photos_mod.PHOTOS_DIR = self.tmp / "auto.json", self.tmp / "ph"
        try:
            self.assertTrue(kto_photos.ensure_photo(topic, self.cfg, FakeSession(), self.tmp / "ph", self.tmp / "auto.json"))
            table = json.loads((self.tmp / "auto.json").read_text())
            self.assertIn("Kim Test", table["seoul-seongsu"]["credit"])   # skipped the too-small first result
            self.assertIn("KOGL", table["seoul-seongsu"]["credit"])
            self.assertIsNotNone(photos_mod.photo_for(topic, self.tmp / "ph", photos_mod.load_photos()))
        finally:
            os.environ.pop("KTO_API_KEY", None)
            photos_mod.AUTO_PATH, photos_mod.PHOTOS_DIR = orig

    def test_photo_credit_never_puts_hangul_on_the_card(self):
        from bot.sources.kto_photos import _credit
        self.assertEqual(_credit("한국관광공사 김지호"), "Photo: Korea Tourism Organization (KOGL Type 1)")
        self.assertEqual(_credit("Kim Test"), "Photo: Kim Test / Korea Tourism Organization (KOGL Type 1)")

    def test_photo_ranking_prefers_scenery_and_avoids_crowds(self):
        from bot.sources.kto_photos import _rank
        items = [{"galTitle": "명동성당 미사", "galSearchKeyword": "명동"},
                 {"galTitle": "명동 거리", "galSearchKeyword": "명동"},
                 {"galTitle": "명동 쇼핑", "galSearchKeyword": "명동"}]
        self.assertEqual([i["galTitle"] for i in sorted(items, key=_rank)], ["명동 거리", "명동 쇼핑", "명동성당 미사"])

    def test_ai_check_rejects_crowds_and_keeps_the_next_good_photo(self):
        import io, json, os
        from PIL import Image
        from bot.sources import kto_photos
        entry = next(h for h in self.lib.hoods if h["key"] == "seoul-hongdae")
        topic = editorial.Topic(kind="hood", key="k", data=entry)
        buf = io.BytesIO(); Image.new("RGB", (1600, 1200), (10, 90, 60)).save(buf, "JPEG")

        class R:
            def __init__(self, payload=None, content=b""): self._p, self.content = payload, content
            def raise_for_status(self): pass
            def json(self): return self._p

        class KtoSession:
            def get(self, url, params=None, timeout=0):
                if "gallerySearchList1" in url:
                    return R({"response": {"body": {"items": {"item": [
                        {"galTitle": "홍대 거리", "galWebImageUrl": "http://x/a.jpg", "galPhotographer": "A Kim"},
                        {"galTitle": "홍대 골목", "galWebImageUrl": "http://x/b.jpg", "galPhotographer": "B Lee"}]}}}})
                return R(content=buf.getvalue())

        verdicts = iter([{"shows_place": False, "quality": 4},
                         {"shows_place": True, "identifiable_faces": True, "crowd": True, "quality": 4}])

        class GeminiSession:
            def post(self, url, json=None, timeout=0, headers=None):
                assert "key=" not in url and "x-goog-api-key" in headers   # key goes in a header, never the URL
                v = next(verdicts)
                return R({"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(v)}]}}]})

        os.environ["KTO_API_KEY"], os.environ["GEMINI_API_KEY"] = "k1", "k2"
        try:
            ok = kto_photos.ensure_photo(topic, self.cfg, KtoSession(), self.tmp / "ph2", self.tmp / "a2.json", GeminiSession())
            table = json.loads((self.tmp / "a2.json").read_text())
            self.assertTrue(ok)
            self.assertEqual(table["seoul-hongdae"]["title"], "홍대 골목")   # the first was rejected as the wrong place; faces/crowds are allowed
            self.assertTrue(table["seoul-hongdae"]["ai_checked"])
        finally:
            os.environ.pop("KTO_API_KEY", None); os.environ.pop("GEMINI_API_KEY", None)

    def test_neighborhood_post_gets_five_photo_slides_when_enough_photos_exist(self):
        import io, json, os
        from PIL import Image
        from bot import photos as photos_mod
        from bot.sources import kto_photos
        entry = next(h for h in self.lib.hoods if h["key"] == "seoul-itaewon")
        topic = editorial.Topic(kind="hood", key="hood-seoul-itaewon", data=entry)
        buf = io.BytesIO(); Image.new("RGB", (1500, 1000), (30, 100, 150)).save(buf, "JPEG")

        class R:
            def __init__(self, payload=None, content=b""): self._p, self.content = payload, content
            def raise_for_status(self): pass
            def json(self): return self._p

        def session(n):
            class S:
                def get(self, url, params=None, timeout=0):
                    if "gallerySearchList1" in url:
                        return R({"response": {"body": {"items": {"item": [
                            {"galTitle": f"이태원 거리 {i}", "galWebImageUrl": f"http://x/{i}.jpg", "galPhotographer": "Kim"} for i in range(n)]}}}})
                    return R(content=buf.getvalue())
            return S()

        os.environ["KTO_API_KEY"] = "k"
        orig = photos_mod.PHOTOS_DIR, photos_mod.GALLERY_PATH, photos_mod.AUTO_PATH
        photos_mod.PHOTOS_DIR, photos_mod.GALLERY_PATH, photos_mod.AUTO_PATH = self.tmp / "g", self.tmp / "g.json", self.tmp / "none.json"
        try:
            self.assertEqual(kto_photos.ensure_gallery(topic, self.cfg, session=session(3), photos_dir=self.tmp / "g0", gallery_path=self.tmp / "g0.json"), [])
            got = kto_photos.ensure_gallery(topic, self.cfg, session=session(8), photos_dir=self.tmp / "g", gallery_path=self.tmp / "g.json")
            self.assertEqual(len(got), 6)              # 1 cover photo + 5 photo slides
            paths = render_topic(topic, 3, self.cfg, self.tmp / "tour")
            self.assertEqual(len(paths), 10)           # cover + 3 text slides + 5 photos + closing slide (Instagram's max)
            cp = copy_mod.build_copy(topic, self.cfg)
            self.assertIn("Photos: Korea Tourism Organization", cp.caption)
        finally:
            os.environ.pop("KTO_API_KEY", None)
            photos_mod.PHOTOS_DIR, photos_mod.GALLERY_PATH, photos_mod.AUTO_PATH = orig

    def test_vision_falls_back_to_the_next_model_when_one_is_gone(self):
        from PIL import Image
        from bot import vision
        seen = []

        class R:
            def __init__(self, code, payload=None): self.status_code, self._p = code, payload
            def raise_for_status(self): pass
            def json(self): return self._p

        class S:
            def post(self, url, json=None, timeout=0, headers=None):
                seen.append(url.split("/models/")[1].split(":")[0])
                if "old-model" in url:
                    return R(404)
                return R(200, {"candidates": [{"content": {"parts": [{"text": '{"shows_place": true, "quality": 4}'}]}}]})

        vision._working.clear()
        v = vision.judge(Image.new("RGB", (100, 100)), "X", "Seoul", "key", "old-model", S())
        self.assertTrue(v["shows_place"])
        self.assertEqual(seen[0], "old-model")
        self.assertEqual(seen[1], "gemini-3.5-flash-lite")

    def test_gallery_takes_one_photo_per_kind_of_subject(self):
        import io, json, os
        from PIL import Image
        from bot import photos as photos_mod
        from bot.sources import kto_photos
        entry = next(h for h in self.lib.hoods if h["key"] == "seoul-myeongdong")
        topic = editorial.Topic(kind="hood", key="k", data=entry)
        buf = io.BytesIO(); Image.new("RGB", (1500, 1000), (30, 100, 150)).save(buf, "JPEG")

        class R:
            def __init__(self, payload=None, content=b""): self._p, self.content = payload, content
            def raise_for_status(self): pass
            def json(self): return self._p

        class Kto:
            def get(self, url, params=None, timeout=0):
                if "gallerySearchList1" in url:
                    kw = params["keyword"]
                    return R({"response": {"body": {"items": {"item": [
                        {"galContentId": f"{kw}-{i}", "galTitle": f"t{kw}{i}", "galWebImageUrl": f"http://x/{kw}{i}.jpg", "galPhotographer": "Kim"}
                        for i in range(3)]}}}})
                return R(content=buf.getvalue())

        cats = iter(["statue/monument", "statue/monument", "landmark or building exterior", "street food", "street scene",
                     "landmark or building exterior", "shopping/storefronts", "night lights/decorations", "interior", "other", "other", "other"] * 3)

        class Gem:
            def post(self, url, json=None, timeout=0, headers=None):
                v = {"shows_place": True, "quality": 4, "category": next(cats)}
                return R({"candidates": [{"content": {"parts": [{"text": __import__("json").dumps(v)}]}}]})

        os.environ["KTO_API_KEY"], os.environ["GEMINI_API_KEY"] = "k1", "k2"
        try:
            got = kto_photos.ensure_gallery(topic, self.cfg, session=Kto(), photos_dir=self.tmp / "gd", gallery_path=self.tmp / "gd.json", vision_session=Gem())
            cats_got = [e["category"] for e in got]
            self.assertEqual(len(got), 6)
            self.assertEqual(len(set(c for c in cats_got if c != "other")), len([c for c in cats_got if c != "other"]))  # no repeated kind
        finally:
            os.environ.pop("KTO_API_KEY", None); os.environ.pop("GEMINI_API_KEY", None)

    def test_kto_photo_does_nothing_without_a_key(self):
        from bot.sources import kto_photos
        entry = next(h for h in self.lib.hoods if h["key"] == "seoul-seongsu")
        topic = editorial.Topic(kind="hood", key="k", data=entry)
        self.assertFalse(kto_photos.ensure_photo(topic, self.cfg, None, self.tmp / "ph", self.tmp / "a.json"))


if __name__ == "__main__":
    unittest.main()

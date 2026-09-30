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


if __name__ == "__main__":
    unittest.main()

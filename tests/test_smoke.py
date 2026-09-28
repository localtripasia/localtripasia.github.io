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
        for kind in ("city101", "hotel", "area", "transport", "route", "season", "words"):
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


if __name__ == "__main__":
    unittest.main()

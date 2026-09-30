"""Every content/*.toml entry needs >= 2 sources, and every key must be unique — this is what
keeps the bot honest (no AI-invented facts) and keeps data/state.json's history lookups correct."""
from __future__ import annotations

import unittest
from pathlib import Path

from bot import editorial
from bot.config import load_config

ROOT = Path(__file__).resolve().parent.parent
NEEDS_SOURCES = ("cities", "areas", "hoods", "passes", "routes", "seasons")  # words.toml is phrases, no claims to source


class ContentTest(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()
        self.lib = editorial.load_library(self.cfg)

    def test_every_entry_has_two_sources(self):
        for attr in NEEDS_SOURCES:
            for entry in getattr(self.lib, attr):
                sources = entry.get("sources") or []
                self.assertGreaterEqual(len(sources), 2,
                    f"content/{attr}.toml '{entry.get('key')}' 은 출처가 {len(sources)}개예요 (2개 이상 필요)")
                for s in sources:
                    self.assertTrue(s.startswith("http"), f"'{entry.get('key')}' 의 출처가 URL이 아니에요: {s}")

    def test_keys_are_unique_within_each_file(self):
        for kind in editorial.KINDS:
            entries = editorial.entries_for(kind, self.lib)
            keys = [e["key"] for e in entries]
            self.assertEqual(len(keys), len(set(keys)), f"'{kind}' 안에 key가 중복돼요: {keys}")

    def test_cities_have_three_things_and_three_hotel_tiers(self):
        for c in self.lib.cities:
            self.assertGreaterEqual(len(c.get("things", [])), 3, f"'{c['key']}' 는 'things' 가 3개 미만이에요")
            tiers = {h["tier"] for h in c.get("example_hotels", [])}
            self.assertTrue({"budget", "mid", "splurge"} <= tiers or not c.get("example_hotels"),
                            f"'{c['key']}' 의 example_hotels 는 budget/mid/splurge 세 등급이 다 있어야 해요")


if __name__ == "__main__":
    unittest.main()

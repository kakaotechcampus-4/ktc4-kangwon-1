"""학교 교육환경보호구역 규제 판정을 검증합니다."""

import unittest

from app.agentic.scoring import WEIGHTS, rank_candidates, result, summarize
from app.agentic.scoring import regulation as judge_regulation

ABSOLUTE = {"status": "ok", "zones": [{"name": "절대보호구역"}]}
RELATIVE = {"status": "ok", "zones": [{"name": "상대보호구역"}]}


class SchoolZoneRegulationTests(unittest.TestCase):
    def test_absolute_zone_bans_bar_and_amusement(self):
        for code in ("I101", "I102", "I211", "R104"):
            with self.subTest(code=code):
                status = judge_regulation(code, ABSOLUTE)
                self.assertEqual(status, "금지")
                items = {key: result(key, 4) if key != "L" else result(key) for key in WEIGHTS}
                self.assertEqual(summarize(code, items, status)["badge"], "비추천")

    def test_absolute_zone_rows_leave_top5(self):
        items = {key: result(key, 4) if key != "L" else result(key) for key in WEIGHTS}
        rows = [
            summarize(code, items, judge_regulation(code, ABSOLUTE))
            for code in ("I211", "R104", "G204")
        ]
        self.assertEqual([r["code"] for r in rank_candidates(rows)], ["G204"])

    def test_relative_zone_keeps_conditional(self):
        for code in ("I101", "I102", "I211", "R104"):
            with self.subTest(code=code):
                self.assertEqual(judge_regulation(code, RELATIVE), "조건부")

    def test_unverified_scan_stays_unknown(self):
        scan = {**ABSOLUTE, "contains_verified": False}
        for code in ("I211", "R104"):
            with self.subTest(code=code):
                self.assertEqual(judge_regulation(code, scan), "unknown")

    def test_other_codes_unaffected(self):
        self.assertEqual(judge_regulation("G204", ABSOLUTE), "해당 없음")

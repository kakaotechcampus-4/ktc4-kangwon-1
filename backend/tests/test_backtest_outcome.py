import unittest

import pandas as pd

from app.industries.catalog import SEOUL_TO_INDUSTRY
from backtest.data import api_rows, quarters_after, quarters_until
from backtest.outcome import MIN_STORES, StoreTable

SEOUL_A, SEOUL_B = next(
    (a, b)
    for a in sorted(SEOUL_TO_INDUSTRY)
    for b in sorted(SEOUL_TO_INDUSTRY)
    if a < b and SEOUL_TO_INDUSTRY[a] != SEOUL_TO_INDUSTRY[b]
)
IND_A, IND_B = SEOUL_TO_INDUSTRY[SEOUL_A], SEOUL_TO_INDUSTRY[SEOUL_B]
BASE = "20234"


def row(quarter, area, seoul_code, stores, closed):
    return {
        "STDR_YYQU_CD": quarter,
        "TRDAR_SE_CD": "A",
        "TRDAR_SE_CD_NM": "골목상권",
        "TRDAR_CD": area,
        "TRDAR_CD_NM": f"상권{area}",
        "SVC_INDUTY_CD": seoul_code,
        "SVC_INDUTY_CD_NM": seoul_code,
        "SIMILR_INDUTY_STOR_CO": float(stores),
        "STOR_CO": float(stores),
        "FRC_STOR_CO": 0.0,
        "OPBIZ_RT": 0.0,
        "OPBIZ_STOR_CO": 0.0,
        "CLSBIZ_RT": 0.0,
        "CLSBIZ_STOR_CO": float(closed),
        "INDUSTRY": SEOUL_TO_INDUSTRY.get(seoul_code),
    }


def frame(rows):
    return pd.DataFrame(rows)


class QuarterTests(unittest.TestCase):
    def test_quarter_ranges(self):
        self.assertEqual(quarters_after("20251", "20252"), ["20252"])
        self.assertEqual(quarters_after("20254", "20262"), ["20261", "20262"])
        self.assertEqual(quarters_until("20234", 4), ["20231", "20232", "20233", "20234"])

    def test_api_rows_use_lowercase_keys_and_only_requested_quarters(self):
        data = frame([row("20234", "1", SEOUL_A, 10, 1), row("20241", "1", SEOUL_A, 10, 1)])
        rows = api_rows(data, ["20234"])
        self.assertEqual([r["stdr_yyqu_cd"] for r in rows], ["20234"])
        self.assertEqual(rows[0]["similr_induty_stor_co"], 10.0)


class SurvivalTests(unittest.TestCase):
    def setUp(self):
        self.table = StoreTable(
            frame(
                [
                    row(BASE, "1", SEOUL_A, 10, 0),
                    row(BASE, "2", SEOUL_A, 20, 0),
                    row(BASE, "1", SEOUL_B, 2, 0),
                    row("20241", "1", SEOUL_A, 10, 1),
                    row("20242", "1", SEOUL_A, 0, 0),
                    row("20243", "1", SEOUL_A, 10, 2),
                    row("20241", "2", SEOUL_A, 20, 10),
                    row("20243", "2", SEOUL_A, 20, 10),
                    row("20241", "1", SEOUL_B, 2, 0),
                    row("20243", "1", SEOUL_B, 2, 0),
                ]
            )
        )
        self.quarters = ["20241", "20242", "20243"]

    def test_survival_multiplies_quarters_and_skips_empty_ones(self):
        self.assertAlmostEqual(self.table.survival("1", IND_A, self.quarters), 0.9 * 0.8)

    def test_seoul_and_area_averages(self):
        self.assertAlmostEqual(
            self.table.seoul_survival(IND_A, self.quarters), (1 - 11 / 30) * (1 - 12 / 30)
        )
        self.assertAlmostEqual(
            self.table.area_survival("1", self.quarters), (1 - 1 / 12) * (1 - 2 / 12)
        )

    def test_judge_scores_marks_absent_and_refuses(self):
        scored = self.table.judge("1", IND_A, "recommended", BASE, self.quarters)
        self.assertEqual(scored.status, "scored")
        self.assertTrue(scored.correct_vs_seoul)
        self.assertEqual(scored.base_stores, 10)
        against = self.table.judge("1", IND_A, "not_recommended", BASE, self.quarters)
        self.assertFalse(against.correct_vs_seoul)
        absent = self.table.judge("1", IND_B, "recommended", BASE, self.quarters)
        self.assertEqual(absent.status, "absent")
        self.assertLess(absent.base_stores, MIN_STORES)
        self.assertIsNone(absent.survival)
        self.assertEqual(
            self.table.judge("1", "Z999", "recommended", BASE, self.quarters).status, "unscorable"
        )


class JudgeAtBaseTests(unittest.TestCase):
    quarters = ["20241", "20242", "20243"]

    def test_industry_that_shrinks_after_base_is_still_scored(self):
        table = StoreTable(
            frame(
                [
                    row(BASE, "1", SEOUL_A, 10, 0),
                    row("20241", "1", SEOUL_A, 10, 10),
                    row(BASE, "2", SEOUL_A, 10, 0),
                    row("20241", "2", SEOUL_A, 10, 1),
                    row("20242", "2", SEOUL_A, 10, 1),
                    row("20243", "2", SEOUL_A, 10, 1),
                ]
            )
        )
        verdict = table.judge("1", IND_A, "recommended", BASE, self.quarters)
        self.assertEqual(verdict.status, "scored")
        self.assertEqual(verdict.survival, 0.0)
        self.assertFalse(verdict.correct_vs_seoul)

    def test_no_future_rows_is_pending(self):
        table = StoreTable(frame([row(BASE, "1", SEOUL_A, 10, 0)]))
        self.assertEqual(
            table.judge("1", IND_A, "recommended", BASE, self.quarters).status, "pending"
        )

    def test_references_use_the_quarters_the_cell_used(self):
        table = StoreTable(
            frame(
                [
                    row(BASE, "1", SEOUL_A, 10, 0),
                    row("20241", "1", SEOUL_A, 10, 1),
                    row("20241", "2", SEOUL_A, 10, 3),
                    row("20243", "2", SEOUL_A, 10, 9),
                    row("20241", "1", SEOUL_B, 10, 0),
                    row("20243", "1", SEOUL_B, 10, 9),
                ]
            )
        )
        verdict = table.judge("1", IND_A, "recommended", BASE, self.quarters)
        self.assertAlmostEqual(verdict.seoul, table.seoul_survival(IND_A, ["20241"]))
        self.assertAlmostEqual(verdict.area, table.area_survival("1", ["20241"]))
        self.assertNotAlmostEqual(verdict.seoul, table.seoul_survival(IND_A, self.quarters))

    def test_exact_tie_is_not_counted_either_way(self):
        table = StoreTable(
            frame([row(BASE, "1", SEOUL_A, 10, 0), row("20241", "1", SEOUL_A, 10, 1)])
        )
        for kind in ("recommended", "not_recommended"):
            verdict = table.judge("1", IND_A, kind, BASE, self.quarters)
            self.assertEqual(verdict.status, "scored")
            self.assertIsNone(verdict.correct_vs_area)
            self.assertIsNone(verdict.correct_vs_seoul)

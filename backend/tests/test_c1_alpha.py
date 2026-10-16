"""순위 동점·로그 제외·수요 보정 강도를 가짜 값으로 검증한다."""

import unittest
from unittest.mock import patch

from scripts.validate_c1_alpha import alpha_reports, correlations, ranks, spearman


class C1AlphaTests(unittest.TestCase):
    def test_average_tie_ranks_and_constant_correlation(self):
        self.assertEqual(ranks([3, 1, 1]), [3, 1.5, 1.5])
        self.assertAlmostEqual(spearman([1, 1, 3], [2, 2, 6]), 1)
        self.assertAlmostEqual(spearman([1, 2, 3], [3, 2, 1]), -1)
        self.assertIsNone(spearman([1, 1], [2, 3]))

    def test_zero_q_is_excluded_but_zero_closure_is_retained(self):
        rows = [
            {
                "code": "I201",
                "items": {
                    "C1": {"status": "observed", "value": q},
                    "S1": {"status": "observed", "value": s},
                },
            }
            for q, s in [(0, 2), (1, 0), (2, 1)]
        ]
        data = correlations([{"rows": rows}], True, "S1")
        self.assertEqual(data["eligible"], 3)
        self.assertEqual(data["n"], 2)
        self.assertEqual(data["excluded_q_zero"], 1)
        self.assertAlmostEqual(data["rho"], 1)

    def test_fractional_alpha_and_missing_demand(self):
        from scripts.rubric_dryrun import WEIGHTS, result, summarize

        items = {k: result(k, 3) for k in WEIGHTS}
        items["C1"] = result("C1", 0, value=4)
        base = {"address": "대역", "rows": [summarize("I201", items, "해당 없음")]}
        sample = {"floating_population": {"benchmark": {"mean_daily_per_trade_area": 40}}}
        with (
            patch("scripts.validate_c1_alpha.evaluate", return_value=base),
            patch("scripts.validate_c1_alpha.DAILY_TOTAL_PERCENTILES", {50: 10}),
        ):
            item = alpha_reports([sample], 0.75)[0]["rows"][0]["items"]["C1"]
            self.assertAlmostEqual(item["value"], 4 / 4**0.75)
            self.assertEqual(item["grade"], 1)
            sample["floating_population"]["benchmark"]["mean_daily_per_trade_area"] = 0
            self.assertEqual(
                alpha_reports([sample], 1)[0]["rows"][0]["items"]["C1"]["status"], "unknown"
            )
            self.assertEqual(alpha_reports([sample], 0)[0]["rows"][0]["items"]["C1"]["value"], 4)

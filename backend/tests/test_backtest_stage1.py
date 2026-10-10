import unittest
from unittest.mock import patch

import pandas as pd
from test_backtest_outcome import row

from app.industries.catalog import SEOUL_TO_INDUSTRY
from backtest import stage1
from backtest.data import quarters_after, quarters_until
from backtest.outcome import MIN_STORES, StoreTable
from backtest.scores import (
    concordance,
    persistence_baseline,
    popularity_baseline,
    seoul_baseline,
)
from backtest.stage1 import evaluate, lifecycle_scores, summarize

CODES = sorted(SEOUL_TO_INDUSTRY)[:6]


def synthetic(future_closed=1):
    rows = []
    quarters = quarters_until("20234", 12) + quarters_after("20234", "20244")
    for area in ("1", "2"):
        for i, code in enumerate(CODES):
            for q in quarters:
                closed = future_closed * i if q > "20234" else i % 3
                rows.append(row(q, area, code, 10 + i, closed))
    return pd.DataFrame(rows)


FOUR = {"lifecycle", "seoul_average", "popularity", "persistence"}


def outcomes_for(data, area):
    table = StoreTable(data)
    future = quarters_after("20234", "20244")
    return {
        industry: value
        for industry, stores in table.stores_at(area, "20234").items()
        if stores >= MIN_STORES and (value := table.survival(area, industry, future)) is not None
    }


def patched(lifecycle, misleading):
    def life(frame, area, base):
        if isinstance(lifecycle, Exception):
            raise lifecycle
        return lifecycle(area)

    return (
        patch.object(stage1, "lifecycle_scores", life),
        patch.object(stage1, "seoul_baseline", lambda table, base: misleading),
        patch.object(stage1, "popularity_baseline", lambda table, area, base: misleading),
        patch.object(stage1, "persistence_baseline", lambda table, area, base: misleading),
    )


class SameIndustrySetTests(unittest.TestCase):
    def setUp(self):
        self.data = synthetic()
        self.outcomes = outcomes_for(self.data, "1")
        self.best = max(self.outcomes, key=lambda k: self.outcomes[k])
        self.misleading = {**self.outcomes, self.best: -1.0}
        self.partial = {k: v for k, v in self.outcomes.items() if k != self.best}

    def evaluate(self, lifecycle):
        a, b, c, d = patched(lifecycle, self.misleading)
        with a, b, c, d:
            return evaluate(self.data, ["20234"], last="20244")

    def test_industry_missing_from_lifecycle_is_excluded_from_every_signal(self):
        result = self.evaluate(lambda area: self.partial)
        area = result[result["area"] == "1"]
        self.assertEqual(set(area["signal"]), FOUR)
        restricted = {k: self.outcomes[k] for k in self.partial}
        expected = concordance(self.misleading, restricted)
        self.assertNotEqual(expected, concordance(self.misleading, self.outcomes))
        self.assertTrue((area["concordance"] == expected).all())
        n = len(self.outcomes)
        self.assertTrue((area["industries"] == n - 1).all())
        self.assertTrue((area["coverage"] == (n - 1) / n).all())

    def test_pair_with_fewer_than_two_common_industries_is_skipped(self):
        def lifecycle(area):
            return {self.best: 1.0} if area == "1" else dict(self.outcomes)

        result = self.evaluate(lifecycle)
        area = result[result["area"] == "1"]
        self.assertEqual(list(area["signal"]), ["lifecycle"])
        self.assertTrue(area["concordance"].isna().all())
        self.assertIsNone(area["error"].iloc[0])
        n = len(self.outcomes)
        self.assertAlmostEqual(area["coverage"].iloc[0], 1 / n)
        summary = summarize(result)
        self.assertEqual(summary["pairs"], 1)
        self.assertEqual(summary["skipped"], 1)
        other = result[(result["area"] == "2") & (result["signal"] == "lifecycle")]
        self.assertAlmostEqual(summary["coverage_mean"], (1 / n + other["coverage"].iloc[0]) / 2)

    def test_lifecycle_error_scores_baselines_on_the_unrestricted_set(self):
        result = self.evaluate(RuntimeError("boom"))
        area = result[result["area"] == "1"]
        errors = area[area["signal"] == "lifecycle"]
        self.assertEqual(errors["error"].tolist(), ["RuntimeError"])
        baselines = area[area["signal"] != "lifecycle"]
        self.assertEqual(len(baselines), 3)
        expected = concordance(self.misleading, self.outcomes)
        self.assertTrue((baselines["concordance"] == expected).all())
        self.assertTrue(area["coverage"].isna().all())
        self.assertIsNone(summarize(result)["coverage_mean"])


class StageOneTests(unittest.TestCase):
    def test_every_signal_is_scored_per_area(self):
        result = evaluate(synthetic(), ["20234"], last="20244")
        self.assertEqual(
            set(result["signal"]), {"lifecycle", "seoul_average", "popularity", "persistence"}
        )
        self.assertEqual(set(result["area"]), {"1", "2"})
        self.assertTrue(result["concordance"].between(0, 1).all())

    def test_industries_are_chosen_by_stores_at_base_not_future(self):
        data = synthetic()
        industries = [SEOUL_TO_INDUSTRY[c] for c in CODES]
        code = next(c for c in CODES if industries.count(SEOUL_TO_INDUSTRY[c]) == 1)
        shrink = (
            (data["TRDAR_CD"] == "1")
            & (data["SVC_INDUTY_CD"] == code)
            & (data["STDR_YYQU_CD"] > "20234")
        )
        data.loc[shrink, ["SIMILR_INDUTY_STOR_CO", "CLSBIZ_STOR_CO"]] = 1.0
        self.assertEqual(outcomes_for(data, "1")[SEOUL_TO_INDUSTRY[code]], 0.0)
        result = evaluate(data, ["20234"], last="20244")
        counts = result[result["signal"] == "seoul_average"].set_index("area")["industries"]
        self.assertEqual(counts["1"], counts["2"])

    def test_lifecycle_scores_ignore_future_quarters(self):
        a = synthetic(future_closed=1)
        b = synthetic(future_closed=5)
        first = lifecycle_scores(a[a["TRDAR_CD"] == "1"], "1", "20234")
        self.assertTrue(first)
        self.assertEqual(first, lifecycle_scores(b[b["TRDAR_CD"] == "1"], "1", "20234"))

    def test_baselines_ignore_future_quarters(self):
        a = StoreTable(synthetic(future_closed=1))
        b = StoreTable(synthetic(future_closed=5))
        base = "20234"
        pairs = [
            (seoul_baseline(a, base), seoul_baseline(b, base)),
            (persistence_baseline(a, "1", base), persistence_baseline(b, "1", base)),
            (popularity_baseline(a, "1", base), popularity_baseline(b, "1", base)),
        ]
        for first, second in pairs:
            self.assertTrue(first)
            self.assertEqual(first, second)

    def test_summarize_bootstraps_over_areas(self):
        data = [
            ("20234", "A", "lifecycle", 0.9),
            ("20234", "A", "seoul_average", 0.9),
            ("20234", "A", "popularity", 0.9),
            ("20234", "A", "persistence", 0.9),
            ("20241", "A", "lifecycle", 0.9),
            ("20241", "A", "seoul_average", 0.9),
            ("20241", "A", "popularity", 0.9),
            ("20241", "A", "persistence", 0.9),
            ("20234", "B", "lifecycle", 0.1),
            ("20234", "B", "seoul_average", 0.1),
            ("20234", "B", "popularity", 0.1),
            ("20234", "B", "persistence", 0.1),
        ]
        rows = pd.DataFrame(
            [
                {
                    "base": base,
                    "area": area,
                    "signal": signal,
                    "concordance": concordance,
                    "industries": 5,
                    "error": None,
                }
                for base, area, signal, concordance in data
            ]
        )
        summary = summarize(rows)
        self.assertEqual(summary["pairs"], 3)
        self.assertEqual(summary["areas"], 2)
        self.assertAlmostEqual(summary["signals"]["lifecycle"]["mean"], 0.5)
        self.assertIsNone(summary["coverage_mean"])
        rows["coverage"] = [1.0] * 4 + [0.5] * 4 + [0.6] * 4
        self.assertAlmostEqual(summarize(rows)["coverage_mean"], (1.0 + 0.5 + 0.6) / 3)

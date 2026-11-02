"""시점 분리 전진 검증이 이후 자료를 채점 입력에 섞지 않고 건수 합으로 성과를 재는지 확인합니다."""

import unittest

from app.geo import to_epsg5181
from backtest import forward_metrics
from backtest.forward import (
    area_outcomes,
    period_counts,
    pool_rows,
    split_versions,
    strict_data,
    to_wgs84,
)

QUARTERS = [f"{y}{q}" for y in (2023, 2024, 2025, 2026) for q in (1, 2, 3, 4)]
LIFECYCLE = QUARTERS[2:14]  # 20233~20262


def versions(lifecycle=LIFECYCLE, floating=("20252", "20262")):
    rows = [{"source": s, "quarter": "", "version_id": s} for s in ("areas", "seoul_boundary")]
    rows += [{"source": s, "quarter": "20262", "version_id": s} for s in ("stores", "resident")]
    rows += [{"source": "worker", "quarter": "20262", "version_id": "worker"}]
    rows += [{"source": "lifecycle", "quarter": q, "version_id": "l" + q} for q in lifecycle]
    rows += [{"source": "floating", "quarter": q, "version_id": "f" + q} for q in floating]
    return rows


def raw(quarter, code="CS100001", area="A1", stores=10, opened=1, closed=1):
    return {
        "STDR_YYQU_CD": quarter,
        "TRDAR_CD": area,
        "SVC_INDUTY_CD": code,
        "SIMILR_INDUTY_STOR_CO": stores,
        "STOR_CO": stores,
        "FRC_STOR_CO": 0,
        "OPBIZ_STOR_CO": opened,
        "CLSBIZ_STOR_CO": closed,
    }


class SplitTests(unittest.TestCase):
    def test_inputs_stop_at_cutoff_and_outcomes_start_after(self):
        asof, future = split_versions(versions(), "20252")
        past = sorted(v["quarter"] for v in asof if v["source"] == "lifecycle")
        self.assertEqual(past, LIFECYCLE[:8])
        self.assertEqual(sorted(v["quarter"] for v in future), LIFECYCLE[8:])
        self.assertEqual([v["quarter"] for v in asof if v["source"] == "floating"], ["20252"])
        self.assertFalse({id(v) for v in asof} & {id(v) for v in future})

    def test_rejects_gaps_before_or_after_cutoff(self):
        with self.assertRaisesRegex(ValueError, "8개 분기"):
            split_versions(versions([q for q in LIFECYCLE if q != "20241"]), "20252")
        with self.assertRaisesRegex(ValueError, "4개 분기"):
            split_versions(versions(LIFECYCLE[:11]), "20252")
        with self.assertRaisesRegex(ValueError, "유동인구"):
            split_versions(versions(floating=("20262",)), "20252")


class OutcomeTests(unittest.TestCase):
    future = LIFECYCLE[8:]

    def test_sums_raw_counts_and_scales_by_seoul_rate(self):
        rows = [raw(q, stores=12, opened=1, closed=2) for q in self.future]
        seoul = period_counts(
            pool_rows([raw(q, area="X", stores=100, closed=5) for q in self.future]), "11", "20262"
        )
        out = area_outcomes(rows, "A1", "20262", seoul)
        code = next(iter(out))
        self.assertEqual((out[code]["exposure"], out[code]["closed"]), (48, 8))
        self.assertAlmostEqual(out[code]["expected"], 48 * 0.05)

    def test_skips_small_exposure_instead_of_guessing(self):
        rows = [raw(q, stores=9) for q in self.future]
        seoul = period_counts(pool_rows([raw(q, stores=100) for q in self.future]), "11", "20262")
        self.assertEqual(area_outcomes(rows, "A1", "20262", seoul), {})

    def test_pooled_rows_add_counts_across_areas(self):
        pooled = pool_rows([raw("20253", area="A"), raw("20253", area="B", closed=3)])
        self.assertEqual(len(pooled), 1)
        self.assertEqual(pooled[0]["clsbiz_stor_co"], 4)
        self.assertEqual(pooled[0]["trdar_cd"], "11")


class SiteTests(unittest.TestCase):
    def test_inverse_projection_round_trips_within_half_metre(self):
        x, y = to_epsg5181(37.5665, 126.978)
        lat, lon = to_wgs84(x, y)
        fx, fy = to_epsg5181(lat, lon)
        self.assertLess(abs(fx - x) + abs(fy - y), 0.5)

    def test_strict_data_removes_post_cutoff_sources_only(self):
        data = {
            "commercial_collection_complete": True,
            "floating_population": {"population": {"a": 1}, "resident": {"x": 1}, "worker": {}},
        }
        strict = strict_data(data)
        self.assertFalse(strict["commercial_collection_complete"])
        self.assertIsNone(strict["floating_population"]["resident"])
        self.assertEqual(strict["floating_population"]["population"], {"a": 1})
        self.assertTrue(data["commercial_collection_complete"])


def record(district, order, outcomes):
    return {
        "area": district + "-a",
        "district": district,
        "orders": {"service": order, "other": list(reversed(order))},
        "badges": dict.fromkeys(order, "보류"),
        "outcomes": outcomes,
    }


def outcome(closed, expected, exposure=100, opened=0):
    return {"closed": closed, "expected": expected, "exposure": exposure, "opened": opened}


class MetricTests(unittest.TestCase):
    def setUp(self):
        order = [f"I{i}" for i in range(10)]
        # 상위 5개는 기대의 절반만 닫고, 나머지는 기대만큼 닫습니다.
        good = {code: outcome(1, 2) for code in order[:5]}
        bad = {code: outcome(2, 2) for code in order[5:]}
        self.records = [record(d, order, {**good, **bad}) for d in ("11110", "11140", "11170")]

    def test_pooled_ratio_compares_top_five_with_rest(self):
        result = forward_metrics.top_vs_rest(self.records, "service", rounds=50, seed=1)
        self.assertAlmostEqual(result["top5"]["scr"], 0.5)
        self.assertAlmostEqual(result["rest"]["scr"], 1.0)
        self.assertAlmostEqual(result["scr_ratio_top5_over_rest"], 0.5)
        self.assertEqual(result["scr_ratio_ci95"], (0.5, 0.5))

    def test_reverse_order_is_worse_and_paired_ratio_reflects_it(self):
        paired = forward_metrics.paired(self.records, "other", "service", rounds=50, seed=1)
        self.assertAlmostEqual(paired["scr_ratio"], 2.0)
        wins = forward_metrics.area_wins(self.records, "other")
        self.assertEqual(wins, {"compared_areas": 3, "top5_lower_share": 0.0})

    def test_unmeasured_picks_are_counted_not_imputed(self):
        records = [record("11110", ["A", "B", "C", "D", "E", "F"], {"A": outcome(0, 1)})]
        self.assertAlmostEqual(forward_metrics.measured_share(records, "service"), 0.2)
        result = forward_metrics.top_vs_rest(records, "service", rounds=20, seed=1)
        self.assertIsNone(result["scr_ratio_top5_over_rest"])

    def test_rank_bands_and_report_fields(self):
        result = forward_metrics.evaluate(self.records, ["service", "other"], rounds=20)
        bands = result["methods"]["service"]["rank_bands"]
        self.assertEqual([b["pairs"] for b in bands[:2]], [15, 15])
        self.assertAlmostEqual(bands[0]["scr"], 0.5)
        self.assertIn("other", result["paired_vs_reference"])
        self.assertEqual(result["badges"]["보류"]["pairs"], 30)


if __name__ == "__main__":
    unittest.main()

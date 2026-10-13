"""시험 채점의 핵심 상태·규제 처리만 가짜 자료로 검증한다."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from scripts.rubric_dryrun import regulation, score_item, summarize


class RubricDryrunTests(unittest.TestCase):
    def test_v08_default_c1_half_power_and_missing_demand(self):
        from scripts.rubric_dryrun import population_baseline

        sample = {
            "floating_population": {
                "benchmark": {
                    "mean_daily_per_trade_area": 4 * population_baseline.DAILY_TOTAL_PERCENTILES[50]
                }
            },
            "commercial_collection_complete": True,
            "commercial_area": {
                "radius_m": 500,
                "by_middle": [{"code": "I201", "density_per_km2": 40}],
            },
        }
        with patch("scripts.rubric_dryrun.SEOUL_INDUSTRY_DENSITY_PERCENTILES", {"I201": {50: 10}}):
            self.assertEqual(score_item("C1", {}, "I201", sample)["value"], 2)
            self.assertEqual(score_item("C1", {}, "I201", sample, c1_alpha=0)["value"], 4)
            sample["floating_population"]["benchmark"]["mean_daily_per_trade_area"] = 0
            self.assertEqual(score_item("C1", {}, "I201", sample)["status"], "unknown")

    def test_c1_alternatives_only_change_c1(self):
        from scripts.audit_c1_density import alternatives
        from scripts.build_density_baseline import area_km2
        from scripts.rubric_dryrun import WEIGHTS

        items = {
            k: {"status": "observed", "points": weight * 0.75, "grade": 3}
            for k, weight in WEIGHTS.items()
        }
        base = summarize("G204", items, "해당 없음")
        sample = {
            "floating_population": {"benchmark": {"mean_daily_per_trade_area": 20}},
            "commercial_area": {
                "by_middle": [{"code": "G204", "density_per_km2": 20 / area_km2(500)}]
            },
            "business_lifecycle": {"metadata": {"area_resolver": {"area_code": "1"}}},
        }
        with (
            patch(
                "scripts.audit_c1_density.load_trade_areas",
                return_value=[SimpleNamespace(code="1", kind="발달상권")],
            ),
            patch(
                "scripts.audit_c1_density.load_industry_done",
                return_value={"1": {"counts": '{"G204": 10}', "blocked_codes": "[]"}},
            ),
            patch(
                "scripts.audit_c1_density.evaluate",
                return_value={"address": "대역", "rows": [base]},
            ),
            patch("scripts.audit_c1_density.industry_percentile", return_value=50),
            patch("scripts.audit_c1_density.DAILY_TOTAL_PERCENTILES", {50: 10}),
            patch(
                "scripts.audit_c1_density.SEOUL_INDUSTRY_DENSITY_PERCENTILES",
                {"G204": {50: 10 / area_km2(500)}},
            ),
        ):
            output = alternatives([sample])["reports"]
            sample["floating_population"]["benchmark"]["mean_daily_per_trade_area"] = 0
            zero_demand = alternatives([sample])["reports"]
        self.assertEqual(output["type_median"][0]["rows"][0]["items"]["C1"]["grade"], 0)
        self.assertEqual(output["percentile"][0]["rows"][0]["items"]["C1"]["grade"], 2)
        self.assertEqual(output["percentile"][0]["rows"][0]["items"]["D1"], items["D1"])
        self.assertEqual(output["demand"][0]["rows"][0]["items"]["C1"]["grade"], 2)
        self.assertEqual(output["type_demand"][0]["rows"][0]["items"]["C1"]["grade"], 2)
        self.assertEqual(zero_demand["demand"][0]["rows"][0]["items"]["C1"]["status"], "unknown")

    def test_normalized_bounds_and_only_g_blocks_recommendation(self):
        from scripts.rubric_dryrun import WEIGHTS

        items = {k: {"status": "n.a.", "points": None} for k in WEIGHTS}
        items["D1"] = {"status": "observed", "points": 7.5}
        items["C1"] = {"status": "observed", "points": 10}
        items["S1"] = {"status": "unknown", "points": None}
        report = summarize("G204", items, "해당 없음", lower_min=0.60)
        self.assertEqual(report["applicable_weight"], 32.5)
        self.assertEqual(report["upper"], 25)
        self.assertAlmostEqual(report["lower_ratio"], 17.5 / 32.5)
        self.assertEqual(report["badge"], "보류")
        items["C1"]["points"] = 15
        self.assertEqual(summarize("G204", items, "해당 없음")["badge"], "조건부")
        self.assertEqual(summarize("G204", items, "unknown")["badge"], "조건부")
        self.assertEqual(summarize("G204", items, "조건부")["badge"], "조건부")
        items["D1"]["points"] = 0
        items["C1"]["points"] = 0
        self.assertEqual(summarize("G204", items, "해당 없음")["badge"], "비추천")
        for item in items.values():
            item.update(status="n.a.", points=None)
        report = summarize("G204", items, "해당 없음")
        self.assertIsNone(report["lower_ratio"])
        self.assertEqual(report["badge"], "보류")

    def test_recommendation_requires_applicable_weight_and_demand_evidence(self):
        from scripts.rubric_dryrun import WEIGHTS

        items = {
            k: {"status": "observed", "points": weight * 0.75} for k, weight in WEIGHTS.items()
        }
        self.assertEqual(summarize("G204", items, "해당 없음")["badge"], "추천")
        for key in ("D1", "D3"):
            items[key] = {"status": "n.a.", "points": None}
        report = summarize("G204", items, "해당 없음")
        self.assertEqual(report["applicable_weight"], 80)
        self.assertEqual(report["badge"], "조건부")
        self.assertIn("손님 수요 근거 없음", report["confirmation_conditions"])
        items["D1"] = {"status": "observed", "points": 7.5}
        for key in ("D2", "C4", "D4", "S1"):
            items[key] = {"status": "n.a.", "points": None}
        report = summarize("G204", items, "해당 없음")
        self.assertEqual(report["applicable_weight"], 57.5)
        self.assertEqual(report["badge"], "조건부")
        self.assertIn("채점 가능한 문항이 적음", report["confirmation_conditions"])
        food = {k: {"status": "observed", "points": weight * 0.75} for k, weight in WEIGHTS.items()}
        for key in ("D2", "D3", "C4"):
            food[key] = {"status": "n.a.", "points": None}
        report = summarize("I201", food, "해당 없음")
        self.assertEqual(report["applicable_weight"], 70)
        self.assertEqual(report["badge"], "추천")

    def test_v08_weights_and_unknown_decision_judgment(self):
        from scripts.rubric_dryrun import WEIGHTS, result

        self.assertEqual(sum(WEIGHTS.values()), 100)
        self.assertEqual(sum(v for k, v in WEIGHTS.items() if k != "L"), 90)
        self.assertEqual(result("D4", 3)["points"], 3.75)
        self.assertEqual(result("C4", 3)["points"], 7.5)
        items = {k: result(k, 3) for k in WEIGHTS}
        items["L"] = score_item("L", {}, "I201", {})
        self.assertEqual(items["L"]["status"], "unknown")
        self.assertIsNone(items["L"]["points"])
        report = summarize("I201", items, "해당 없음")
        self.assertEqual(report["applicable_weight"], 100)
        self.assertEqual(report["coverage"], 0.9)
        self.assertEqual(report["upper"] - report["lower"], 10)

    def test_d1_min_all_day_unknown_and_regulatory_ban(self):
        floating = {
            "period_code": "20262",
            "population": {"by_time": {"11_14": 10000000}, "time_per_hour_share": {"11_14": 0.001}},
            "benchmark": {"mean_daily_per_trade_area": 10000},
            "reliability": {"covered_trade_areas": 1},
        }
        meal = {"pattern": "주간 생활형", "primary_bands": "11_14"}
        low = score_item("D1", meal, "I201", {"floating_population": floating})
        self.assertEqual(low["grade"], 0)
        all_day = score_item("D1", {"pattern": "종일형"}, "G204", {"floating_population": floating})
        self.assertEqual(all_day["grade"], 3)
        missing = score_item("D1", {"pattern": "종일형"}, "G204", {})
        self.assertEqual(missing["status"], "unknown")
        self.assertIsNone(missing["points"])
        g = regulation("I101", {"status": "ok", "zones": [{"name": "절대보호구역"}]})
        self.assertEqual(g, "금지")
        report = summarize("I101", {"D1": missing}, g)
        self.assertEqual(report["badge"], "비추천")
        self.assertEqual(report["lower"], 0)
        self.assertEqual(report["upper"], 100)

    def test_v03_age_sum_fallback_and_applicable_coverage(self):
        data = {"floating_population": {"population": {"age_share": {"20": 0.3, "30": 0.3}}}}
        profile = {"target_population": "상주", "target_age_bands": "20;30"}
        value = score_item("D3", profile, "G204", data)
        from app.agents.floating_population.baseline import AGE_SHARE_AVG

        self.assertAlmostEqual(
            value["value"]["r"], 0.6 / (AGE_SHARE_AVG["20"] + AGE_SHARE_AVG["30"])
        )
        self.assertIn("유동 연령 대체", value["reason"])
        from scripts.rubric_dryrun import WEIGHTS

        items = {k: {"status": "n.a.", "points": None} for k in WEIGHTS}
        items["C1"] = {"status": "observed", "points": 15}
        report = summarize("G204", items, "unknown")
        self.assertEqual(report["coverage"], 1)
        self.assertEqual(report["c_coverage"], 1)

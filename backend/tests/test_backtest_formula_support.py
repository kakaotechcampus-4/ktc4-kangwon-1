"""관측 기간에 맞춘 S 보완도 누락·타 업종·미확인 상태를 왜곡하지 않는지 검증합니다."""

import copy
import unittest

from app.agents.business_lifecycle.client import get_recent_quarters
from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.formula_support import WINDOW_REASON, apply_support, evidence_for
from backtest.temporal_score import metrics


class FormulaSupportTests(unittest.TestCase):
    def fixture(self, stocks=5):
        quarters = get_recent_quarters("20252", 12)
        source = INDUSTRY_TO_SEOUL["G216"][0]
        local = {q: {source: [stocks, 0, 0]} for q in quarters}
        city = {q: {source: [100, 2, 2]} for q in quarters}
        baseline = {**metrics([[100, 2, 2]] * 12), "data_complete": True, "zero_filled_sources": 0}
        evidence = evidence_for("G216", quarters, local, city, baseline)
        return quarters, source, local, city, baseline, evidence

    def inputs(self, evidence):
        ratio = min(evidence["old_exposure"], evidence["recent_exposure"]) / 40
        fractions = {
            "D1": 0.3,
            "S1": evidence["fractions"]["S1"]["fraction"],
            "S2": evidence["fractions"]["S2"]["fraction"] * ratio**2,
            "S3": 0.4,
            "S4": 0.2,
        }
        items = {
            "S1": {"status": "observed"},
            "S2": {"status": "unknown", "reason": WINDOW_REASON},
        }
        return fractions, items

    def test_recent_S1_discount_uses_recent4_not_all12_exposure(self):
        *_, evidence = self.fixture()
        fractions, items = self.inputs(evidence)
        changed = apply_support(fractions, items, evidence, "S1_recent_support")
        self.assertEqual(evidence["full_exposure"], 60)
        self.assertEqual(changed["fractions"]["S1"], fractions["S1"] * 0.25)
        self.assertEqual(changed["fractions"]["S2"], fractions["S2"])

    def test_S2_full12_estimate_keeps_original_unknown_status_and_other_items(self):
        *_, evidence = self.fixture()
        fractions, items = self.inputs(evidence)
        before = copy.deepcopy((fractions, items))
        changed = apply_support(fractions, items, evidence, "S2_full_period_support")
        self.assertEqual(changed["fractions"]["S2"], 0.5)
        self.assertEqual(changed["changes"]["S2"]["source_status"], "unknown")
        self.assertEqual((fractions, items), before)
        for item in ("D1", "S1", "S3", "S4"):
            self.assertEqual(changed["fractions"][item], fractions[item])

    def test_missing_count_or_industry_is_never_repaired(self):
        q, code, local, city, baseline, good = self.fixture()
        fractions, items = self.inputs(good)
        local[q[0]].pop(code)
        missing = evidence_for("G216", q, local, city, baseline)
        self.assertFalse(missing["available"])
        self.assertEqual(
            apply_support(fractions, items, missing, "both_formula_support")["fractions"], fractions
        )
        self.assertFalse(evidence_for("I207", q, local, city, None)["available"])

    def test_low_total_exposure_still_receives_no_new_S2_credit(self):
        *_, evidence = self.fixture(stocks=3)
        fractions, items = self.inputs(evidence)
        changed = apply_support(fractions, items, evidence, "S2_full_period_support")
        self.assertEqual(changed["fractions"], fractions)

    def test_observed_S2_and_unknown_S1_are_not_overwritten(self):
        *_, evidence = self.fixture()
        fractions, items = self.inputs(evidence)
        items["S1"]["status"], items["S2"]["status"] = "unknown", "observed"
        changed = apply_support(fractions, items, evidence, "both_formula_support")
        self.assertEqual(changed["fractions"], fractions)

    def test_other_unknown_causes_do_not_receive_S2_estimate(self):
        *_, evidence = self.fixture()
        fractions, items = self.inputs(evidence)
        items["S2"]["reason"] = "원문 수집 부분 실패·행/페이지 누락"
        self.assertEqual(
            apply_support(fractions, items, evidence, "S2_full_period_support")["fractions"],
            fractions,
        )

    def test_complete_zero_events_remain_observed_and_baseline_conflict_is_rejected(self):
        quarters, source, local, city, baseline, evidence = self.fixture()
        self.assertTrue(evidence["available"])
        self.assertEqual(evidence["fractions"]["S1"]["fraction"], 1)
        baseline["net_change_rate"] = 100
        with self.assertRaises(ValueError):
            evidence_for("G216", quarters, local, city, baseline)

    def test_incorrect_old_fraction_cannot_be_silently_replaced(self):
        *_, evidence = self.fixture()
        fractions, items = self.inputs(evidence)
        fractions["S2"] = 0.99
        with self.assertRaises(ValueError):
            apply_support(fractions, items, evidence, "S2_full_period_support")


if __name__ == "__main__":
    unittest.main()

"""결제 분포의 원문 누락·법인 분모·모집단 대체가 가점으로 이어지지 않게 검증합니다."""

import unittest

from app.agents.floating_population.models import AGE_BANDS, DAYS
from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.purchase_profile import (
    FIELDS,
    affinity,
    build_profiles,
    changed_fractions,
    evidence_for,
)


class PurchaseProfileTests(unittest.TestCase):
    def rows(self):
        return [
            {
                "STDR_YYQU_CD": "20242",
                "MEGA_CD": "11",
                "SVC_INDUTY_CD": s,
                "THSMON_SELNG_CO": 1_000_000,
                **{f: 100 for fields in FIELDS.values() for f in fields.values()},
            }
            for s in INDUSTRY_TO_SEOUL["G216"]
        ]

    def test_age_denominator_uses_personal_age_sum_and_keeps_observed_zero(self):
        rows = self.rows()
        rows[0][FIELDS["age"]["10"]] = 0
        result = build_profiles(rows)["G216"]["age"]
        self.assertTrue(result["available"])
        self.assertEqual(result["weights"]["10"], 0)
        self.assertEqual(result["denominator"], 500)
        self.assertAlmostEqual(sum(result["weights"].values()), 1)

    def test_missing_count_or_mapping_component_does_not_become_zero(self):
        rows = self.rows()
        rows[0][FIELDS["age"]["20"]] = None
        self.assertFalse(build_profiles(rows)["G216"]["age"]["available"])
        rows = self.rows()
        self.assertFalse(build_profiles(rows)["G205"]["age"]["available"])

    def test_duplicate_future_or_nonseoul_row_is_rejected(self):
        for changes in ({"STDR_YYQU_CD": "20252"}, {"MEGA_CD": "26"}):
            rows = self.rows()
            rows[0].update(changes)
            with self.assertRaises(ValueError):
                build_profiles(rows)
        rows = self.rows()
        with self.assertRaises(ValueError):
            build_profiles(rows + rows)

    def test_identical_population_is_neutral_for_every_payment_profile(self):
        local = {"young": 0.2, "old": 0.8}
        for weight in (0, 0.2, 1):
            result = affinity(local, local, {"young": weight, "old": 1 - weight})
            self.assertAlmostEqual(result["ratio"], 1)
            self.assertAlmostEqual(result["fraction"], 0.5)
        self.assertGreater(
            affinity({"young": 0.4, "old": 0.6}, local, {"young": 1, "old": 0})["fraction"],
            0.5,
        )

    def test_unknown_and_not_applicable_receive_no_new_contribution(self):
        original = {"D2": 0.0, "D3": 0.0, "S1": 0.1}
        evidence = {k: {"available": True, "fraction": 1} for k in ("D2", "D3")}
        changed = changed_fractions(
            original, {"D2": "unknown", "D3": "n.a."}, evidence, "both_half"
        )
        self.assertEqual(changed, original)

    def test_resident_customer_profile_never_uses_floating_age_proxy(self):
        item = {
            "status": "observed",
            "value": {"population": "유동", "requested_population": "상주"},
        }
        data = {
            "floating_population": {
                "period_code": "20252",
                "population": {"age_share": dict.fromkeys(AGE_BANDS, 1 / 6)},
            }
        }
        result = evidence_for(
            {"target_population": "상주"},
            data,
            {"D2": {"status": "unknown"}, "D3": item},
            build_profiles(self.rows())["G216"],
            dict.fromkeys(DAYS, 1 / 7),
            dict.fromkeys(AGE_BANDS, 1 / 6),
        )
        self.assertFalse(result["D3"]["available"])

    def test_invalid_counts_and_zero_city_denominators_are_rejected(self):
        for value in (True, -1, 0.5, float("nan")):
            rows = self.rows()
            rows[0][FIELDS["age"]["20"]] = value
            with self.assertRaises(ValueError):
                build_profiles(rows)
        with self.assertRaises(ValueError):
            affinity({"a": 1, "b": 0}, {"a": 1, "b": 0}, {"a": 1, "b": 0})


if __name__ == "__main__":
    unittest.main()

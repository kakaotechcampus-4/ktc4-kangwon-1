"""시설 미확인·실제 부적합·프로필 미적용을 C4 정책에서 섞지 않습니다."""

import copy
import unittest

from backtest.c4_comparison import add_c4
from backtest.c4_policy import POLICIES, FacilityPolicy, score_policy


class FacilityPolicyTests(unittest.TestCase):
    def profile(self, categories="SC4", confidence="low"):
        return {
            "required_facilities": categories,
            "required_facilities_confidence": confidence,
            "max_distance_m_confidence": confidence,
        }

    def component(self, points=None):
        return {"status": "unknown" if points is None else "observed", "points": points}

    def policy(self, name):
        return next(p for p in POLICIES if p.name == name)

    def test_original_matches_previous_C4_for_observed_unknown_and_NA(self):
        policy = self.policy("original_min_zero")
        cases = [
            (self.profile(), {"SC4": self.component(7.5)}, "observed", 7.5),
            (self.profile(), {"SC4": self.component(0)}, "observed", 0),
            (self.profile(), {"SC4": self.component()}, "unknown", None),
            (self.profile(""), {}, "n.a.", None),
            (
                self.profile("SC4;HP8"),
                {"SC4": self.component(10), "HP8": self.component()},
                "unknown",
                None,
            ),
        ]
        for profile, components, state, points in cases:
            with self.subTest(state=state, points=points):
                new = score_policy(57, 60, profile, components, policy)
                old = add_c4(57, 60, {"status": state, "points": points})
                self.assertEqual(new["normalized"], old["normalized"])
                self.assertEqual(new["source_status"], state)

    def test_wholly_unknown_never_gets_more_than_without_C4_and_keeps_penalty(self):
        for policy in POLICIES:
            for score in (0, 10, 40, 60, 80):
                with self.subTest(policy=policy.name, score=score):
                    result = score_policy(
                        score, 60, self.profile(), {"SC4": self.component()}, policy
                    )
                    neutral = 90 * score / 80
                    self.assertLessEqual(result["normalized"], neutral)
                    if score:
                        self.assertLess(result["normalized"], neutral)
                    self.assertEqual(result["source_status"], "unknown")
                    self.assertIsNone(result["observed_aggregate_points"])

    def test_mild_unknown_relaxes_penalty_without_creating_observed_points(self):
        profile, components = self.profile(), {"SC4": self.component()}
        strict = score_policy(60, 80, profile, components, self.policy("original_min_zero"))
        mild = score_policy(60, 80, profile, components, self.policy("min_mild_unknown"))
        self.assertEqual(strict["normalized"], 60)
        self.assertEqual(mild["normalized"], 65)
        self.assertLess(mild["normalized"], 67.5)
        self.assertTrue(mild["derived_from_unknown"])

    def test_known_bad_distance_is_not_given_unknown_credit(self):
        for policy in POLICIES:
            with self.subTest(policy=policy.name):
                result = score_policy(60, 80, self.profile(), {"SC4": self.component(0)}, policy)
                self.assertEqual(result["effective_C4_contribution"], 0)
                self.assertEqual(result["source_status"], "observed")
                self.assertFalse(result["derived_from_unknown"])

    def test_min_with_one_missing_cannot_override_a_known_bad_facility(self):
        result = score_policy(
            60,
            80,
            self.profile("SC4;HP8"),
            {"SC4": self.component(0), "HP8": self.component()},
            self.policy("min_mild_unknown"),
        )
        self.assertEqual(result["policy_aggregate_points"], 0)
        self.assertEqual(result["source_status"], "unknown")

    def test_mean_keeps_partial_evidence_separate_from_complete_observation(self):
        result = score_policy(
            60,
            80,
            self.profile("SC4;HP8"),
            {"SC4": self.component(10), "HP8": self.component()},
            self.policy("mean_mild_unknown"),
        )
        self.assertEqual(result["policy_aggregate_points"], 7.5)
        self.assertIsNone(result["observed_aggregate_points"])
        self.assertEqual(result["source_status"], "unknown")
        self.assertEqual(result["component_status"], {"SC4": "observed", "HP8": "unknown"})

    def test_complete_mean_is_an_explicit_policy_change_not_original_min(self):
        components = {"SC4": self.component(10), "HP8": self.component(2.5)}
        original = score_policy(
            40, 80, self.profile("SC4;HP8"), components, self.policy("original_min_zero")
        )
        new = score_policy(40, 80, self.profile("SC4;HP8"), components, self.policy("mean_zero"))
        self.assertEqual(original["observed_aggregate_points"], 2.5)
        self.assertEqual(new["observed_aggregate_points"], 6.25)

    def test_half_weight_uses_profile_confidence_without_altering_actual_source_points(self):
        profile, components = self.profile(), {"SC4": self.component(10)}
        before = copy.deepcopy((profile, components))
        result = score_policy(
            40, 80, profile, components, self.policy("mean_mild_low_confidence_half")
        )
        self.assertEqual(result["observed_aggregate_points"], 10)
        self.assertEqual(result["effective_C4_contribution"], 5)
        self.assertEqual(result["effective_C4_weight"], 5)
        self.assertAlmostEqual(result["normalized"], 90 * 45 / 85)
        self.assertEqual((profile, components), before)
        high = score_policy(
            40,
            80,
            self.profile(confidence="high"),
            components,
            self.policy("mean_mild_low_confidence_half"),
        )
        self.assertEqual(high["effective_C4_weight"], 10)

    def test_single_facility_aggregation_and_fully_observed_unknown_policies_match(self):
        single = {"SC4": self.component(7.5)}
        results = [
            score_policy(40, 80, self.profile(), single, p)["normalized"] for p in POLICIES[:4]
        ]
        self.assertEqual(len(set(results)), 1)

    def test_observed_C4_increase_cannot_reduce_score(self):
        for policy in POLICIES:
            values = [
                score_policy(40, 60, self.profile(), {"SC4": self.component(p)}, policy)[
                    "normalized"
                ]
                for p in (0, 2.5, 5, 7.5, 10)
            ]
            self.assertEqual(values, sorted(values))

    def test_invalid_components_and_policy_are_rejected(self):
        for components in (
            {},
            {"SC4": {"status": "unknown", "points": 5}},
            {"SC4": {"status": "n.a.", "points": None}},
            {"SC4": self.component(float("nan"))},
        ):
            with self.subTest(components=components), self.assertRaises(ValueError):
                score_policy(40, 80, self.profile(), components, POLICIES[0])
        with self.assertRaises(ValueError):
            FacilityPolicy("unfrozen", aggregation="max")


if __name__ == "__main__":
    unittest.main()

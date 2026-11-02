"""가변 배점이 자료 부족을 유리하게 만들지 않고 80점을 넘지 않는지 확인합니다."""

import unittest

import numpy as np

from backtest.evidence_mix import MODES, mixed_scores


class EvidenceMixTests(unittest.TestCase):
    def test_missing_S_keeps_at_least15_points_before_NA_conversion(self):
        applicable = np.array([5.0, 15, 25, 35])
        for mode in MODES:
            value = mixed_scores(applicable, applicable, np.ones(4), np.zeros(4), mode)
            self.assertTrue(np.all(value <= 80 - 80 * 15 / (applicable + 45) + 1e-12))

    def test_more_survival_evidence_never_lowers_score(self):
        c = np.linspace(0, 1, 21)
        d, applicable = np.full(21, 15.0), np.full(21, 35.0)
        for mode in MODES:
            previous = mixed_scores(d, applicable, c, np.zeros(21), mode)
            for value in np.linspace(0.05, 1, 20):
                current = mixed_scores(d, applicable, c, np.full(21, value), mode)
                self.assertTrue(np.all(current >= previous - 1e-12))
                previous = current

    def test_removing_competition_evidence_does_not_improve_score(self):
        s = np.linspace(0, 1, 21)
        d, applicable = np.full(21, 10.0), np.full(21, 25.0)
        for mode in MODES:
            missing = mixed_scores(d, applicable, np.zeros(21), s, mode)
            observed = mixed_scores(d, applicable, np.full(21, 0.3), s, mode)
            self.assertTrue(np.all(missing <= observed + 1e-12))

    def test_symmetric_full_evidence_has_same80_point_scale(self):
        d, applicable = np.array([0.0, 35]), np.array([35.0, 35])
        for mode in MODES:
            np.testing.assert_allclose(
                mixed_scores(d, applicable, np.array([0.0, 1]), np.array([0.0, 1]), mode), [0, 80]
            )

    def test_mean_matches_fixed22_5_weights_and_half_max_is_bounded(self):
        d, applicable, c, s = (np.array(v) for v in ([10.0], [25.0], [0.9], [0.2]))
        average = mixed_scores(d, applicable, c, s, "mean")
        maximum = mixed_scores(d, applicable, c, s, "max")
        middle = mixed_scores(d, applicable, c, s, "half_max")
        np.testing.assert_allclose(average, 80 * (d + 22.5 * c + 22.5 * s) / (applicable + 45))
        np.testing.assert_allclose(middle, (average + maximum) / 2)

    def test_invalid_fraction_or_D_capacity_is_not_silently_corrected(self):
        with self.assertRaises(ValueError):
            mixed_scores(np.array([36]), np.array([35]), np.array([0.5]), np.array([0.5]), "max")
        with self.assertRaises(ValueError):
            mixed_scores(
                np.array([10]), np.array([35]), np.array([float("nan")]), np.array([0.5]), "max"
            )


if __name__ == "__main__":
    unittest.main()

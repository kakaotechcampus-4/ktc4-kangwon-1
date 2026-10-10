import unittest

from backtest.scores import bootstrap_mean, cluster_bootstrap_ratio, concordance


class ScoreTests(unittest.TestCase):
    def test_concordance_counts_agreeing_pairs_and_ties(self):
        outcomes = {"a": 0.9, "b": 0.8, "c": 0.7}
        self.assertEqual(concordance({"a": 3, "b": 2, "c": 1}, outcomes), 1.0)
        self.assertEqual(concordance({"a": 1, "b": 2, "c": 3}, outcomes), 0.0)
        self.assertEqual(concordance({"a": 1, "b": 1, "c": 1}, outcomes), 0.5)
        self.assertIsNone(concordance({"a": 1}, outcomes))
        self.assertEqual(concordance({"a": 2, "b": 1, "x": 9}, outcomes), 1.0)

    def test_concordance_skips_tied_outcomes_and_missing_values(self):
        outcomes = {"a": 0.9, "b": 0.9, "c": 0.7}
        self.assertEqual(concordance({"a": 1, "b": 3, "c": 2}, outcomes), 0.5)
        self.assertIsNone(concordance({"a": 1, "b": 3}, outcomes))
        nan = float("nan")
        clean = {"a": 0.9, "b": 0.8, "c": 0.7}
        self.assertEqual(concordance({"a": 3, "b": nan, "c": 1}, clean), 1.0)
        self.assertEqual(concordance({"a": 3, "b": 2, "c": 1}, {**clean, "b": nan}), 1.0)

    def test_cluster_bootstrap_resamples_sites_not_items(self):
        groups = [[1.0] * 9, [0.0], [0.0], [0.0], [1.0]]
        mean, low, high = cluster_bootstrap_ratio(groups)
        self.assertAlmostEqual(mean, 10 / 13)
        self.assertEqual((mean, low, high), cluster_bootstrap_ratio(groups))
        items = [value for group in groups for value in group]
        _, item_low, item_high = bootstrap_mean(items)
        self.assertGreater(high - low, item_high - item_low)
        self.assertEqual(cluster_bootstrap_ratio([[], [1.0, 0.0]])[0], 0.5)

    def test_bootstrap_is_reproducible_and_brackets_the_mean(self):
        values = [0.4, 0.6, 0.5, 0.7, 0.3]
        first = bootstrap_mean(values)
        self.assertEqual(first, bootstrap_mean(values))
        mean, low, high = first
        self.assertAlmostEqual(mean, 0.5)
        self.assertLessEqual(low, mean)
        self.assertGreaterEqual(high, mean)

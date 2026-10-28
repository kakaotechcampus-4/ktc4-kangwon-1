import json
import tempfile
import unittest
from pathlib import Path

from app.industries.catalog import INDUSTRIES
from backtest.measure import density_percentiles, load_baselines, save_baselines


def area_row(code, count, blocked=()):
    return {
        "code": code,
        "counts": json.dumps(dict.fromkeys(INDUSTRIES, count)),
        "blocked_codes": json.dumps(sorted(blocked)),
    }


class DensityTests(unittest.TestCase):
    def test_percentiles_cover_every_industry_with_integer_steps(self):
        rows = [area_row("a", 1), area_row("b", 3), area_row("c", 5)]
        result = density_percentiles(rows, {"a", "b", "c"})
        self.assertEqual(set(result), set(INDUSTRIES))
        steps = result[next(iter(INDUSTRIES))]
        self.assertEqual(set(steps), set(range(5, 100, 5)))
        values = [steps[p] for p in sorted(steps)]
        self.assertEqual(values, sorted(values))

    def test_blocked_industry_makes_the_baseline_incomplete(self):
        code = next(iter(INDUSTRIES))
        rows = [area_row("a", 1, blocked=[code]), area_row("b", 3)]
        with self.assertRaises(ValueError) as caught:
            density_percentiles(rows, {"a", "b"})
        self.assertIn(code, str(caught.exception))

    def test_missing_area_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            density_percentiles([area_row("a", 1)], {"a", "b"})
        self.assertIn("상권 표본", str(caught.exception))


class FileTests(unittest.TestCase):
    def test_round_trip(self):
        values = {
            "quarter": "20234",
            "lifecycle": {},
            "floating": {},
            "density": {"G202": {5: 1.0}},
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "baseline.json"
            save_baselines(path, values)
            loaded = load_baselines(path)
        self.assertEqual(loaded["quarter"], "20234")
        self.assertEqual(loaded["density"], {"G202": {"5": 1.0}})

    def test_rejects_another_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "other.json"
            path.write_text('{"x": 1}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_baselines(path)


if __name__ == "__main__":
    unittest.main()

"""과거 자료의 미래 유입·기준선 복원·미확인 점수 보존을 확인합니다."""

import json
import tempfile
import unittest
from pathlib import Path

from app.agentic import scoring
from app.agents.floating_population import baseline
from app.local_data.database import LocalDataDB
from backtest.licensing import sha256
from backtest.past80 import continuous_rows, item_kind
from backtest.past_baselines import calibrated
from backtest.past_data import copy_past, public_rows


class PastDataTests(unittest.TestCase):
    def test_public_source_cannot_mix_quarters_duplicate_or_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def save(rows, q="20252"):
                p = root / f"floating-{q}.json"
                p.write_text(json.dumps({"DATA": rows}), encoding="utf-8")
                (root / f"floating-{q}-receipt.json").write_text(
                    json.dumps(
                        {"sha256": sha256(p), "bytes": p.stat().st_size, "row_n": len(rows)}
                    ),
                    encoding="utf-8",
                )
                return p

            row = {"stdr_yyqu_cd": "20252", "trdar_cd": "a"}
            p = save([row])
            self.assertEqual(public_rows(root, "floating", "20252")[0]["TRDAR_CD"], "a")
            p.write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                public_rows(root, "floating", "20252")
            for rows in ([row, row], [{**row, "stdr_yyqu_cd": "20262"}], []):
                save(rows)
                with self.assertRaises(ValueError):
                    public_rows(root, "floating", "20252")
            save([{**row, "stdr_yyqu_cd": "20262"}], "20262")
            with self.assertRaises(ValueError):
                public_rows(root, "floating", "20262")

    def test_copy_excludes_future_numeric_rows_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = LocalDataDB(root / "original.sqlite3")
            versions = []
            for source in ("floating", "lifecycle"):
                for q in ("20252", "20262"):
                    vid = original.stage(source, q, [{"row_key": "a", "payload": {"period": q}}], q)
                    versions.append(original.version(vid))
            source_hash = sha256(original.path)
            target = LocalDataDB(root / "target.sqlite3")
            ids = copy_past(original.path, target, versions)
            self.assertEqual(len(ids), 2)
            with target.connection() as db:
                self.assertEqual(
                    {r[0] for r in db.execute("SELECT quarter FROM data_versions")}, {"20252"}
                )
            self.assertEqual(sha256(original.path), source_hash)


class PastScoringTests(unittest.TestCase):
    def test_calibration_restores_every_global_on_error(self):
        old_age = baseline.AGE_SHARE_AVG
        old_density = scoring.SEOUL_INDUSTRY_DENSITY_PERCENTILES
        old_quarter = scoring.BASELINE_BASE_QUARTER
        values = {
            "population": {"AGE_SHARE_AVG": {"20": 0.5}},
            "density": {},
            "lifecycle": {},
            "cutoff": "20252",
            "quarter_count": 12,
        }
        with self.assertRaisesRegex(RuntimeError, "stop"):
            with calibrated(values):
                self.assertEqual(baseline.AGE_SHARE_AVG, {"20": 0.5})
                self.assertEqual(scoring.BASELINE_BASE_QUARTER, "20252")
                raise RuntimeError("stop")
        self.assertIs(baseline.AGE_SHARE_AVG, old_age)
        self.assertIs(scoring.SEOUL_INDUSTRY_DENSITY_PERCENTILES, old_density)
        self.assertEqual(scoring.BASELINE_BASE_QUARTER, old_quarter)

    def test_continuous_variant_keeps_unknown_and_original_observations(self):
        rows = [
            {
                "items": {
                    "S1": {**scoring.result("S1", 2, value=0.97)},
                    "S2": scoring.result("S2"),
                    "S3": scoring.result("S3"),
                    "S4": scoring.result("S4"),
                }
            }
        ]
        changed = continuous_rows(rows)
        self.assertEqual(rows[0]["items"]["S1"]["points"], 3.75)
        self.assertAlmostEqual(changed[0]["items"]["S1"]["points"], 4.3125)
        for item in ("S2", "S3", "S4"):
            self.assertEqual(changed[0]["items"][item], rows[0]["items"][item])
            self.assertIsNone(changed[0]["items"][item]["points"])

    def test_real_zero_is_observed_but_policy_fixed_is_separate(self):
        self.assertEqual(item_kind("C1", scoring.result("C1", 0, value=0)), "observed")
        self.assertEqual(item_kind("C1", scoring.result("C1", 2, value=None)), "profile_fixed")

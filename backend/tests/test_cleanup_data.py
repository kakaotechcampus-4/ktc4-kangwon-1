"""자료 묶음·체크포인트·실패 정리를 임시 DB와 API 대역으로 검증합니다."""

import argparse
import asyncio
import json
import os
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.local_data.database import DataValidationError, LocalDataDB
from app.local_data.refresh import collect_pages
from app.seoul import previous_quarter
from scripts.refresh_local_data import parser, refresh


class CleanupDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = LocalDataDB(Path(self.temp.name) / "market.sqlite3")

    def stage(self, source, quarter="", tag="a", count=1):
        return self.db.stage(
            source,
            quarter,
            [{"row_key": str(n), "payload": {"value": tag}} for n in range(count)],
            tag + quarter + str(count),
        )

    def bundle(self, latest="20262", tag="a"):
        versions = []
        for source, count in (("lifecycle", 12), ("floating", 5)):
            quarter = latest
            for _ in range(count):
                versions.append(self.stage(source, quarter, tag))
                quarter = previous_quarter(quarter)
        for source in ("stores", "resident", "worker"):
            versions.append(self.stage(source, latest, tag))
        versions.append(self.stage("areas", tag=tag))
        return versions

    def test_validation_error_is_not_input_value_error(self):
        self.assertFalse(issubclass(DataValidationError, ValueError))

    def test_complete_bundle_and_previous_release_are_preserved(self):
        first = self.bundle(tag="a")
        self.db.activate(first)
        second = self.bundle(tag="b")
        self.db.activate(second)
        unused = self.stage("seoul_boundary", tag="unused")
        self.db.activate(second)
        self.assertIsNone(self.db.version(unused))
        self.assertEqual(self.db.release_count(), 2)
        self.assertTrue(all(self.db.version(v) for v in first))
        third = self.bundle(tag="c")
        self.db.activate(third)
        self.assertTrue(all(self.db.version(v) is None for v in first))
        self.assertTrue(all(self.db.version(v) for v in second))
        self.assertEqual(set(self.db.active_versions()), set(third))

    def test_incomplete_and_misaligned_bundles_are_rejected_atomically(self):
        active = self.bundle()
        self.db.activate(active)
        for defect in ("missing", "lifecycle", "floating", "resident", "worker", "stores"):
            with self.subTest(defect=defect):
                selected = self.bundle(tag=defect)
                if defect == "missing":
                    selected = [v for v in selected if self.db.version(v)["source"] != "areas"]
                elif defect in ("lifecycle", "floating"):
                    selected.remove(
                        next(v for v in selected if self.db.version(v)["source"] == defect)
                    )
                else:
                    selected = [v for v in selected if self.db.version(v)["source"] != defect]
                    selected.append(self.stage(defect, "20261", defect))
                with self.assertRaises(DataValidationError):
                    self.db.activate(selected)
                self.assertEqual(set(self.db.active_versions()), set(active))
                self.assertEqual(self.db.release_count(), 1)
                with self.db.connection() as con:
                    self.assertEqual(
                        con.execute(
                            "SELECT COUNT(*) FROM data_versions WHERE state='staged'"
                        ).fetchone()[0],
                        0,
                    )

    def test_gap_and_row_count_drift_are_rejected(self):
        active = self.bundle()
        self.db.activate(active)
        selected = self.bundle(tag="gap")
        selected.remove(next(v for v in selected if self.db.version(v)["source"] == "lifecycle"))
        selected.append(self.stage("lifecycle", "20231", "gap"))
        with self.assertRaises(DataValidationError):
            self.db.activate(selected)
        selected = self.bundle(tag="drift")
        selected = [v for v in selected if self.db.version(v)["source"] != "stores"]
        selected.append(self.stage("stores", "20262", "drift", 3))
        with self.assertRaises(DataValidationError):
            self.db.activate(selected)
        self.assertEqual(set(self.db.active_versions()), set(active))

    @staticmethod
    def page(start, total=1001, tag="new"):
        return {
            "list_total_count": total,
            "row": [{"id": n, "tag": tag} for n in range(start, min(start + 999, total) + 1)],
        }

    def test_first_page_change_recollects_same_total(self):
        self.db.save_page("key", 1, self.page(1, tag="old"))
        self.db.save_page("key", 1001, self.page(1001, tag="old"))
        fetch = AsyncMock(side_effect=lambda start, end: self.page(start))
        rows, used = asyncio.run(collect_pages(self.db, "key", fetch))
        self.assertEqual(used, 2)
        self.assertTrue(all(row["tag"] == "new" for row in rows))

    def test_resume_revalidates_first_page_and_reuses_remaining_pages(self):
        self.db.save_page("key", 1, self.page(1))
        self.db.save_page("key", 1001, self.page(1001))
        fetch = AsyncMock(side_effect=lambda start, end: self.page(start))
        rows, used = asyncio.run(collect_pages(self.db, "key", fetch))
        self.assertEqual(len(rows), 1001)
        self.assertEqual(used, 1)
        fetch.assert_awaited_once_with(1, 1000)

    def test_total_change_clears_and_recollects(self):
        fetch = AsyncMock(
            side_effect=[
                self.page(1),
                self.page(1001, 1002),
                self.page(1, 1002),
                self.page(1001, 1002),
            ]
        )
        rows, used = asyncio.run(collect_pages(self.db, "key", fetch))
        self.assertEqual(len(rows), 1002)
        self.assertEqual(used, 4)
        self.assertEqual(self.db.page("key", 1)["list_total_count"], 1002)

    def test_repeated_total_change_leaves_recoverable_empty_checkpoint(self):
        fetch = AsyncMock(
            side_effect=[
                self.page(1),
                self.page(1001, 1002),
                self.page(1, 1002),
                self.page(1001, 1003),
            ]
        )
        with self.assertRaises(DataValidationError):
            asyncio.run(collect_pages(self.db, "key", fetch))
        self.assertIsNone(self.db.page("key", 1))
        self.assertIsNone(self.db.page("key", 1001))

    def test_expired_and_old_format_checkpoints_are_discarded(self):
        for key, body in (
            ("legacy", self.page(1)),
            (
                "expired",
                {
                    "collected_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                    "body": self.page(1),
                },
            ),
        ):
            with self.subTest(key=key), self.db.connection() as con:
                con.execute("INSERT INTO api_pages VALUES(?,?,?)", (key, 1, json.dumps(body)))
                con.execute("INSERT INTO api_pages VALUES(?,?,?)", (key, 1001, json.dumps(body)))
            self.assertIsNone(self.db.page(key, 1))
            self.assertIsNone(self.db.page(key, 1001))

    def test_refresh_failure_clears_staged_and_preserves_active(self):
        active = self.bundle()
        self.db.activate(active)

        async def failed_refresh(args, db):
            db.stage("resident", "20262", [{"row_key": "x", "payload": {"x": 1}}], "failed")
            raise DataValidationError("대역 검증 실패")

        with patch("scripts.refresh_local_data._refresh", side_effect=failed_refresh):
            with self.assertRaises(DataValidationError):
                asyncio.run(refresh(argparse.Namespace(), self.db))
        self.assertEqual(set(self.db.active_versions()), set(active))
        with self.db.connection() as con:
            self.assertEqual(
                con.execute("SELECT COUNT(*) FROM data_versions WHERE state='staged'").fetchone()[
                    0
                ],
                0,
            )

    def test_reset_checkpoint_option(self):
        self.assertTrue(parser().parse_args(["--reset-checkpoint"]).reset_checkpoint)

    def test_store_validation_failure_removes_staged_version(self):
        path = Path(self.temp.name) / "stores.csv"
        args = parser().parse_args(["--source", "stores", "--seoul-csv", str(path)])
        with (
            patch("scripts.refresh_local_data.file_hash", return_value="invalid-store"),
            patch(
                "scripts.refresh_local_data.store_rows",
                return_value=[{"row_key": "x", "payload": {"x": 1}, "district_code": "11110"}],
            ),
        ):
            with self.assertRaises(DataValidationError):
                asyncio.run(refresh(args, self.db))
        with self.db.connection() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM data_versions").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM stores").fetchone()[0], 0)

    def test_reset_clears_checkpoint_before_collection(self):
        key = "v1:VwsmTrdarFlpopQq:20262"
        self.db.save_page(key, 1, self.page(1))
        args = parser().parse_args(["--source", "floating", "--reset-checkpoint"])

        async def collect(db, checkpoint, fetch):
            self.assertEqual(checkpoint, key)
            self.assertIsNone(db.page(checkpoint, 1))
            raise DataValidationError("대역 수집 중단")

        with (
            patch.dict(os.environ, {"FLOATING_POPULATION_API_KEY": "fake"}),
            patch("scripts.refresh_local_data.collect_pages", side_effect=collect),
        ):
            with self.assertRaises(DataValidationError):
                asyncio.run(refresh(args, self.db))


if __name__ == "__main__":
    unittest.main()

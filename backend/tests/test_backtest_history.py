import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.local_data.database import LocalDataDB
from backtest.history import HistoryDataError, check_history_db, main
from tests.local_data_fixture import complete_versions

STORE = {
    "row_key": "s1",
    "payload": {"상호명": "가"},
    "area_code": "a",
    "industry_code": "G202",
    "district_code": "11680",
    "latitude": 37.5,
    "longitude": 127.0,
}


def build_db(path: Path, quarter: str) -> None:
    db = LocalDataDB(path)
    seed = db.stage("stores", quarter, [STORE], "seed")
    db.activate(complete_versions(db, [seed], quarter))


class HistoryTests(unittest.TestCase):
    def test_accepts_a_complete_past_release(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "market_20234.sqlite3"
            build_db(path, "20234")
            info = check_history_db(path, "20234")
        sources = [v["source"] for v in info["versions"]]
        self.assertEqual(info["release_count"], 1)
        self.assertEqual(sources.count("lifecycle"), 12)
        self.assertEqual(sources.count("floating"), 5)
        stores = {v["quarter"] for v in info["versions"] if v["source"] == "stores"}
        self.assertEqual(stores, {"20234"})

    def test_rejects_a_release_of_another_quarter(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "market.sqlite3"
            build_db(path, "20262")
            with self.assertRaises(HistoryDataError) as caught:
                check_history_db(path, "20234")
        self.assertIn("20262", str(caught.exception))

    def test_rejects_the_service_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "market.sqlite3"
            build_db(path, "20234")
            with patch("backtest.history.default_path", return_value=path):
                with self.assertRaises(HistoryDataError) as caught:
                    check_history_db(path, "20234")
        self.assertIn("서비스 자료 DB", str(caught.exception))

    def test_rejects_a_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(HistoryDataError):
                check_history_db(Path(folder) / "none.sqlite3", "20234")

    def test_main_returns_one_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = Path(folder) / "none.sqlite3"
            self.assertEqual(main(["--data", str(missing), "--quarter", "20234"]), 1)


if __name__ == "__main__":
    unittest.main()

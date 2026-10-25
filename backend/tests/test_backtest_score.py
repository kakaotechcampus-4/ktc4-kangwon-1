import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backtest.baselines import swapped
from backtest.ranking import rank_rows
from backtest.score import score_address
from tests.backtest_fixture import build_market, file_values

MISMATCH = "개폐업 기준선 분석 기간 불일치"


def run_score(root: Path, values=None):
    site = build_market(root / "market_20234.sqlite3", "20234")

    async def run():
        with (
            patch("httpx.AsyncClient", side_effect=AssertionError("API 금지")),
            patch("backtest.score.collect_preflight", AsyncMock(return_value=({}, None))),
        ):
            return await score_address(
                site.input_address,
                local_data_path=root / "market_20234.sqlite3",
                db_path=root / "requests.sqlite3",
                request_id="bt-test",
                resolve=AsyncMock(return_value=site),
            )

    if values is None:
        return asyncio.run(run())
    with swapped(values):
        return asyncio.run(run())


class ScoreAddressTests(unittest.TestCase):
    def test_scores_all_industries_from_the_past_release(self):
        with tempfile.TemporaryDirectory() as folder:
            _, data, report = run_score(Path(folder))
        self.assertEqual(len(report["rows"]), 51)
        self.assertEqual(data["area_selection"]["area_code"], "a")
        self.assertEqual(rank_rows(report["rows"])[0]["rank"], 1)
        reasons = {row["items"]["S1"]["reason"] for row in report["rows"]}
        self.assertIn(MISMATCH, reasons)

    def test_swapped_quarter_removes_the_period_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            _, _, report = run_score(Path(folder), file_values("20234"))
        reasons = {row["items"]["S1"]["reason"] for row in report["rows"]}
        self.assertNotIn(MISMATCH, reasons)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from app.application.facts import register_fact
from app.application.report import fact_rows
from app.infrastructure.persistence.connection import connect, initialize
from app.infrastructure.persistence.raw_capture import capture_scope
from app.infrastructure.persistence.repository import create_request


class ReportFactRowsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "db.sqlite3"
        initialize(self.path)
        create_request("loop", "시험", db_path=self.path)
        self.manager = capture_scope("loop", self.path)
        self.scope = await self.manager.__aenter__()

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_fact_rows_keep_pre_move_query_order(self):
        response = await self.scope.record(
            source="floating_population",
            source_type="api",
            args={},
            page="test",
            status=200,
            payload={"rows": [{"age": str(age), "share": 0.1} for age in range(12)]},
        )
        with connect(self.path) as db:
            ref = db.execute(
                "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
            ).fetchone()[0]
        ids = [
            register_fact(
                self.scope,
                industry_code=None,
                source="floating_population",
                metric="age_share",
                value={str(age): 0.1},
                unit="비율",
                status="observed",
                row_ids=[ref],
            )
            for age in range(12)
        ]
        with connect(self.path) as db:
            before = [
                row[0]
                for row in db.execute(
                    "SELECT *,EXISTS(SELECT 1 FROM local_fact_lineage l "
                    "WHERE l.fact_id=facts.fact_id) AS local_lineage FROM facts "
                    "WHERE request_id=? AND snapshot_id=? AND fact_id IN ("
                    + ",".join("?" for _ in ids)
                    + ")",
                    [self.scope.request_id, self.scope.snapshot_id, *ids],
                )
            ]
        self.assertNotEqual(before, sorted(before))
        self.assertEqual(list(fact_rows(self.scope, ids)), before)


if __name__ == "__main__":
    unittest.main()

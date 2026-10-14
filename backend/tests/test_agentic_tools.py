"""현재 스냅샷 SQL 격리·도구 권한·결정론 지도를 검증합니다."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.schemas import Site
from app.storage.raw import capture_scope


class RawToolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "db.sqlite3"
        initialize(self.path)
        create_request("one", "시험", radius_m=500, db_path=self.path)
        create_request("two", "다른 요청", radius_m=500, db_path=self.path)
        self.manager = capture_scope("one", self.path)
        self.scope = await self.manager.__aenter__()
        await self.scope.record(
            source="business_lifecycle",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={
                "rows": [
                    {"SIMILR_INDUTY_STOR_CO": i, "SVC_INDUTY_CD": "CS100001"} for i in range(60)
                ]
            },
        )
        async with capture_scope("two", self.path) as other:
            await other.record(
                source="business_lifecycle",
                source_type="api",
                args={},
                page="1",
                status=200,
                payload={"rows": [{"SIMILR_INDUTY_STOR_CO": 999}]},
            )

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_direct_field_registered_and_request_isolation(self):
        from app.agents.agentic.raw_query import query_raw

        reply = await query_raw(
            self.scope, "SELECT raw_row_id, store_count FROM v_raw_lifecycle WHERE store_count=5"
        )
        self.assertEqual(reply.status, "ok")
        self.assertEqual(reply.data.rows[0].values["store_count"], 5)
        self.assertEqual(len(reply.data.rows[0].fact_ids), 1)
        with connect(self.path) as db:
            fact = db.execute("SELECT value_json FROM facts").fetchone()
        self.assertEqual(json.loads(fact[0]), 5)
        foreign = await query_raw(
            self.scope, "SELECT raw_row_id, store_count FROM v_raw_lifecycle WHERE request_id='two'"
        )
        self.assertEqual(foreign.data.rows, [])

    async def test_aggregate_uncitable_and_row_limit(self):
        from app.agents.agentic.raw_query import query_raw

        aggregate = await query_raw(
            self.scope, "SELECT sum(store_count) AS total FROM v_raw_lifecycle"
        )
        self.assertEqual(aggregate.data.uncitable_columns, ["total"])
        self.assertEqual(aggregate.data.rows[0].fact_ids, [])
        limited = await query_raw(self.scope, "SELECT raw_row_id, store_count FROM v_raw_lifecycle")
        self.assertEqual(len(limited.data.rows), 50)
        self.assertTrue(limited.truncated)

    async def test_denied_statements_and_functions(self):
        from app.agents.agentic.raw_query import query_raw

        for sql in [
            "DELETE FROM raw_rows",
            "CREATE TABLE x(a)",
            "PRAGMA table_info(raw_rows)",
            "ATTACH ':memory:' AS other",
            "SELECT 1; SELECT 2",
            "WITH x AS (SELECT 1) SELECT * FROM x",
            "SELECT * FROM raw_rows",
            "SELECT * FROM sqlite_master",
            "SELECT load_extension('x')",
            "SELECT raw_request_id()",
            "SELECT * FROM facts",
        ]:
            with self.subTest(sql=sql):
                reply = await query_raw(self.scope, sql)
                self.assertEqual(reply.error.code, "SQL_DENIED")

    async def test_sql_timeout(self):
        from app.agents.agentic.raw_query import query_raw

        with patch("app.agents.agentic.raw_query.monotonic", side_effect=[0, 0, 3, 3, 3]):
            reply = await query_raw(
                self.scope,
                "SELECT sum(a.store_count*b.store_count) "
                "FROM v_raw_lifecycle a CROSS JOIN v_raw_lifecycle b",
            )
        self.assertEqual(reply.error.code, "SQL_TIMEOUT")

    async def test_implicit_lineage_alias_and_expression_not_citable(self):
        from app.agents.agentic.raw_query import query_raw

        reply = await query_raw(
            self.scope, "SELECT store_count AS amount FROM v_raw_lifecycle WHERE store_count=5"
        )
        self.assertEqual(reply.data.columns, ["amount"])
        self.assertEqual(len(reply.data.rows[0].raw_row_refs), 1)
        self.assertEqual(len(reply.data.rows[0].fact_ids), 1)
        expression = await query_raw(
            self.scope,
            "SELECT raw_row_id, store_count*2 AS amount FROM v_raw_lifecycle WHERE store_count=5",
        )
        self.assertIn("amount", expression.data.uncitable_columns)
        self.assertEqual(expression.data.rows[0].fact_ids, [])

    async def test_fact_storage_error_is_not_tool_error(self):
        import sqlite3

        from app.agents.agentic.raw_query import query_raw

        with patch(
            "app.agents.agentic.raw_query.register_fact",
            side_effect=sqlite3.OperationalError("저장 실패"),
        ):
            with self.assertRaises(sqlite3.OperationalError):
                await query_raw(
                    self.scope, "SELECT store_count FROM v_raw_lifecycle WHERE store_count=5"
                )

    async def test_actor_permission_and_budget(self):
        from app.agents.agentic.tools import ToolExecutor

        tool = ToolExecutor(
            self.scope,
            Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0),
            actor="examiner",
        )
        self.assertEqual((await tool.execute("ask_user", {})).error.code, "INVALID_ARGUMENT")
        for i in range(2):
            await tool.execute(
                "query_raw",
                {"sql": f"SELECT store_count FROM v_raw_lifecycle WHERE store_count={i}"},
            )
        self.assertEqual(
            (await tool.execute("query_raw", {"sql": "SELECT 1"})).error.code, "BUDGET_EXCEEDED"
        )

    def executor(self):
        from app.agents.agentic.tools import ToolExecutor

        return ToolExecutor(
            self.scope,
            Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0),
        )

    async def test_denied_actor_attempts_consume_budget(self):
        tool = self.executor().for_actor("examiner")
        for _ in range(4):
            self.assertEqual((await tool.execute("ask_user", {})).error.code, "INVALID_ARGUMENT")
        self.assertEqual(
            (await tool.execute("query_raw", {"sql": "SELECT 1"})).error.code, "BUDGET_EXCEEDED"
        )

    async def test_all_views_are_request_scoped(self):
        from app.agents.agentic.raw_query import VIEWS, query_raw

        for view, source in VIEWS.items():
            await self.scope.record(
                source=source,
                source_type="api",
                args={},
                page="test",
                status=200,
                payload={"rows": [{"marker": "one"}]},
            )
            async with capture_scope("two", self.path) as other:
                await other.record(
                    source=source,
                    source_type="api",
                    args={},
                    page="test",
                    status=200,
                    payload={"rows": [{"marker": "two"}]},
                )
            reply = await query_raw(self.scope, f"SELECT request_id FROM {view}")
            self.assertTrue(reply.data.rows)
            self.assertEqual({r.values["request_id"] for r in reply.data.rows}, {"one"})

    async def test_stored_regulation_avoids_requery(self):
        async def forbidden(*args, **kwargs):
            self.fail("저장된 규제 원문이 있으면 API를 다시 부르면 안 됩니다.")

        await self.scope.record(
            source="regulation",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [{"status": "ok", "queried_at": "2026-10-14", "zones": []}]},
        )
        tool = self.executor()
        tool.shared.regulation_lookup = forbidden
        reply = await tool.execute("check_regulation", {})
        self.assertTrue(reply.data.contains_verified)

    async def test_stored_score_and_facts_are_typed(self):
        from app.agents.agentic.contracts import FactsResult, ScorecardResult
        from app.agents.agentic.registry import persist_report
        from app.agents.agentic.scoring import WEIGHTS, result, summarize

        items = {key: result(key) for key in WEIGHTS}
        row = summarize("I201", items, "unknown")
        persist_report(self.scope, {"rows": [row], "top5": [row]}, {}, [])
        tool = self.executor()
        reply = await tool.execute("get_scorecard", {"mode": "detail", "limit": 5})
        data = ScorecardResult.model_validate(reply.data)
        self.assertEqual(len(data.scorecards[0].items), 11)
        fact_id = data.scorecards[0].items[0].fact_ids[0]
        reply = await tool.execute("get_facts", {"fact_ids": [fact_id]})
        data = FactsResult.model_validate(reply.data)
        self.assertEqual(data.facts[0].status, "unknown")
        self.assertFalse(data.facts[0].citable)
        unknown = await tool.for_actor("founder").execute(
            "get_facts", {"fact_ids": ["f_00000000-0000-0000-0000-000000000000"]}
        )
        self.assertEqual(unknown.error.code, "UNKNOWN_FACT")

    async def test_duplicate_and_invalid_argument(self):
        tool = self.executor()
        self.assertEqual(
            (await tool.execute("query_raw", {"sql": "SELECT 1", "max_rows": 51})).error.code,
            "INVALID_ARGUMENT",
        )
        await tool.execute("query_raw", {"sql": "SELECT count(*) FROM v_raw_lifecycle"})
        self.assertEqual(
            (
                await tool.execute("query_raw", {"sql": "SELECT count(*) FROM v_raw_lifecycle"})
            ).error.code,
            "DUPLICATE_CALL",
        )

    async def test_map_no_llm_statuses_and_shared_cache(self):
        from app.agents.agentic.contracts import MapResult

        class Places:
            calls = 0

            async def search_keyword(self, *args, **kwargs):
                self.calls += 1
                return {
                    "meta": {"is_end": False, "total_count": 40},
                    "documents": [
                        {
                            "id": "1",
                            "place_name": "가게",
                            "category_name": "음식점 > 중식",
                            "category_group_code": "FD6",
                            "distance": "10",
                        },
                        {
                            "id": "2",
                            "place_name": "중식 가게",
                            "category_name": "기타",
                            "distance": "20",
                        },
                        {
                            "id": "3",
                            "place_name": "미확인",
                            "category_name": "기타",
                            "distance": "30",
                        },
                    ],
                }

        tool = self.executor()
        client = Places()
        tool.shared.map_client = client
        with patch("app.llm.session._new_client", side_effect=AssertionError("모델 생성 금지")):
            reply = await tool.execute("map_search", {"industry_code": "I202", "radius_m": 500})
            second = await tool.for_actor("founder").execute(
                "map_search", {"industry_code": "I202", "radius_m": 500}
            )
        data = MapResult.model_validate(reply.data)
        self.assertEqual(
            [p.match_status for p in data.places], ["category_match", "name_match", "unknown"]
        )
        self.assertTrue(data.has_more)
        self.assertEqual(reply.data, second.data)
        self.assertEqual(client.calls, tool.shared.map_http)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM facts WHERE source='map'").fetchone()[0],
                9 * client.calls,
            )

    async def test_map_limits_and_empty_not_absence(self):
        class Places:
            calls = 0

            async def search_category(self, *args):
                self.calls += 1
                return {"meta": {"is_end": True, "total_count": 0}, "documents": []}

        tool = self.executor()
        tool.shared.map_client = Places()
        for radius in [50, 100, 150, 200, 250, 300]:
            reply = await tool.execute("map_search", {"facility_code": "SW8", "radius_m": radius})
            self.assertIn("0건", reply.warnings[0])
        reply = await tool.execute("map_search", {"facility_code": "SW8", "radius_m": 350})
        self.assertEqual(reply.error.code, "BUDGET_EXCEEDED")
        tool = self.executor()
        tool.shared.map_client = Places()
        tool.shared.map_http = 20
        reply = await tool.execute("map_search", {"facility_code": "SW8", "radius_m": 50})
        self.assertEqual(reply.error.code, "BUDGET_EXCEEDED")
        self.assertEqual(tool.shared.map_client.calls, 0)

    async def test_regulation_shared_original_output_and_unverified(self):
        from app.agents.agentic.contracts import RegulationResult
        from app.education_zone import EducationZoneScan

        scan = EducationZoneScan(
            status="ok",
            center={"latitude": 37.5, "longitude": 127.0},
            queried_at="2026-10-14",
            zones=[],
        )
        calls = []

        async def lookup(*args, **kwargs):
            calls.append(args)
            return scan

        tool = self.executor()
        tool.shared.regulation_lookup = lookup
        reply = await tool.execute("check_regulation", {})
        data = RegulationResult.model_validate(reply.data)
        self.assertEqual(data.zones, scan.model_dump(mode="json")["zones"])
        self.assertEqual(data.status, scan.status)
        self.assertEqual(data.queried_at, scan.queried_at)
        self.assertTrue(data.contains_verified)
        await tool.for_actor("examiner").execute("check_regulation", {})
        self.assertEqual(len(calls), 1)
        tool = self.executor()
        tool.shared.regulation_scan = {
            "status": "ok",
            "queried_at": "2026-10-14",
            "zones": [{"name": "절대보호구역", "geometry": None}],
        }
        data = (await tool.execute("check_regulation", {})).data
        self.assertFalse(data.contains_verified)
        self.assertEqual(
            next(r.status for r in data.industry_restrictions if r.industry_code == "I101"),
            "unknown",
        )

    async def test_regulation_only_containing_polygon_blocks(self):
        tool = self.executor()
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [[127.1, 37.4], [127.2, 37.4], [127.2, 37.6], [127.1, 37.6], [127.1, 37.4]]
            ],
        }
        tool.shared.regulation_scan = {
            "status": "ok",
            "queried_at": "2026-10-14",
            "zones": [{"name": "절대보호구역", "geometry": polygon}],
        }
        data = (await tool.execute("check_regulation", {})).data
        self.assertTrue(data.contains_verified)
        self.assertEqual(
            next(r.status for r in data.industry_restrictions if r.industry_code == "I101"),
            "해당 없음",
        )


if __name__ == "__main__":
    unittest.main()

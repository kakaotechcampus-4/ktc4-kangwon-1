"""원문 저장·보안·요청 격리는 실제 SQLite와 전송 대역으로 확인합니다."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.storage.raw import RawStorageError, capture_http, capture_scope, scoped_reader, scrub


class RawCaptureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = initialize(Path(self.tmp.name) / "raw.sqlite3")
        for request in ("one", "two"):
            create_request(request, "서울 목업", db_path=self.path)

    def tearDown(self):
        self.tmp.cleanup()

    async def record(self, scope, source="commercial_area", page=1, total=1):
        await scope.record(
            source=source,
            source_type="api",
            args={"query": {"pageNo": page}, "secret": "ignore"},
            page=str(page),
            status=200,
            payload={
                "response": {
                    "body": {
                        "items": [{"bizesId": "excluded", "indsMclsCd": "G206", "extra_column": 7}],
                        "totalCount": total,
                    }
                }
            },
        )

    async def test_original_rows_and_page_duplicates(self):
        async with capture_scope("one", self.path) as scope:
            await self.record(scope)
            await self.record(scope)
            snapshot = scope.snapshot_id
        with scoped_reader(self.path, "one", snapshot) as db:
            rows = db.execute("SELECT raw_json FROM v_raw_stores").fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(json.loads(rows[0][0])["extra_column"], 7)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT count(*) FROM raw_responses WHERE duplicate_of IS NOT NULL"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(db.execute("SELECT count(*) FROM raw_rows").fetchone()[0], 1)

    async def test_partial_pages(self):
        async with capture_scope("one", self.path) as scope:
            await self.record(scope, total=3)
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT completeness FROM snapshots").fetchone()[0], "partial"
            )

    async def test_snapshot_is_single_across_runs(self):
        async with capture_scope("one", self.path) as first:
            await self.record(first)
        async with capture_scope("one", self.path) as second:
            await self.record(second)
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertNotEqual(first.run_id, second.run_id)
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM snapshots").fetchone()[0], 1)
            self.assertEqual(
                db.execute("SELECT count(DISTINCT run_id) FROM raw_responses").fetchone()[0], 2
            )

    async def test_scrub_url_query_headers_and_echo(self):
        secret = "private-secret-123"
        response = httpx.Response(
            200,
            json={"RESULT": {"MESSAGE": secret}, "rows": []},
            request=httpx.Request(
                "GET",
                f"http://openapi.seoul.go.kr/{secret}/json/VwsmTrdarFlpopQq/1/1000/?serviceKey={secret}",
                headers={"Authorization": "Bearer " + secret, "Referer": secret},
            ),
        )
        async with capture_scope("one", self.path):
            await capture_http(
                "floating_population",
                response,
                secrets=[secret],
                args={"url": str(response.request.url), "headers": dict(response.request.headers)},
                page="1",
            )
        with connect(self.path) as db:
            row = db.execute(
                "SELECT p.request_args_json,b.response_json FROM raw_responses p "
                "JOIN raw_payloads b USING(payload_hash)"
            ).fetchone()
            stored = " ".join(row)
            self.assertNotIn(secret, stored)
            self.assertNotIn("Authorization", stored)
            self.assertNotIn("Referer", stored)
        self.assertNotIn(
            secret,
            json.dumps(
                scrub({"url": f"https://x/{secret}?api_key={secret}", "api_key": secret}, [secret])
            ),
        )

    async def test_all_views_are_request_scoped(self):
        sources = {
            "v_raw_stores": "commercial_area",
            "v_raw_lifecycle": "business_lifecycle",
            "v_raw_floating": "floating_population",
            "v_raw_resident": "resident_population",
            "v_raw_worker": "worker_population",
        }
        snapshots = {}
        for request in ("one", "two"):
            async with capture_scope(request, self.path) as scope:
                snapshots[request] = scope.snapshot_id
                for source in sources.values():
                    await self.record(scope, source)
        for request in ("one", "two"):
            with scoped_reader(self.path, request, snapshots[request]) as db:
                for view in sources:
                    rows = db.execute(f"SELECT request_id FROM {view}").fetchall()
                    self.assertEqual([r[0] for r in rows], [request])
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM v_raw_stores").fetchone()[0], 0)

    async def test_csv_capture_even_when_parser_cache_is_warm(self):
        from app.agents.floating_population.population import SNAPSHOT_PATHS, load_snapshot

        load_snapshot("REPOP")
        async with capture_scope("one", self.path):
            await asyncio.to_thread(load_snapshot, "REPOP")
        with connect(self.path) as db:
            row = db.execute(
                "SELECT source_type,request_args_json FROM raw_responses WHERE "
                "source='resident_population'"
            ).fetchone()
            self.assertEqual(row[0], "file")
            args = json.loads(row[1])
            self.assertEqual(len(args["file_hash"]), 64)
            self.assertEqual(args["file_name"], SNAPSHOT_PATHS["REPOP"].name)
            self.assertTrue(args["quarter"])

    async def test_storage_failure_is_not_an_agent_result(self):
        from app.mocks import mock_agents, mock_generate, mock_resolve
        from app.services.analysis import execute_analysis

        async def broken(task):
            with patch("app.storage.raw._save_response", side_effect=OSError("secret")):
                await capture_http(
                    "commercial_area",
                    httpx.Response(
                        200, json={}, request=httpx.Request("GET", "https://example.invalid")
                    ),
                )
            return await mock_agents()["commercial_area"](task)

        agents = mock_agents()
        agents["commercial_area"] = broken
        with self.assertRaises(RawStorageError):
            await execute_analysis(
                "서울",
                request_id="failed",
                db_path=self.path,
                resolve=mock_resolve,
                agents=agents,
                generate=mock_generate,
            )
        with connect(self.path) as db:
            row = db.execute(
                "SELECT status,error_json FROM analysis_requests WHERE request_id='failed'"
            ).fetchone()
            self.assertEqual(row[0], "failed")
            self.assertNotIn("secret", row[1])

    async def test_http_hooks_capture_before_field_reduction(self):
        from app.agents.business_lifecycle.client import request_page
        from app.agents.commercial_area.client import StoreClient
        from app.agents.commercial_area.config import Settings as StoreSettings
        from app.agents.floating_population.client import SeoulOpenDataClient
        from app.agents.floating_population.config import Settings as PopulationSettings

        def transport(request):
            if "openapi.seoul" in request.url.host:
                service = (
                    "VwsmTrdarStorQq"
                    if "VwsmTrdarStorQq" in request.url.path
                    else "VwsmTrdarFlpopQq"
                )
                return httpx.Response(
                    200,
                    json={
                        service: {
                            "RESULT": {"CODE": "INFO-000"},
                            "list_total_count": 1,
                            "row": [
                                {"STDR_YYQU_CD": "20262", "TRDAR_CD": "100", "unparsed_field": 17}
                            ],
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "response": {
                        "header": {"resultCode": "00"},
                        "body": {
                            "items": [
                                {
                                    "bizesId": "excluded",
                                    "indsLclsCd": "G",
                                    "indsMclsCd": "G206",
                                    "lat": "37.5",
                                    "lon": "127.0",
                                    "unparsed_field": 19,
                                }
                            ],
                            "totalCount": 1,
                        },
                    }
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            async with capture_scope("one", self.path):
                await request_page("SECRET", "20262", "100", 1, 1000, http=http)
                population = SeoulOpenDataClient(PopulationSettings(api_key="SECRET"), http=http)
                await population._get("VwsmTrdarFlpopQq", 1, 1000, extra="20262")
                store = StoreClient(
                    StoreSettings(sbiz_service_key="SECRET", cache_dir=Path(self.tmp.name)),
                    client=http,
                )
                await store.stores_in_radius(37.5, 127.0, 500, use_cache=False)
        with connect(self.path) as db:
            rows = db.execute(
                "SELECT p.source,p.request_args_json,b.response_json FROM raw_responses p "
                "JOIN raw_payloads b USING(payload_hash)"
            ).fetchall()
            self.assertEqual(
                {r[0] for r in rows},
                {"business_lifecycle", "floating_population", "commercial_area"},
            )
            for row in rows:
                self.assertNotIn("SECRET", row[1] + row[2])
                self.assertIn("unparsed_field", row[2])
            self.assertEqual(db.execute("SELECT count(*) FROM raw_rows").fetchone()[0], 3)

    async def test_snapshot_finish_failure_prevents_completion(self):
        from app.mocks import mock_agents, mock_generate, mock_resolve
        from app.services.analysis import execute_analysis

        with (
            patch("app.storage.raw._finish", side_effect=OSError("secret")),
            self.assertRaises(RawStorageError),
        ):
            await execute_analysis(
                "서울",
                request_id="finish-failed",
                db_path=self.path,
                resolve=mock_resolve,
                agents=mock_agents(),
                generate=mock_generate,
            )
        with connect(self.path) as db:
            row = db.execute(
                "SELECT status FROM analysis_requests WHERE request_id='finish-failed'"
            ).fetchone()
            self.assertEqual(row[0], "failed")

    async def test_failed_http_keeps_partial_response(self):
        async with capture_scope("one", self.path):
            await capture_http(
                "floating_population",
                httpx.Response(
                    503,
                    json={"error": "upstream"},
                    request=httpx.Request("GET", "https://example.invalid"),
                ),
            )
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT completeness FROM snapshots").fetchone()[0], "partial"
            )
            self.assertEqual(db.execute("SELECT http_status FROM raw_responses").fetchone()[0], 503)

    async def test_cancellation_waits_for_write_then_marks_partial(self):
        import threading

        from app.storage import raw

        original = raw._save_response
        entered, release = threading.Event(), threading.Event()

        def blocked(*args, **kwargs):
            entered.set()
            release.wait(5)
            return original(*args, **kwargs)

        async def collect():
            async with capture_scope("one", self.path) as scope:
                await self.record(scope)

        with patch("app.storage.raw._save_response", side_effect=blocked):
            task = asyncio.create_task(collect())
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM raw_responses").fetchone()[0], 1)
            self.assertEqual(
                db.execute("SELECT completeness FROM snapshots").fetchone()[0], "partial"
            )

    def test_storage_failure_in_mixed_exception_group(self):
        from app.storage.raw import raise_storage_error

        error = ExceptionGroup(
            "병렬 오류",
            [RuntimeError("일반 API 실패"), ExceptionGroup("저장", [RawStorageError("저장 실패")])],
        )
        with self.assertRaises(RawStorageError):
            raise_storage_error(error)

    async def test_malformed_upstream_is_raw_data_not_storage_error(self):
        async with capture_scope("one", self.path):
            await capture_http(
                "commercial_area",
                httpx.Response(
                    200,
                    json={"response": "malformed"},
                    request=httpx.Request("GET", "https://example.invalid"),
                ),
            )
            await capture_http(
                "floating_population",
                httpx.Response(
                    200,
                    text='{"value":NaN}',
                    request=httpx.Request("GET", "https://example.invalid"),
                ),
            )
        with connect(self.path) as db:
            rows = db.execute("SELECT response_json FROM raw_payloads").fetchall()
            self.assertEqual(len(rows), 2)
            self.assertIn("unparsed_text", rows[1][0])
            self.assertEqual(
                db.execute("SELECT completeness FROM snapshots").fetchone()[0], "partial"
            )

    async def test_authorization_token_echo_is_redacted(self):
        response = httpx.Response(
            200,
            json={"echo": "header-only-secret"},
            request=httpx.Request(
                "GET",
                "https://example.invalid",
                headers={"Authorization": "Bearer header-only-secret"},
            ),
        )
        async with capture_scope("one", self.path):
            await capture_http("commercial_area", response)
        with connect(self.path) as db:
            row = db.execute("SELECT response_json FROM raw_payloads").fetchone()
            self.assertNotIn("header-only-secret", row[0])

    async def test_resume_without_collection_keeps_complete_snapshot(self):
        async with capture_scope("one", self.path) as first:
            await self.record(first)
        async with capture_scope("one", self.path):
            pass
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT completeness FROM snapshots").fetchone()[0], "complete"
            )

    async def test_later_decision_failure_keeps_completed_collection(self):
        with self.assertRaises(RuntimeError):
            async with capture_scope("one", self.path) as scope:
                await self.record(scope)
                await scope.finish()
                raise RuntimeError("판정 단계 실패")
        with connect(self.path) as db:
            self.assertEqual(
                db.execute("SELECT completeness FROM snapshots").fetchone()[0], "complete"
            )

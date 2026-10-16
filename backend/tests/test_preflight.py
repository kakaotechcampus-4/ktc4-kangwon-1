"""사전 관측의 채점·캐시 재사용·실패 경계를 네트워크 없이 검증합니다."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.agentic.contracts import MapResult, ToolReply
from app.agentic.preflight import FACILITIES, collect_preflight
from app.agentic.runtime import DecisionLoop
from app.agentic.scoring import evaluate
from app.agentic.tools import SharedTools, ToolExecutor
from app.agents.map_analysis.client import MapApiError
from app.concurrency import run_in_thread
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.local_data.persistence import persist_local
from app.schemas import AnalysisTask, Site
from app.storage.raw import RawStorageError, capture_scope


class PreflightTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "requests.sqlite3"
        initialize(self.path)
        create_request("preflight", "시험", radius_m=500, db_path=self.path)
        self.manager = capture_scope("preflight", self.path)
        self.scope = await self.manager.__aenter__()
        self.site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)
        self.client = AsyncMock()

        async def category(code, latitude, longitude, radius):
            return {
                "documents": [
                    {
                        "id": code,
                        "place_name": "시설",
                        "category_name": "시설 분류",
                        "category_group_code": code,
                        "distance": "100",
                    }
                ],
                "meta": {"is_end": False, "total_count": 25},
            }

        self.client.search_category.side_effect = category
        self.lookup = AsyncMock(
            return_value={
                "status": "ok",
                "queried_at": "2026-10-14T00:00:00Z",
                "center": {"latitude": 37.5, "longitude": 127.0},
                "zones": [
                    {
                        "name": "절대보호구역",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [126.99, 37.49],
                                    [127.01, 37.49],
                                    [127.01, 37.51],
                                    [126.99, 37.51],
                                    [126.99, 37.49],
                                ]
                            ],
                        },
                    }
                ],
            }
        )
        self.shared = SharedTools(map_client=self.client, regulation_lookup=self.lookup)

    async def asyncTearDown(self):
        await self.manager.__aexit__(None, None, None)
        self.temp.cleanup()

    async def test_five_queries_score_and_reuse_cached_observations(self):
        data, shared = await collect_preflight(self.scope, self.site, self.shared)
        self.assertEqual(shared.map_http, 5)
        self.assertEqual(self.client.search_category.await_count, 5)
        self.lookup.assert_awaited_once()
        self.assertTrue(data["education_zones"]["contains_verified"])
        report = evaluate({"address": "시험", **data})
        rows = {r["code"]: r for r in report["rows"]}
        self.assertEqual(rows["I101"]["regulation"], "금지")
        observed = [r for r in report["rows"] if r["items"]["C4"]["status"] == "observed"]
        self.assertEqual(len(observed), 6)
        self.assertTrue(data["limitations"])
        serialized = {k: v.model_dump(mode="json") for k, v in shared.map_cache.items()}
        restored = SharedTools(
            map_cache={k: ToolReply[MapResult].model_validate(v) for k, v in serialized.items()},
            regulation=shared.regulation,
            map_client=self.client,
        )
        tools = ToolExecutor(self.scope, self.site, shared=restored)
        for category in FACILITIES:
            reply = await tools.execute("map_search", {"facility_code": category, "radius_m": 500})
            self.assertEqual(reply.status, "partial")
        await tools.execute("check_regulation", {})
        self.assertEqual(self.client.search_category.await_count, 5)
        self.lookup.assert_awaited_once()
        with connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM raw_responses WHERE source IN ('map','regulation')"
                ).fetchone()[0],
                6,
            )

    async def test_one_source_failure_is_unknown_and_cached(self):
        category = self.client.search_category.side_effect

        async def fail_hospital(code, *args):
            if code == "HP8":
                raise MapApiError("UPSTREAM_FAILED", "실패")
            return await category(code, *args)

        self.client.search_category.side_effect = fail_hospital
        data, shared = await collect_preflight(self.scope, self.site, self.shared)
        rows = {r["code"]: r for r in evaluate({"address": "시험", **data})["rows"]}
        self.assertEqual(rows["G215"]["items"]["C4"]["status"], "unknown")
        self.assertEqual(rows["I101"]["regulation"], "금지")
        self.assertTrue(any("HP8" in text for text in data["limitations"]))
        await collect_preflight(self.scope, self.site, shared)
        self.assertEqual(self.client.search_category.await_count, 5)

    async def test_regulation_failure_preserves_facilities(self):
        from app.education_zone import EducationZoneError

        self.lookup.side_effect = EducationZoneError("CONFIG_ERROR", "실패")
        data, shared = await collect_preflight(self.scope, self.site, self.shared)
        rows = evaluate({"address": "시험", **data})["rows"]
        self.assertTrue(all(r["regulation"] == "unknown" for r in rows))
        self.assertEqual(sum(r["items"]["C4"]["status"] == "observed" for r in rows), 6)
        self.assertEqual(shared.regulation.status, "error")
        with connect(self.path) as db:
            raw = db.execute(
                "SELECT raw_json FROM raw_rows JOIN raw_response_rows USING(raw_row_id) "
                "JOIN raw_responses USING(response_id) WHERE source='regulation'"
            ).fetchone()
        self.assertEqual(json.loads(raw[0])["status"], "error")

    async def test_storage_and_contract_failures_propagate(self):
        for failure in (RawStorageError("저장 실패"), ValueError("계약 실패")):
            with patch("app.agentic.preflight.map_search", side_effect=failure):
                with self.assertRaises(type(failure)):
                    await collect_preflight(self.scope, self.site, self.shared)

    async def test_outside_polygon_does_not_prohibit(self):
        self.lookup.return_value["zones"][0]["geometry"]["coordinates"] = [
            [[128.0, 37.49], [128.01, 37.49], [128.01, 37.51], [128.0, 37.49]]
        ]
        data, _ = await collect_preflight(self.scope, self.site, self.shared)
        self.assertEqual(data["education_zones"]["zones"], [])
        self.assertTrue(data["education_zones"]["contains_verified"])
        rows = evaluate({"address": "시험", **data})["rows"]
        self.assertTrue(all(r["regulation"] == "해당 없음" for r in rows))

    async def test_persisted_scores_and_runtime_reload_reuse_observations(self):
        observations, shared = await collect_preflight(self.scope, self.site, self.shared)
        task = AnalysisTask(request_id="preflight", site=self.site, radius_m=500)
        adapter = SimpleNamespace(path=self.path, versions=[])
        data, report, score_id = await run_in_thread(
            persist_local,
            task,
            self.scope,
            adapter,
            {"address": "시험", "limitations": ["로컬 자료 한계"]},
            observations,
        )
        self.assertIn("로컬 자료 한계", data["limitations"])
        with connect(self.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM scores WHERE item='C4' AND status='observed'"
                ).fetchone()[0],
                6,
            )
            linked = db.execute(
                "SELECT COUNT(*) FROM fact_sources JOIN facts USING(fact_id) "
                "WHERE facts.source='map' AND facts.industry_code IS NOT NULL"
            ).fetchone()[0]
        self.assertGreater(linked, 0)
        loop = DecisionLoop(self.scope, self.site, score_id, report["rows"])
        loop.tools.shared = shared
        await loop.save()
        with connect(self.path) as db:
            saved = json.loads(db.execute("SELECT state_json FROM agentic_runs").fetchone()[0])
        restored = DecisionLoop(self.scope, self.site, score_id, report["rows"], saved=saved)
        for category in FACILITIES:
            reply = await restored.tools.execute(
                "map_search", {"facility_code": category, "radius_m": 500}
            )
            self.assertEqual(reply.status, "partial")
        await restored.tools.execute("check_regulation", {})
        self.assertEqual(restored.tools.shared.map_http, 5)
        self.assertEqual(self.client.search_category.await_count, 5)
        self.lookup.assert_awaited_once()

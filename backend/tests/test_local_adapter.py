"""로컬 자료의 버전 고정과 원문 복사 없는 분석을 검증합니다."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.commercial_area.client import CSV_FIELDS
from app.agents.floating_population.models import _AGE_KEYS, _DAY_KEYS, TIME_BANDS, PopulationRecord
from app.db import repository
from app.db.connection import connect, initialize
from app.geo import to_epsg5181
from app.local_data.adapter import LocalAdapter
from app.local_data.database import LocalDataDB
from app.local_data.persistence import metric_periods, persist_local, register_cell
from app.schemas import AnalysisTask, Site
from app.storage.raw import capture_scope
from tests.local_data_fixture import complete_versions


class LocalAdapterTests(unittest.TestCase):
    def test_versions_are_pinned_and_vacuum(self):
        with tempfile.TemporaryDirectory() as directory:
            db = LocalDataDB(Path(directory) / "market.sqlite3")
            first = db.stage(
                "stores",
                "20262",
                [{"row_key": "a", "payload": {"a": 1}, "latitude": 37.5, "longitude": 127.0}],
                "first",
            )
            db.activate(complete_versions(db, [first], "20262"))
            adapter = LocalAdapter(db.path)
            second = db.stage(
                "stores",
                "20263",
                [{"row_key": "b", "payload": {"a": 2}, "latitude": 37.5, "longitude": 127.0}],
                "second",
            )
            db.activate(complete_versions(db, [second], "20263"))
            self.assertIn(first, [version["version_id"] for version in adapter.versions])
            self.assertEqual(adapter.rows("stores")[0]["a"], 1)
            before, after = db.vacuum()
            self.assertLessEqual(after, before)

    def test_local_sql_no_clients_and_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            market = LocalDataDB(root / "market.sqlite3")
            site = Site(
                input_address="서울 테스트",
                road_address="서울 테스트",
                latitude=37.5,
                longitude=127.0,
            )
            x, y = to_epsg5181(site.latitude, site.longitude)
            store = dict.fromkeys(CSV_FIELDS.values(), "")
            store.update(
                {
                    "상가업소번호": "s1",
                    "상호명": "테스트",
                    "상권업종대분류코드": "I2",
                    "상권업종중분류코드": "I201",
                    "상권업종소분류코드": "I20101",
                    "시군구코드": "11680",
                    "위도": 37.5,
                    "경도": 127.0,
                }
            )
            area = {
                "TRDAR_CD": "a",
                "TRDAR_CD_NM": "테스트 상권",
                "XCNTS_VALU": x,
                "YDNTS_VALU": y,
                "RELM_AR": 40000,
                "bbox": [x - 100, y - 100, x + 100, y + 100],
                "rings": [
                    [
                        [x - 100, y - 100],
                        [x + 100, y - 100],
                        [x + 100, y + 100],
                        [x - 100, y + 100],
                        [x - 100, y - 100],
                    ]
                ],
            }
            fp = {
                "STDR_YYQU_CD": "20262",
                "TRDAR_CD": "a",
                "TOT_FLPOP_CO": 1000,
                "ML_FLPOP_CO": 500,
                "FML_FLPOP_CO": 500,
            }
            fp.update({f"TMZON_{band}_FLPOP_CO": 100 for band in TIME_BANDS})
            fp.update({key: 100 for key in (*_AGE_KEYS.values(), *_DAY_KEYS.values())})
            life = {
                "STDR_YYQU_CD": "20262",
                "TRDAR_CD": "a",
                "SVC_INDUTY_CD": "CS100001",
                "TRDAR_SE_CD": "A",
                "TRDAR_SE_CD_NM": "골목",
                "TRDAR_CD_NM": "테스트",
                "SVC_INDUTY_CD_NM": "한식",
                "SIMILR_INDUTY_STOR_CO": 20,
                "STOR_CO": 20,
                "FRC_STOR_CO": 0,
                "OPBIZ_RT": 0,
                "OPBIZ_STOR_CO": 0,
                "CLSBIZ_RT": 0,
                "CLSBIZ_STOR_CO": 0,
            }
            raw = {"stores": store, "areas": area, "floating": fp, "lifecycle": life}
            for source, kind in (("resident", "REPOP"), ("worker", "WRC_POPLTN")):
                row = dict.fromkeys(PopulationRecord.columns(kind), 100)
                row.update(STDR_YYQU_CD="20262", TRDAR_CD="a", TRDAR_CD_NM="테스트")
                raw[source] = row
            versions = []
            second_store = {**store, "상가업소번호": "s2", "상권업종중분류코드": "G204"}
            for source, row in raw.items():
                staged = [("s1" if source == "stores" else "a", row, "I201")]
                if source == "stores":
                    staged.append(("s2", second_store, "G204"))
                versions.append(
                    market.stage(
                        source,
                        "" if source == "areas" else "20262",
                        [
                            {
                                "row_key": key,
                                "payload": payload,
                                "area_code": "a",
                                "industry_code": industry,
                                "district_code": "11680",
                                "latitude": 37.5,
                                "longitude": 127.0,
                            }
                            for key, payload, industry in staged
                        ],
                        source,
                    )
                )
            market.activate(complete_versions(market, versions, "20262"))
            path = initialize(root / "requests.sqlite3")
            repository.create_request("test", site.input_address, db_path=path)
            task = AnalysisTask(request_id="test", site=site, radius_m=500)

            async def run():
                with (
                    patch("httpx.AsyncClient", side_effect=AssertionError("API 금지")),
                    patch(
                        "app.agents.commercial_area.client.StoreClient",
                        side_effect=AssertionError("점포 API 금지"),
                    ),
                    patch(
                        "app.agents.floating_population.client.SeoulOpenDataClient",
                        side_effect=AssertionError("서울 API 금지"),
                    ),
                ):
                    async with capture_scope("test", path) as scope:
                        adapter = LocalAdapter(market.path)
                        data, report, _ = persist_local(task, scope, adapter)
                        self.assertEqual(len(report["rows"]), 51)
                        self.assertIn("서울 밖 점포 미반영", data["limitations"])
                        store_version = next(
                            v["version_id"] for v in adapter.versions if v["source"] == "stores"
                        )
                        fact = register_cell(
                            scope,
                            "stores",
                            store_version,
                            "s1",
                            "상호명",
                            metric="place_name",
                            unit="텍스트",
                        )
                        from app.agentic.contracts import GetFactsInput
                        from app.agentic.read_tools import get_facts

                        reply = await get_facts(scope, GetFactsInput(fact_ids=[fact]))
                        self.assertEqual(reply.facts[0].spatial_scope["radius_m"], 500)
                        with connect(path) as con:
                            self.assertEqual(
                                con.execute("SELECT COUNT(*) FROM raw_rows").fetchone()[0], 51
                            )
                            self.assertEqual(
                                con.execute(
                                    "SELECT COUNT(*) FROM fact_sources JOIN facts USING(fact_id) "
                                    "WHERE source='industry_profile' "
                                    "AND metric='space_requirements'"
                                ).fetchone()[0],
                                51,
                            )
                            self.assertEqual(
                                con.execute(
                                    "SELECT COUNT(*) FROM fact_sources JOIN facts USING(fact_id) "
                                    "WHERE NOT (source='industry_profile' "
                                    "AND metric='space_requirements')"
                                ).fetchone()[0],
                                0,
                            )
                            row = con.execute(
                                "SELECT row_key,column_name FROM local_fact_lineage "
                                "WHERE fact_id=?",
                                (fact,),
                            ).fetchone()
                            self.assertEqual(tuple(row), ("s1", "상호명"))
                            self.assertLess(
                                con.execute("SELECT COUNT(*) FROM local_provenance").fetchone()[0],
                                10,
                            )
                            lifecycle_periods = {
                                metric: {
                                    period
                                    for (period,) in con.execute(
                                        "SELECT DISTINCT period FROM facts "
                                        "WHERE source='business_lifecycle' AND metric=?",
                                        (metric,),
                                    )
                                }
                                for metric in (
                                    "recent_year_close_rate",
                                    "oldest_year_close_rate",
                                    "avg_store_count",
                                    "turnover_rate",
                                )
                            }
                            self.assertEqual(
                                lifecycle_periods,
                                {
                                    "recent_year_close_rate": {"20253~20262"},
                                    "oldest_year_close_rate": {"20233~20242"},
                                    "avg_store_count": {"20233~20262"},
                                    "turnover_rate": {"20233~20262"},
                                },
                            )
                            floating = {
                                v["version_id"]
                                for v in adapter.versions
                                if v["source"] == "floating"
                            }
                            stores = {
                                v["version_id"] for v in adapter.versions if v["source"] == "stores"
                            }
                            c1 = {}
                            for code, unit, versions_json in con.execute(
                                "SELECT f.industry_code,f.unit,p.version_ids_json FROM facts f "
                                "JOIN local_fact_lineage l USING(fact_id) "
                                "JOIN local_provenance p USING(provenance_id) "
                                "WHERE f.metric='competition_index'"
                            ):
                                c1[code] = (unit, set(json.loads(versions_json)))
                            self.assertEqual(c1["M103"][0], "업종 집적 유형(프로필)")
                            self.assertFalse(c1["M103"][1] & floating)
                            self.assertFalse(c1["M103"][1] & stores)
                            self.assertIn("모임형", c1["I201"][0])
                            self.assertTrue(c1["I201"][1] & stores)
                            self.assertFalse(c1["I201"][1] & floating)
                            self.assertIn("근처형", c1["G204"][0])
                            self.assertTrue(c1["G204"][1] & stores)
                            self.assertTrue(c1["G204"][1] & floating)
                        await scope.finish()
                    from types import SimpleNamespace
                    from unittest.mock import AsyncMock

                    from app.services.analysis import execute_agentic_analysis

                    outcome = SimpleNamespace(
                        status="draft_available",
                        result=SimpleNamespace(
                            model_dump_json=lambda: '{"request_id":"local-service"}'
                        ),
                    )
                    loop = SimpleNamespace(
                        state={"limitations": []},
                        run=AsyncMock(return_value=outcome),
                        review_and_finalize=AsyncMock(return_value=outcome),
                        save=AsyncMock(),
                    )
                    with (
                        patch(
                            "app.services.analysis.DecisionLoop.create",
                            AsyncMock(return_value=loop),
                        ),
                        patch(
                            "app.services.analysis.collect_preflight",
                            AsyncMock(return_value=({}, None)),
                        ),
                    ):
                        received = await execute_agentic_analysis(
                            site.input_address,
                            resolve=AsyncMock(return_value=site),
                            db_path=path,
                            local_data_path=market.path,
                            request_id="local-service",
                        )
                    self.assertEqual(received.status, "draft_available")
                    self.assertIn("서울 밖 점포 미반영", loop.state["limitations"])
                    with connect(path) as con:
                        self.assertEqual(
                            con.execute(
                                "SELECT COUNT(*) FROM local_snapshots "
                                "JOIN snapshots USING(snapshot_id) "
                                "WHERE request_id='local-service'"
                            ).fetchone()[0],
                            1,
                        )

            asyncio.run(run())


class MetricPeriodTests(unittest.TestCase):
    def test_duplicate_quarters_do_not_shift_periods(self):
        quarters = ["20221", "20222", "20223", "20224", "20231", "20232", "20233", "20234"]
        found = metric_periods({"business_lifecycle": [*quarters, "20234", "20221"]})
        self.assertEqual(
            found["business_lifecycle"],
            {
                "recent_year_close_rate": "20231~20234",
                "close_rate_ratio": "20231~20234",
                "oldest_year_close_rate": "20221~20224",
            },
        )


if __name__ == "__main__":
    unittest.main()

"""로컬 SQL의 버전·공간 격리와 서울 경계 조건입니다."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from app.agents.agentic.sql_tool import query_raw
from app.db.connection import connect, initialize
from app.db.repository import create_request
from app.local_data.adapter import LocalAdapter
from app.local_data.boundary import boundary_limitations, fetch_boundary
from app.local_data.database import LocalDataDB
from app.local_data.provenance import save_snapshot
from app.schemas import AnalysisTask, Site
from app.storage.raw import capture_scope
from tests.local_data_fixture import complete_versions


class LocalReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_boundary_auth_matches_regulation(self):
        def respond(request):
            self.assertEqual(request.headers["Referer"], "http://localhost:8000")
            self.assertEqual(request.url.params["key"], "test-key")
            self.assertNotIn("domain", request.url.params)
            self.assertEqual(request.url.params["errorFormat"], "json")
            self.assertEqual(
                str(request.url.copy_with(query=None)), "https://api.vworld.kr/req/data"
            )
            return httpx.Response(
                200,
                json={
                    "response": {
                        "status": "OK",
                        "result": {
                            "featureCollection": {
                                "features": [
                                    {
                                        "properties": {"ctp_kor_nm": "서울특별시"},
                                        "geometry": {
                                            "type": "Polygon",
                                            "coordinates": [
                                                [
                                                    [126.9, 37.4],
                                                    [127.1, 37.4],
                                                    [127.1, 37.6],
                                                    [126.9, 37.4],
                                                ]
                                            ],
                                        },
                                    }
                                ]
                            }
                        },
                    }
                },
            )

        with patch.dict(
            "os.environ",
            {"VWORLD_API_KEY": " test-key ", "VWORLD_REFERER": " http://localhost:8000 "},
        ):
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
                rows = await fetch_boundary(http)
        self.assertEqual(rows[0]["row_key"], "11")

    async def test_bound_views_cells_limits_and_denials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            market = LocalDataDB(root / "market.sqlite3")
            versions = []
            for source in ("stores", "lifecycle", "floating", "resident", "worker"):
                versions.append(
                    market.stage(
                        source,
                        "20262",
                        [
                            {
                                "row_key": str(i),
                                "area_code": "a" if i < 60 else "b",
                                "latitude": 37.5 if i < 60 else 38.0,
                                "longitude": 127.0,
                                "district_code": "11680",
                                "industry_code": "I201",
                                "payload": {
                                    "SIMILR_INDUTY_STOR_CO": i,
                                    "TOT_FLPOP_CO": i,
                                    "STDR_YYQU_CD": "20262",
                                },
                            }
                            for i in range(61)
                        ],
                        source,
                    )
                )
            market.activate(complete_versions(market, versions, "20262"))
            path = initialize(root / "request.sqlite3")
            create_request("one", "시험", radius_m=500, db_path=path)
            site = Site(input_address="시험", road_address="시험", latitude=37.5, longitude=127.0)
            async with capture_scope("one", path) as scope:
                save_snapshot(
                    scope,
                    LocalAdapter(market.path),
                    AnalysisTask(request_id="one", site=site, radius_m=500),
                    data={
                        "selected_trade_area_codes": ["a"],
                        "area_selection": {"area_code": "a"},
                        "district_code": "11680",
                    },
                )
                direct = await query_raw(
                    scope,
                    "SELECT store_count FROM v_raw_lifecycle "
                    "WHERE store_count=5 AND quarter='20262'",
                )
                self.assertEqual(direct.status, "ok")
                self.assertEqual(len(direct.fact_ids), 1)
                with connect(path) as db:
                    lineage = db.execute(
                        "SELECT row_key,column_name FROM local_fact_lineage"
                    ).fetchone()
                    self.assertEqual(tuple(lineage), ("5", "SIMILR_INDUTY_STOR_CO"))
                for view in ("stores", "lifecycle", "floating", "resident", "worker"):
                    result = await query_raw(scope, f"SELECT count(*) AS n FROM v_raw_{view}")
                    self.assertEqual(result.status, "ok", (view, result.error))
                    quarters = 12 if view == "lifecycle" else 5 if view == "floating" else 1
                    self.assertEqual(result.data.rows[0].values["n"], 60 * quarters)
                    self.assertEqual(result.data.uncitable_columns, ["n"])
                limited = await query_raw(scope, "SELECT store_count FROM v_raw_lifecycle")
                self.assertTrue(limited.truncated)
                self.assertEqual(len(limited.data.rows), 50)
                district = await query_raw(
                    scope, "SELECT count FROM v_ref_district_counts WHERE industry_code='I201'"
                )
                self.assertEqual(district.data.rows[0].values["count"], 61)
                self.assertEqual(district.data.uncitable_columns, ["count"])
                for sql in (
                    "SELECT * FROM main.v_raw_lifecycle",
                    "SELECT * FROM local.stores",
                    "SELECT * FROM local.source_fields",
                    "SELECT * FROM sqlite_master",
                    "ATTACH ':memory:' AS x",
                    "PRAGMA table_info(stores)",
                    "DELETE FROM stores",
                    "SELECT 1; SELECT 2",
                    "WITH x AS (SELECT 1) SELECT * FROM x",
                    "SELECT scope_distance(37,127)",
                ):
                    denied = await query_raw(scope, sql)
                    self.assertEqual(denied.error.code, "SQL_DENIED", sql)
                cell = await query_raw(
                    scope,
                    "SELECT TOT_FLPOP_CO FROM v_raw_floating "
                    "WHERE TOT_FLPOP_CO=4 AND quarter='20262'",
                )
                self.assertEqual(len(cell.fact_ids), 1)
                self.assertEqual(cell.data.uncitable_columns, [])
                forged = await query_raw(
                    scope,
                    "SELECT store_count FROM v_raw_lifecycle WHERE 0 "
                    "UNION ALL SELECT 999 FROM v_raw_lifecycle WHERE store_count=5",
                )
                self.assertEqual(forged.data.rows[0].values["store_count"], 999)
                self.assertEqual(forged.fact_ids, [])
                self.assertEqual(forged.data.uncitable_columns, ["store_count"])
                foreign = await query_raw(
                    scope, "SELECT store_count FROM v_raw_lifecycle WHERE request_id='other'"
                )
                self.assertEqual(foreign.data.rows, [])
                with patch("app.agents.agentic.sql_tool.monotonic", side_effect=[0, 3]):
                    timeout = await query_raw(scope, "SELECT count(*) FROM v_raw_lifecycle")
                self.assertEqual(timeout.error.code, "SQL_TIMEOUT")

    def test_boundary_inside_crossing_missing(self):
        rows = [
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[126.9, 37.4], [127.1, 37.4], [127.1, 37.6], [126.9, 37.6], [126.9, 37.4]]
                    ],
                }
            }
        ]
        self.assertEqual(boundary_limitations(rows, 37.5, 127.0, 500), [])
        self.assertEqual(boundary_limitations(rows, 37.5, 127.099, 500), ["서울 밖 점포 미반영"])
        self.assertEqual(len(boundary_limitations([], 37.5, 127.0, 500)), 2)

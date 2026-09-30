"""유동인구 에이전트의 주거·직장인구 블록과 인구 총괄 시험."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.agents.decision import analyze as decide
from app.agents.decision.agent import DecisionContractError, _decision_input
from app.agents.floating_population import agent, population
from app.agents.floating_population.client import SeoulOpenApiError, SeoulOpenDataClient
from app.agents.floating_population.config import Settings
from app.agents.floating_population.interpret import TIME_LABELS, _peak
from app.agents.floating_population.models import (
    AGE_BANDS,
    DAYS,
    TIME_BANDS,
    FlpopRecord,
    PopulationRecord,
    TrdarArea,
)
from app.agents.floating_population.population import (
    RESIDENT_KIND,
    WORKER_KIND,
    load_snapshot,
    resident_block,
    summary_block,
    worker_block,
    write_snapshot,
)
from app.agents.floating_population.selection import SelectionUnavailable
from app.geo import to_epsg5181
from app.schemas import AnalysisTask, DecisionRequest, Site

QUARTER = "20262"
QUARTER_DAYS = 91  # 2026년 2분기


def _pop(
    code: str,
    total: float,
    *,
    households: float | None = None,
    quarter: str = QUARTER,
    ages: dict[str, float] | None = None,
) -> PopulationRecord:
    return PopulationRecord(
        trdar_cd=code,
        stdr_yyqu_cd=quarter,
        total=total,
        by_age=ages or {a: total / len(AGE_BANDS) for a in AGE_BANDS},
        households=households,
    )


def _flpop(code: str, daily: float) -> FlpopRecord:
    total = daily * QUARTER_DAYS
    return FlpopRecord(
        trdar_cd=code,
        stdr_yyqu_cd=QUARTER,
        total=total,
        male=total / 2,
        female=total / 2,
        by_time={b: total / len(TIME_BANDS) for b in TIME_BANDS},
        by_day={d: total / len(DAYS) for d in DAYS},
        by_age={a: total / len(AGE_BANDS) for a in AGE_BANDS},
    )


class PopulationRecordTests(unittest.TestCase):
    def test_resident_row_reads_repop_columns_and_households(self):
        row = {
            "STDR_YYQU_CD": "20262",
            "TRDAR_CD": "3110001",
            "TOT_REPOP_CO": 1269.0,
            "AGRDE_10_REPOP_CO": 43.0,
            "AGRDE_20_REPOP_CO": 299.0,
            "AGRDE_30_REPOP_CO": 377.0,
            "AGRDE_40_REPOP_CO": 133.0,
            "AGRDE_50_REPOP_CO": 130.0,
            "AGRDE_60_ABOVE_REPOP_CO": 287.0,
            "TOT_HSHLD_CO": 882.0,
            "APT_HSHLD_CO": 0.0,
        }
        record = PopulationRecord.from_api_row(row, RESIDENT_KIND)
        self.assertEqual(record.trdar_cd, "3110001")
        self.assertEqual(record.total, 1269.0)
        self.assertEqual(record.by_age["60"], 287.0)
        self.assertEqual(sum(record.by_age.values()), 1269.0)
        self.assertEqual(record.households, 882.0)

    def test_worker_row_reads_wrc_popltn_columns_without_households(self):
        row = {
            "STDR_YYQU_CD": "20262",
            "TRDAR_CD": "3110422",
            "TOT_WRC_POPLTN_CO": 55.0,
            "AGRDE_10_WRC_POPLTN_CO": 0.0,
            "AGRDE_20_WRC_POPLTN_CO": 3.0,
            "AGRDE_30_WRC_POPLTN_CO": 8.0,
            "AGRDE_40_WRC_POPLTN_CO": 17.0,
            "AGRDE_50_WRC_POPLTN_CO": 17.0,
            "AGRDE_60_ABOVE_WRC_POPLTN_CO": 10.0,
        }
        record = PopulationRecord.from_api_row(row, WORKER_KIND)
        self.assertEqual(record.total, 55.0)
        self.assertEqual(record.by_age["60"], 10.0)
        self.assertIsNone(record.households)


class ResidentWorkerBlockTests(unittest.TestCase):
    def setUp(self):
        young = {"10": 0.0, "20": 500.0, "30": 500.0, "40": 0.0, "50": 0.0, "60": 0.0}
        self.seoul = [
            # 반경 안: 1인가구 동네(가구당 1명), 20·30대만 산다
            _pop("A", 1000, households=1000, ages=young),
            # 반경 밖: 서울 나머지
            _pop("S", 3000, households=1000),
        ]

    def test_resident_block_aggregates_only_trade_areas_in_radius(self):
        block = resident_block(self.seoul, QUARTER, {"A", "M"})
        assert block is not None
        self.assertEqual(block.count, 1000)
        self.assertEqual(block.households, 1000)
        self.assertEqual(block.persons_per_household, 1.0)
        self.assertEqual(block.age_share["20"], 0.5)
        self.assertEqual(block.period, "2026년 2분기")
        # 시장 상권 M 은 주거인구가 없다
        self.assertEqual((block.covered_trade_areas, block.trade_area_count), (1, 2))

    def test_resident_benchmark_uses_seoul_rows_of_same_response(self):
        block = resident_block(self.seoul, QUARTER, {"A"})
        assert block is not None
        bench = block.benchmark
        # 서울 가구당 인원 4000/2000 = 2.0 → 1.0/2.0
        self.assertEqual(bench.persons_per_household_index, 0.5)
        # 서울 20대 비중 = (500 + 500) / 4000 = 0.25 → 0.5/0.25
        self.assertEqual(bench.age_index["20"], 2.0)
        self.assertEqual(bench.age_index["60"], 0.0)
        # 1000 이하인 서울 상권은 2곳 중 1곳
        self.assertEqual(bench.scale_percentile, 50)
        self.assertIn("2곳", bench.baseline)

    def test_worker_block_has_no_household_index(self):
        seoul = [_pop("A", 400), _pop("S", 100)]
        block = worker_block(seoul, QUARTER, {"A"})
        assert block is not None
        self.assertEqual(block.count, 400)
        self.assertIsNone(block.benchmark.persons_per_household_index)
        self.assertEqual(block.benchmark.scale_percentile, 100)

    def test_no_local_rows_returns_none(self):
        self.assertIsNone(resident_block(self.seoul, QUARTER, {"X"}))
        self.assertIsNone(worker_block(self.seoul, QUARTER, {"X"}))


class SummaryBlockTests(unittest.TestCase):
    def test_ratios_use_only_trade_areas_with_all_three_datasets(self):
        resident = [_pop("B", 1000), _pop("S", 3000)]
        worker = [_pop("A", 4000), _pop("B", 2000), _pop("S", 1000)]
        flpop = [_flpop("A", 9999), _flpop("B", 5000)]

        summary = summary_block(flpop, QUARTER_DAYS, resident, worker, {"A", "B"})

        # A 는 주거인구가 없어 비율에서 빠진다(직장인구 4,000 이 분자에 섞이면 안 된다)
        self.assertEqual(summary.basis_trade_areas, 1)
        self.assertEqual(summary.visitor_multiple, 5.0)
        self.assertEqual(summary.worker_to_resident_ratio, 2.0)
        # 서울 직장/주거 = (2000 + 1000) / (1000 + 3000) = 0.75 → 2.0 / 0.75
        self.assertEqual(summary.worker_to_resident_index, 2.667)
        self.assertEqual(summary.composition, "직장 중심")
        self.assertEqual(summary.seoul_worker_to_resident_ratio, 0.75)

    def composition(self, local_worker: float) -> str:
        resident = [_pop("A", 1000), _pop("S", 1000)]
        worker = [_pop("A", local_worker), _pop("S", 1000)]
        return summary_block([_flpop("A", 1)], QUARTER_DAYS, resident, worker, {"A"}).composition

    def test_composition_thresholds(self):
        # 서울 비 = (local + 1000) / 2000
        self.assertEqual(self.composition(3000), "직장 중심")  # 3.0 / 2.0 = 1.5
        self.assertEqual(self.composition(1000), "주거·직장 혼재")  # 1.0 / 1.0
        self.assertEqual(self.composition(500), "주거 중심")  # 0.5 / 0.75 = 0.667

    def test_no_common_trade_area_is_undecidable(self):
        summary = summary_block(
            [_flpop("A", 1)], QUARTER_DAYS, [_pop("B", 10)], [_pop("A", 10)], {"A"}
        )
        self.assertEqual(summary.basis_trade_areas, 0)
        self.assertIsNone(summary.visitor_multiple)
        self.assertIsNone(summary.worker_to_resident_ratio)
        self.assertEqual(summary.composition, "판단 불가")


class SnapshotTests(unittest.TestCase):
    def test_write_keeps_only_latest_quarter_and_needed_columns(self):
        rows = [
            {
                "STDR_YYQU_CD": "20261",
                "TRDAR_CD": "B",
                "TRDAR_CD_NM": "옛 분기",
                "TOT_REPOP_CO": 1.0,
                "TOT_HSHLD_CO": 1.0,
            },
            {
                "STDR_YYQU_CD": QUARTER,
                "TRDAR_CD": "B",
                "TRDAR_CD_NM": "골목",
                "TOT_REPOP_CO": 600.0,
                "AGRDE_60_ABOVE_REPOP_CO": 600.0,
                "TOT_HSHLD_CO": 300.0,
                "APT_HSHLD_CO": 0.0,
            },
            {"STDR_YYQU_CD": QUARTER, "TRDAR_CD": "A", "TRDAR_CD_NM": "시장", "TOT_REPOP_CO": 0.0},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resident.csv"
            quarter, count = write_snapshot(rows, RESIDENT_KIND, path)
            header = path.read_text(encoding="utf-8-sig").splitlines()[0].split(",")
            records = load_snapshot(RESIDENT_KIND, path)

        self.assertEqual((quarter, count), (QUARTER, 2))
        self.assertEqual(header, PopulationRecord.columns(RESIDENT_KIND))
        self.assertNotIn("APT_HSHLD_CO", header)
        self.assertEqual([r.trdar_cd for r in records], ["A", "B"])  # 상권코드 순
        self.assertEqual(records[1].total, 600.0)
        self.assertEqual(records[1].by_age["60"], 600.0)
        self.assertEqual(records[1].households, 300.0)

    def test_empty_rows_are_rejected(self):
        with self.assertRaises(ValueError):
            write_snapshot([], RESIDENT_KIND, Path("unused.csv"))

    def test_bundled_snapshot_is_read_once(self):
        population._bundled.cache_clear()
        self.addCleanup(population._bundled.cache_clear)
        with patch.object(population, "_read", wraps=population._read) as read:
            first = load_snapshot(RESIDENT_KIND)
            second = load_snapshot(RESIDENT_KIND)
        self.assertEqual(read.call_count, 1)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)  # 호출한 쪽이 목록을 바꿔도 캐시는 안전하다

    def test_bundled_snapshots_load(self):
        """동봉한 파일이 실제로 읽히고 한 분기 서울 전체를 담고 있는지."""
        for kind in (RESIDENT_KIND, WORKER_KIND):
            records = load_snapshot(kind)
            quarters = {r.stdr_yyqu_cd for r in records}
            self.assertEqual(len(quarters), 1, kind)
            self.assertGreater(len(records), 1000, kind)
            self.assertEqual(len({r.trdar_cd for r in records}), len(records), kind)


class FetchAllRowsTests(unittest.IsolatedAsyncioTestCase):
    """스냅샷 생성용 전량 수신. 에이전트는 이 경로를 쓰지 않는다."""

    def setUp(self):
        # 재시도 사이의 대기를 없앤다
        self.enterContext(patch("app.agents.floating_population.client.asyncio.sleep", AsyncMock()))

    def client(self, handler, **settings) -> SeoulOpenDataClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        from scripts.fetch_population_snapshot import SnapshotClient

        client = SnapshotClient(Settings(api_key="test-key", page_size=1000), http=http)
        for key, value in settings.items():
            setattr(client, key, value)
        return client

    @staticmethod
    def body(rows: list[dict], total: int) -> httpx.Response:
        payload = {"list_total_count": total, "RESULT": {"CODE": "INFO-000"}, "row": rows}
        return httpx.Response(200, json={"VwsmTrdarRepopQq": payload})

    async def test_pages_through_all_quarters_without_quarter_filter(self):
        total = 2500
        rows = [{"STDR_YYQU_CD": QUARTER, "TRDAR_CD": str(i)} for i in range(total)]
        seen: list[list[str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            parts = request.url.path.strip("/").split("/")
            seen.append(parts)
            start, end = int(parts[3]), int(parts[4])
            return self.body(rows[start - 1 : end], total)

        result = await self.client(handler).fetch_all_rows("VwsmTrdarRepopQq")

        self.assertEqual(len(result), total)
        self.assertEqual(sorted(int(p[3]) for p in seen), [1, 1001, 2001])
        # 분기 필터가 먹지 않는 서비스라 경로에 분기를 붙이지 않는다
        self.assertTrue(all(len(p) == 5 for p in seen))

    async def test_no_row_cap(self):
        total = 61_500  # 옛 상한 60,000행을 넘는다

        def handler(request: httpx.Request) -> httpx.Response:
            start = int(request.url.path.strip("/").split("/")[3])
            return self.body([{"TRDAR_CD": str(start)}], total)

        result = await self.client(handler).fetch_all_rows("VwsmTrdarRepopQq")

        self.assertEqual(len(result), 62)  # 1,000행씩 62페이지 모두 요청

    async def test_non_json_page_is_retried(self):
        calls: dict[int, int] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            start = int(request.url.path.strip("/").split("/")[3])
            calls[start] = calls.get(start, 0) + 1
            if start == 1001 and calls[start] == 1:  # 서버가 몰릴 때 주는 HTML 오류 응답
                return httpx.Response(200, text="<html>error</html>")
            return self.body([{"TRDAR_CD": str(start)}], 1500)

        result = await self.client(handler).fetch_all_rows("VwsmTrdarRepopQq")

        self.assertEqual(len(result), 2)
        self.assertEqual(calls[1001], 2)

    async def test_gives_up_after_retries(self):
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            body = {"RESULT": {"CODE": "ERROR-500", "MESSAGE": "서버 오류"}}
            return httpx.Response(200, json={"VwsmTrdarRepopQq": body})

        with self.assertRaises(SeoulOpenApiError):
            await self.client(handler, page_retries=2).fetch_all_rows("VwsmTrdarRepopQq")
        self.assertEqual(calls, 3)

    async def test_concurrency_is_limited(self):
        active = peak = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            active -= 1
            return self.body([{"TRDAR_CD": "x"}], 20_000)

        result = await self.client(handler, page_concurrency=3).fetch_all_rows("VwsmTrdarRepopQq")

        self.assertEqual(len(result), 20)
        self.assertLessEqual(peak, 3)


async def _no_selection(_payload: str) -> tuple[list[str], str]:
    raise SelectionUnavailable("시험에서는 선별하지 않는다")


class _AnalyzeFixture(unittest.IsolatedAsyncioTestCase):
    """가짜 클라이언트·스냅샷으로 analyze() 를 돌리는 공통 준비. 시험 메서드는 두지 않는다."""

    def setUp(self):
        self.site = Site(
            input_address="시험 주소",
            road_address="시험 도로 1",
            latitude=37.5,
            longitude=127.1,
        )
        x, y = to_epsg5181(self.site.latitude, self.site.longitude)
        self.areas = [
            TrdarArea(trdar_cd="A", trdar_cd_nm="시험 시장", x=x, y=y, relm_ar=5000),
            TrdarArea(trdar_cd="B", trdar_cd_nm="시험 골목", x=x + 50, y=y, relm_ar=5000),
        ]
        self.resident = [_pop("B", 1000, households=500), _pop("S", 3000, households=1500)]
        self.worker = [_pop("A", 4000), _pop("B", 2000), _pop("S", 1000)]

    def use_snapshots(self, resident=None, worker=None, error: Exception | None = None) -> None:
        """에이전트가 읽는 스냅샷을 바꿔 끼운다. `error` 면 파일 읽기가 실패한 것으로 본다."""

        def load(kind: str) -> list[PopulationRecord]:
            if error is not None:
                raise error
            return resident if kind == RESIDENT_KIND else worker

        self.enterContext(patch.object(agent, "load_snapshot", side_effect=load))

    def fake_client(self, series=None) -> SimpleNamespace:
        latest = [_flpop("A", 3000), _flpop("B", 5000)]
        return SimpleNamespace(
            fetch_trdar_areas=AsyncMock(return_value=self.areas),
            fetch_flpop_series=AsyncMock(return_value=series or [(QUARTER, latest)]),
            aclose=AsyncMock(),
        )

    async def run_analyze(self, client=None, radius_m: int = 500, select=_no_selection):
        task = AnalysisTask(request_id="population-test", site=self.site, radius_m=radius_m)
        return await agent.analyze(
            task,
            settings=Settings(api_key="test-key", trend_quarters=1),
            client=client or self.fake_client(),  # type: ignore[arg-type]
            select=select,
        )


class AnalyzeWithPopulationTests(_AnalyzeFixture):
    async def test_custom_selection_programming_error_is_not_hidden(self):
        self.use_snapshots(self.resident, self.worker)

        async def broken(_payload):
            raise TypeError("선별 구현 오류")

        with self.assertRaises(TypeError):
            await self.run_analyze(select=broken)

    async def test_default_selection_never_calls_model_and_keeps_raw_data(self):
        self.use_snapshots(self.resident, self.worker)
        with patch("app.llm.client.complete_json", side_effect=AssertionError("모델 호출 금지")):
            result = await self.run_analyze(select=None)
        selection = result.data["selection"]
        self.assertTrue(selection["applied"])
        self.assertNotIn("population_raw", selection["included"])
        self.assertIn("trade_areas", selection["included"])
        self.assertIn("radius_profile", selection["included"])
        self.assertNotIn("trend", selection["included"])
        self.assertTrue(result.data["population"]["by_age"])
        self.assertFalse(any("최종판단 입력에서만" in w for w in result.warnings))

    async def test_missing_selected_area_name_keeps_counts_and_reports_limitation(self):
        self.use_snapshots(self.resident, self.worker)
        self.areas[0].trdar_cd_nm = ""
        result = await self.run_analyze(select=None)
        self.assertEqual(result.data["population"]["daily_avg"], 8000)
        area = next(a for a in result.data["trade_areas"] if a["code"] == "A")
        self.assertIn("명칭 미제공", area["name"])
        self.assertTrue(any("상권명" in w for w in result.warnings))

    async def test_blocks_are_added_next_to_floating_population(self):
        self.use_snapshots(self.resident, self.worker)
        client = self.fake_client()

        result = await self.run_analyze(client)

        self.assertEqual(result.status, "ok")
        data = result.data
        self.assertEqual(data["population"]["daily_avg"], 8000)
        self.assertEqual(data["resident"]["count"], 1000)
        self.assertEqual(data["resident"]["persons_per_household"], 2.0)
        self.assertEqual(data["worker"]["count"], 6000)
        self.assertEqual(data["population_summary"]["basis_trade_areas"], 1)
        self.assertEqual(data["population_summary"]["composition"], "직장 중심")
        self.assertEqual(len(data["sources"]), 4)
        self.assertTrue(any("주거인구는 상권 2곳 중 1곳" in w for w in result.warnings))
        # 인구 블록은 선별 대상이 아니다
        self.assertNotIn("resident", data["selection"]["selectable"])
        # 주거·직장인구는 API 가 아니라 스냅샷에서 읽는다 — 클라이언트는 이 둘만 불린다
        client.fetch_trdar_areas.assert_awaited_once()
        client.fetch_flpop_series.assert_awaited_once()

    async def test_missing_snapshot_keeps_floating_population(self):
        self.use_snapshots(error=FileNotFoundError("resident.csv"))
        client = self.fake_client()

        result = await self.run_analyze(client)

        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.error)
        self.assertEqual(result.data["population"]["daily_avg"], 8000)
        self.assertIsNone(result.data["resident"])
        self.assertIsNone(result.data["worker"])
        self.assertIsNone(result.data["population_summary"])
        self.assertEqual(len(result.data["sources"]), 2)
        self.assertTrue(any("주거인구 자료 파일을 읽지 못해" in w for w in result.warnings))
        client.aclose.assert_not_awaited()  # 주입한 클라이언트는 호출한 쪽이 닫는다

    async def test_broken_snapshot_is_partial_not_crash(self):
        self.use_snapshots(error=KeyError("TRDAR_CD"))

        result = await self.run_analyze()

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data["population"]["daily_avg"], 8000)

    async def test_no_residents_in_radius_is_ok_not_partial(self):
        """반경 안이 시장·역뿐이라 주거인구가 원래 없는 것은 자료 누락이 아니다."""
        self.use_snapshots([_pop("S", 3000, households=1500)], self.worker)

        result = await self.run_analyze()

        self.assertEqual(result.status, "ok")
        self.assertIsNone(result.data["resident"])
        self.assertIsNotNone(result.data["worker"])
        self.assertTrue(any("주거인구 자료가 없습니다" in w for w in result.warnings))

    async def test_empty_snapshot_is_partial(self):
        self.use_snapshots([], self.worker)

        result = await self.run_analyze()

        self.assertEqual(result.status, "partial")
        self.assertTrue(any("주거인구 자료 파일을 읽지 못해" in w for w in result.warnings))

    async def test_code_bugs_are_not_hidden_as_missing_file(self):
        self.use_snapshots(error=RuntimeError("코드 버그"))

        with self.assertRaises(RuntimeError):
            await self.run_analyze()

    async def test_mismatched_snapshot_quarters_are_flagged(self):
        worker = [_pop("A", 4000, quarter="20254"), _pop("B", 2000, quarter="20254")]
        self.use_snapshots(self.resident, worker)

        result = await self.run_analyze()

        self.assertIsNotNone(result.data["population_summary"])
        self.assertTrue(any("분기가 달라" in w for w in result.warnings))

    async def test_older_population_quarter_is_used_with_warning(self):
        self.use_snapshots([_pop("B", 1000, households=500, quarter="20254")], self.worker)

        result = await self.run_analyze()

        self.assertEqual(result.data["resident"]["period"], "2025년 4분기")
        self.assertEqual(result.scope.period, "2026년 2분기")
        self.assertTrue(any("2025년 4분기 값을 썼습니다" in w for w in result.warnings))

    async def test_task_radius_drives_scope_and_radius_profile(self):
        self.use_snapshots(self.resident, self.worker)

        result = await self.run_analyze(radius_m=150)

        self.assertEqual(result.scope.area, "시험 주소 반경 150m")
        self.assertEqual(result.data["radius_m"], 150)
        points = result.data["radius_profile"]["points"]
        self.assertEqual([p["radius_m"] for p in points], [50, 100, 150])


def _resolve(data: dict, path: str):
    """결정 에이전트 `_validate_evidence` 와 같은 방식으로 JSON Pointer 를 따라간다."""
    value = data
    for part in path[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


class InterpretationTests(_AnalyzeFixture):
    async def test_every_finding_points_to_an_existing_value(self):
        self.use_snapshots(self.resident, self.worker)

        result = await self.run_analyze()
        findings = result.data["interpretation"]

        self.assertGreaterEqual(len(findings), 4)
        for finding in findings:
            self.assertIsNotNone(_resolve(result.data, finding["path"]), finding)
        paths = {f["path"] for f in findings}
        self.assertIn("/population_summary/worker_to_resident_index", paths)
        self.assertIn("/resident/benchmark/persons_per_household_index", paths)
        # 해석 문장이 먼저 읽히도록 description 바로 뒤에 온다
        self.assertEqual(list(result.data)[:2], ["description", "interpretation"])

    async def test_population_sentences_are_skipped_when_blocks_are_missing(self):
        self.use_snapshots(error=FileNotFoundError("resident.csv"))

        result = await self.run_analyze()
        findings = result.data["interpretation"]

        paths = {f["path"] for f in findings}
        self.assertFalse(any(p.startswith(("/resident", "/population_summary")) for p in paths))
        for finding in findings:
            self.assertIsNotNone(_resolve(result.data, finding["path"]), finding)

    async def test_trend_sentence_falls_back_to_previous_quarter(self):
        """기본 4개 분기에서는 전년 동기가 없다 — 직전 분기 대비로 문장을 만든다."""
        self.use_snapshots(self.resident, self.worker)
        series = [
            ("20261", [_flpop("A", 3000), _flpop("B", 4000)]),
            (QUARTER, [_flpop("A", 3000), _flpop("B", 5000)]),
        ]

        result = await self.run_analyze(self.fake_client(series))
        trend = next(f for f in result.data["interpretation"] if f["path"].startswith("/trend"))

        self.assertIsNone(result.data["trend"]["yoy_change"])
        self.assertEqual(trend["path"], "/trend/qoq_change")
        qoq = result.data["trend"]["qoq_change"]
        self.assertIn(f"직전 분기보다 {qoq:+.1%}", trend["text"])

    async def test_dropped_sentences_remain_in_source_but_not_decision_input(self):
        self.use_snapshots(self.resident, self.worker)
        series = [
            ("20261", [_flpop("A", 3000), _flpop("B", 4000)]),
            (QUARTER, [_flpop("A", 3000), _flpop("B", 5000)]),
        ]

        async def drop_trend(_payload: str) -> tuple[list[str], str]:
            return ["trade_areas", "population_raw", "radius_profile"], "추세는 판단에 불필요"

        result = await self.run_analyze(self.fake_client(series), select=drop_trend)
        paths = [f["path"] for f in result.data["interpretation"]]

        self.assertEqual(result.data["selection"]["dropped"], ["trend"])
        self.assertTrue(any(p.startswith("/trend") for p in paths))
        self.assertIn("/population_summary/worker_to_resident_index", paths)
        request = DecisionRequest(
            request_id=result.request_id, address="시험 주소", analyses=[result]
        )
        projected = json.loads(_decision_input(request))["analyses"][0]["data"]
        self.assertFalse(
            any(f and f["path"].startswith("/trend") for f in projected["interpretation"])
        )
        self.assertEqual(len(projected["interpretation"]), len(paths))
        self.assertTrue(any(f["path"].startswith("/trend") for f in result.data["interpretation"]))

    async def test_numbers_in_sentences_match_data(self):
        self.use_snapshots(self.resident, self.worker)

        result = await self.run_analyze()
        summary = result.data["population_summary"]
        sentence = next(
            f["text"]
            for f in result.data["interpretation"]
            if f["path"] == "/population_summary/worker_to_resident_index"
        )
        self.assertIn(f"{summary['worker_to_resident_ratio']:.2f}배", sentence)
        self.assertIn(summary["composition"], sentence)


class DecisionPopulationIntegrationTests(_AnalyzeFixture):
    """실제 인구 계산과 최종판단 검증 사이의 전달 계약을 확인합니다."""

    async def decide_from(self, analysis, paths):
        async def generate(_prompt, payload):
            self.decision_input = json.loads(payload)["analyses"][0]["data"]
            return {
                "status": "ok",
                "summary": "연결 시험용 판단",
                "recommendations": [
                    {
                        "category": {"major": "음식점업", "middle": "중식 음식점업"},
                        "score": 60,
                        "reasons": ["시험용 인구 자료를 참고했습니다."],
                        "evidence": [
                            {"agent_id": "floating_population", "path": path} for path in paths
                        ],
                        "risks": [],
                    }
                ],
                "not_recommended": [],
                "limitations": [],
            }

        return await decide(
            DecisionRequest(
                request_id=analysis.request_id,
                address=self.site.input_address,
                analyses=[analysis],
            ),
            generate=generate,
        )

    async def test_selected_input_preserves_population_blocks_and_evidence(self):
        self.use_snapshots(self.resident, self.worker)

        async def select(_payload):
            return [], "차트 원자료 제외"

        analysis = await self.run_analyze(radius_m=300, select=select)
        paths = [finding["path"] for finding in analysis.data["interpretation"]]
        paths.extend(["/resident/count", "/worker/count", "/population_summary/visitor_multiple"])
        result = await self.decide_from(analysis, paths)

        self.assertEqual(self.decision_input["radius_m"], 300)
        self.assertEqual(self.decision_input["population"]["daily_avg"], 8000)
        self.assertEqual(self.decision_input["resident"]["count"], 1000)
        self.assertEqual(self.decision_input["worker"]["count"], 6000)
        self.assertEqual(self.decision_input["population_summary"]["visitor_multiple"], 5)
        self.assertNotIn("trend", self.decision_input)
        self.assertIn("trend", result.source_analyses[0].data)
        for path in paths:
            self.assertEqual(_resolve(self.decision_input, path), _resolve(analysis.data, path))
        self.assertEqual(result.source_analyses[0], analysis)

    async def test_period_difference_is_preserved_in_input_and_limitations(self):
        self.use_snapshots(
            [_pop("B", 1000, households=500, quarter="20254")],
            self.worker,
        )
        analysis = await self.run_analyze()
        result = await self.decide_from(analysis, ["/worker/count"])

        self.assertEqual(self.decision_input["resident"]["period_code"], "20254")
        self.assertEqual(self.decision_input["worker"]["period_code"], "20262")
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("분기가 달라" in note for note in result.limitations))

    async def test_missing_resident_keeps_worker_and_rejects_null_evidence(self):
        self.use_snapshots([], self.worker)
        analysis = await self.run_analyze()
        result = await self.decide_from(analysis, ["/worker/count"])

        self.assertEqual(result.status, "partial")
        self.assertIsNone(self.decision_input["resident"])
        self.assertEqual(self.decision_input["worker"]["count"], 6000)
        self.assertTrue(any("주거인구 자료 파일" in note for note in result.limitations))
        with self.assertRaises(DecisionContractError) as caught:
            await self.decide_from(analysis, ["/resident"])
        self.assertEqual(caught.exception.diagnostics["reason"], "evidence_empty")


class PeakWordingTests(unittest.TestCase):
    def test_peak_above_threshold_is_called_out(self):
        finding = _peak({"11_14": 1.34, "17_21": 0.9}, TIME_LABELS, "시간당 통행 비중", "/b")
        self.assertEqual(finding.path, "/b/11_14")
        self.assertIn("점심(11~14시)", finding.text)
        self.assertIn("가장 두드러진다", finding.text)

    def test_flat_distribution_says_similar(self):
        finding = _peak({"11_14": 1.05, "17_21": 0.98}, TIME_LABELS, "시간당 통행 비중", "/b")
        self.assertIn("서울 평균과 비슷하다", finding.text)


if __name__ == "__main__":
    unittest.main()

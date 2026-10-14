"""유동인구 에이전트의 주거·직장인구 블록과 인구 총괄 시험."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app.agents.floating_population import population
from app.agents.floating_population.client import SeoulOpenApiError, SeoulOpenDataClient
from app.agents.floating_population.config import Settings
from app.agents.floating_population.models import (
    AGE_BANDS,
    DAYS,
    TIME_BANDS,
    FlpopRecord,
    PopulationRecord,
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


if __name__ == "__main__":
    unittest.main()

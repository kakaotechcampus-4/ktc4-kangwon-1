"""상권 경쟁 분석 에이전트가 팀 전달 규약을 지키는지 검사합니다."""

import tempfile
import unittest
from pathlib import Path

import httpx

from app.agents.commercial_area import analyze
from app.agents.commercial_area.client import SbizApiError, StoreClient
from app.agents.commercial_area.config import Settings
from app.agents.commercial_area.upjong import write_master
from app.agents.commercial_area.schemas import MiddleCode, Store
from app.schemas import AgentAnalysis, AnalysisTask

MASTER = [
    MiddleCode(code="I201", name="한식", major_code="I2", major_name="음식점업"),
    MiddleCode(code="I212", name="커피/음료", major_code="I2", major_name="음식점업"),
    MiddleCode(code="I202", name="중식", major_code="I2", major_name="음식점업"),
    MiddleCode(code="G204", name="편의점", major_code="G2", major_name="소매업"),
    MiddleCode(code="R102", name="이용/미용", major_code="R1", major_name="수리 및 개인 서비스업"),
]


def sample_stores(district_code=None, district_name=None):
    def make(code, name, major_code, major_name, label):
        return Store(
            store_id=f"{code}-{label}", name=label, branch_name=None,
            major_code=major_code, major_name=major_name,
            middle_code=code, middle_name=name, small_code=None, small_name=None,
            latitude=37.5006, longitude=127.0364, road_address=None,
            district_code=district_code, district_name=district_name,
        )

    stores = [make("I201", "한식", "I2", "음식점업", f"한식{i}") for i in range(6)]
    stores += [make("I212", "커피/음료", "I2", "음식점업", f"카페{i}") for i in range(3)]
    stores.append(make("G204", "편의점", "G2", "소매업", "편의점0"))
    return stores

NODATA_PAYLOAD = {"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"}}
AUTH_PAYLOAD = {"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}

SITE = {
    "input_address": "서울특별시 강남구 테헤란로 123, ○○빌딩 3층 302호",
    "road_address": "서울특별시 강남구 테헤란로 123",
    "detail_address": "○○빌딩 3층 302호",
    "latitude": 37.5006,
    "longitude": 127.0364,
}


class FakeClient(StoreClient):
    def __init__(self, settings, stores, baseline=None, baseline_error=None, district_error=None):
        super().__init__(settings, client=None)
        self._stores = stores
        self._baseline = baseline if baseline is not None else stores
        self._baseline_error = baseline_error
        self._district_error = district_error
        self.district_calls = 0

    def stores_in_district(self, signgu_cd):
        self.district_calls += 1
        if self._district_error:
            raise self._district_error
        return list(self._stores), {
            "signgu_cd": signgu_cd,
            "total_count": len(self._stores),
            "fetched": len(self._stores),
            "truncated": False,
            "reference_date": "20260331",
            "from_cache": False,
        }

    def stores_in_radius(self, lat, lon, radius_m, use_cache=True, grid_m=None):
        return list(self._stores), {
            "total_count": len(self._stores),
            "fetched": len(self._stores),
            "truncated": False,
            "radius_m": radius_m,
            "reference_date": "20260331",
            "from_cache": False,
        }

    def stores_in_radius_with_fallback(self, lat, lon, candidates, grid_m=None):
        if self._baseline_error:
            raise self._baseline_error
        return list(self._baseline), {
            "total_count": len(self._baseline),
            "fetched": len(self._baseline),
            "truncated": False,
            "radius_m": candidates[0],
            "reference_date": "20260331",
            "from_cache": False,
        }

    def close(self):
        return None


class AgentContractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        master_path = root / "upjong_codes.csv"
        write_master(master_path, MASTER)
        self.settings = Settings(
            cache_dir=root / "cache",
            upjong_master_path=master_path,
            sbiz_service_key="test-key",
        )
        self.task = AnalysisTask.model_validate({"request_id": "request-001", "site": SITE})

    def tearDown(self):
        self._tmp.cleanup()

    def test_result_matches_team_contract(self):
        result = analyze(self.task, settings=self.settings, store_client=FakeClient(self.settings, sample_stores()))
        AgentAnalysis.model_validate(result.model_dump())
        self.assertEqual(result.agent_id, "commercial_area")
        self.assertEqual(result.request_id, "request-001")
        self.assertTrue(result.scope.area.endswith("반경 500m"))
        self.assertTrue(result.scope.period)

    def test_accepts_plain_dict_task(self):
        result = analyze(
            {"request_id": "request-001", "site": SITE},
            settings=self.settings,
            store_client=FakeClient(self.settings, sample_stores()),
        )
        self.assertEqual(result.status, "partial")

    def test_no_data_when_no_stores(self):
        result = analyze(self.task, settings=self.settings, store_client=FakeClient(self.settings, []))
        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.data, {})
        self.assertIsNotNone(result.scope)

    def test_error_when_api_fails(self):
        class FailingClient(FakeClient):
            def stores_in_radius(self, *args, **kwargs):
                raise SbizApiError("UPSTREAM_TIMEOUT", "응답 시간 초과")

        result = analyze(self.task, settings=self.settings, store_client=FailingClient(self.settings, []))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "UPSTREAM_TIMEOUT")
        self.assertEqual(result.data, {})

    def test_partial_when_lq_baseline_fails(self):
        client = FakeClient(self.settings, sample_stores(), baseline_error=SbizApiError("NO_RADIUS", "반경 거부"))
        result = analyze(self.task, settings=self.settings, store_client=client)
        self.assertEqual(result.status, "partial")
        self.assertTrue(all(row["lq"] is None for row in result.data["by_middle"]))

    def test_all_master_categories_present(self):
        result = analyze(self.task, settings=self.settings, store_client=FakeClient(self.settings, sample_stores()))
        codes = {row["code"] for row in result.data["by_middle"]}
        self.assertEqual(codes, {m.code for m in MASTER})
        self.assertEqual(
            sum(row["count"] for row in result.data["by_middle"]), result.data["store_total"]
        )

    def test_district_baseline_is_used_when_code_present(self):
        stores = sample_stores(district_code="11710", district_name="송파구")
        client = FakeClient(self.settings, stores)
        result = analyze(self.task, settings=self.settings, store_client=client)

        self.assertEqual(client.district_calls, 1)
        self.assertEqual(result.data["district_baseline"]["signgu_code"], "11710")
        self.assertEqual(result.data["district_baseline"]["signgu_name"], "송파구")
        han = next(r for r in result.data["by_middle"] if r["code"] == "I201")
        self.assertIsNotNone(han["lq_district"])

    def test_district_step_skipped_without_code(self):
        client = FakeClient(self.settings, sample_stores())
        result = analyze(self.task, settings=self.settings, store_client=client)

        self.assertEqual(client.district_calls, 0)
        self.assertIsNone(result.data["district_baseline"])
        self.assertTrue(all(r["lq_district"] is None for r in result.data["by_middle"]))
        self.assertTrue(any("자치구 코드가 없어" in w for w in result.warnings))

    def test_district_failure_is_not_fatal(self):
        stores = sample_stores(district_code="11710", district_name="송파구")
        client = FakeClient(
            self.settings, stores, district_error=SbizApiError("UPSTREAM_FAILED", "타임아웃")
        )
        result = analyze(self.task, settings=self.settings, store_client=client)

        self.assertEqual(result.status, "partial")
        self.assertIsNone(result.data["district_baseline"])
        self.assertTrue(all(r["lq_district"] is None for r in result.data["by_middle"]))
        self.assertTrue(result.data["store_total"] > 0)

    def test_summary_absent_without_llm_settings(self):
        result = analyze(self.task, settings=self.settings, store_client=FakeClient(self.settings, sample_stores()))
        self.assertIsNone(result.data.get("summary"))
        self.assertTrue(any("ELICE" in w for w in result.warnings))


class ClientBehaviourTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(
            cache_dir=Path(self._tmp.name) / "cache", sbiz_service_key="test-key"
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _client(self, payload):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        return StoreClient(self.settings, client=httpx.Client(transport=transport))

    def test_nodata_returns_empty_instead_of_raising(self):
        stores, meta = self._client(NODATA_PAYLOAD).stores_in_radius(37.5, 127.0, 10)
        self.assertEqual(stores, [])
        self.assertEqual(meta["total_count"], 0)

    def test_agent_reports_no_data_for_empty_area(self):
        task = AnalysisTask.model_validate({"request_id": "request-002", "site": SITE})
        result = analyze(task, settings=self.settings, store_client=self._client(NODATA_PAYLOAD))
        self.assertEqual(result.status, "no_data")
        self.assertIsNone(result.error)

    def test_district_second_call_uses_cache(self):
        items = [
            {
                "bizesId": f"S{i}", "bizesNm": f"가게{i}",
                "indsLclsCd": "I2", "indsLclsNm": "음식점업",
                "indsMclsCd": "I201", "indsMclsNm": "한식 음식점업",
                "signguCd": "11710", "signguNm": "송파구",
                "lat": "37.5", "lon": "127.0",
            }
            for i in range(3)
        ]
        payload = {"header": {"resultCode": "00"}, "body": {"items": items, "totalCount": 3}}
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json=payload)

        client = StoreClient(self.settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
        first, _ = client.stores_in_district("11710")
        after_first = calls["n"]
        second, meta = client.stores_in_district("11710")

        self.assertEqual(len(first), 3)
        self.assertEqual(len(second), 3)
        self.assertEqual(calls["n"], after_first)
        self.assertTrue(meta["from_cache"])

    def test_agent_reports_error_on_auth_failure(self):
        task = AnalysisTask.model_validate({"request_id": "request-003", "site": SITE})
        result = analyze(task, settings=self.settings, store_client=self._client(AUTH_PAYLOAD))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "30")


if __name__ == "__main__":
    unittest.main()

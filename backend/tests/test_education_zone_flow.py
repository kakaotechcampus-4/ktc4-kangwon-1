"""보호구역 조회가 분석 흐름에 실리는 경로를 외부 호출 없이 검증합니다."""

import asyncio
import copy
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import education_zone as ez
from app.agents.decision.agent import _zone_limitations, evaluate
from app.agents.orchestration.graph import RunHooks
from app.agents.orchestration.nodes.analysis import prepare_address
from app.mocks import mock_site, zone_scan
from app.schemas import DecisionRequest

BACKEND = Path(__file__).resolve().parents[1]
EXAMPLES = BACKEND / "examples" / "decision"


def scan(*names, status="ok"):
    return ez.EducationZoneScan(
        status=status,
        center=ez.Coordinate(latitude=37.5, longitude=127.1),
        queried_at="2026-01-01T00:00:00+09:00",
        zones=[ez.EducationZone(name=name) for name in names],
        error=ez.ZoneError(code="X", message="실패") if status == "error" else None,
    )


class ZoneLimitationTests(unittest.TestCase):
    """코드가 직접 한계 문장을 넣습니다. 모델 문장에 기대지 않습니다."""

    def test_no_lookup_adds_nothing(self):
        self.assertEqual(_zone_limitations(None), [])

    def test_outside_any_zone_adds_nothing(self):
        self.assertEqual(_zone_limitations(scan()), [])

    def test_failure_is_not_read_as_safe(self):
        (text,) = _zone_limitations(scan(status="error"))
        self.assertIn("확인하지 못했", text)
        self.assertIn("보호구역이 아니라는 뜻이 아닙니다", text)

    def test_zone_names_are_quoted_as_received(self):
        (text,) = _zone_limitations(scan("절대보호구역"))
        self.assertIn("절대보호구역", text)
        self.assertIn("교육지원청", text)

    def test_overlapping_zones_are_listed_once_each(self):
        (text,) = _zone_limitations(scan("상대보호구역", "절대보호구역", "상대보호구역"))
        # 뒤 설명 문장에도 같은 낱말이 나오므로 나열 부분만 확인합니다.
        listed = text.split("에 속합니다")[0]
        self.assertEqual(listed.count("상대보호구역"), 1)
        self.assertIn("절대보호구역", listed)

    def test_unsplit_zone_name_is_kept(self):
        (text,) = _zone_limitations(scan("교육환경보호구역"))
        self.assertIn("교육환경보호구역", text)


class ScanSiteTests(unittest.IsolatedAsyncioTestCase):
    """보호구역 하나로 분석 전체를 멈추지 않습니다."""

    async def test_no_lookup_returns_none(self):
        self.assertIsNone(await ez.scan_site(mock_site(), None))

    async def test_exception_becomes_error_result(self):
        async def boom(site):
            raise RuntimeError("연결 실패")

        result = await ez.scan_site(mock_site(), boom)
        assert result is not None
        self.assertEqual(result.status, "error")
        assert result.error is not None
        self.assertEqual(result.error.code, "ZONE_FAILED")

    async def test_timeout_becomes_error_result(self):
        async def slow(site):
            await asyncio.sleep(10)

        result = await ez.scan_site(mock_site(), slow, timeout_s=0.01)
        assert result is not None
        assert result.error is not None
        self.assertEqual(result.error.code, "ZONE_TIMEOUT")

    async def test_config_error_does_not_escape(self):
        """인증키가 없어도 분석이 죽지 않고 실패 결과만 남습니다."""

        async def missing_key(site):
            raise ez.EducationZoneError("CONFIG_ERROR", "키 없음")

        result = await ez.scan_site(mock_site(), missing_key)
        assert result is not None
        self.assertEqual(result.status, "error")

    async def test_site_lookup_is_none_without_key(self):
        with patch.dict(os.environ, {"VWORLD_API_KEY": ""}, clear=False):
            os.environ.pop("VWORLD_API_KEY", None)
            self.assertIsNone(ez.site_lookup())
        self.assertIsNotNone(ez.site_lookup(ez.EducationZoneSettings(api_key="k")))


class PrepareAddressTests(unittest.IsolatedAsyncioTestCase):
    def deps(self, find_zones):
        site = mock_site()
        return site, SimpleNamespace(
            address=site.input_address,
            resolve=AsyncMock(return_value=site),
            radius_m=300,
            request_id="zone-node",
            step=AsyncMock(),
            find_zones=find_zones,
            hooks=RunHooks(),
        )

    async def test_lookup_result_is_carried_in_state(self):
        site, deps = self.deps(zone_scan)
        result = await prepare_address({}, deps=deps)
        self.assertEqual(result["education_zones"].zones[0].name, "상대보호구역")
        stages = [call.args[0] for call in deps.step.await_args_list]
        self.assertIn("education_zone", stages)

    async def test_lookup_receives_the_resolved_site(self):
        site, deps = self.deps(AsyncMock(return_value=zone_scan and scan()))
        await prepare_address({}, deps=deps)
        deps.find_zones.assert_awaited_once()
        self.assertEqual(deps.find_zones.await_args.args[0].latitude, site.latitude)

    async def test_failed_lookup_does_not_stop_the_analysis(self):
        async def boom(site):
            raise RuntimeError("연결 실패")

        _, deps = self.deps(boom)
        result = await prepare_address({}, deps=deps)
        self.assertIn("task", result)
        self.assertEqual(result["education_zones"].status, "error")


class DecisionInputTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request = DecisionRequest.model_validate_json(
            (EXAMPLES / "input.json").read_text(encoding="utf-8")
        )
        self.response = json.loads((EXAMPLES / "response.json").read_text(encoding="utf-8"))

    async def judge(self, zones):
        seen = {}

        async def generate(prompt, payload):
            seen.update(json.loads(payload))
            return copy.deepcopy(self.response)

        result = await evaluate(self.request, generate=generate, education_zones=zones)
        return result, seen

    async def test_zone_scan_reaches_the_model_input(self):
        result, payload = await self.judge(scan("상대보호구역"))
        self.assertEqual(payload["education_zones"]["zones"][0]["name"], "상대보호구역")
        self.assertTrue(any("상대보호구역" in note for note in result.limitations))

    async def test_absent_lookup_leaves_input_untouched(self):
        result, payload = await self.judge(None)
        self.assertNotIn("education_zones", payload)
        self.assertFalse(any("보호구역" in note for note in result.limitations))

    async def test_zone_limitation_downgrades_status_to_partial(self):
        """한계가 붙으면 기존 규칙대로 partial로 나갑니다."""
        result, _ = await self.judge(scan("절대보호구역"))
        self.assertEqual(result.status, "partial")

    async def test_failed_lookup_is_reported_as_unchecked(self):
        result, _ = await self.judge(scan(status="error"))
        self.assertTrue(any("확인하지 못했" in note for note in result.limitations))


if __name__ == "__main__":
    unittest.main()

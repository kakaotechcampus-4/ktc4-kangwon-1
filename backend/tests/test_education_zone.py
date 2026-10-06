"""교육환경보호구역 조회의 상태 구분과 재시도 정책을 외부 통신 없이 검증합니다."""

import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app import education_zone as ez

LAT, LNG = 37.4784, 126.9516

ABSOLUTE = {
    "type": "Feature",
    "properties": {
        "uname": "절대보호구역",
        "remark": "최종확인은 관악교육청에 반드시 확인요망",
        "dyear": "2008",
        "dnum": "0001",
        "sido_name": "서울특별시",
        "sigg_name": "관악구",
    },
    "geometry": {"type": "Polygon", "coordinates": [[[126.95, 37.47], [126.96, 37.48]]]},
}
RELATIVE = {
    "type": "Feature",
    "properties": {
        "uname": "상대보호구역",
        "remark": "",
        "dyear": "2011",
        "dnum": "0007",
        "sido_name": "서울특별시",
        "sigg_name": "관악구",
    },
}


def found(*features, total=None):
    return {
        "response": {
            "status": "OK",
            "record": {"total": str(total if total is not None else len(features))},
            "result": {
                "featureCollection": {"type": "FeatureCollection", "features": list(features)}
            },
        }
    }


NOT_FOUND = {"response": {"status": "NOT_FOUND"}}


def failure(code):
    return {"response": {"status": "ERROR", "error": {"level": "error", "code": code, "text": "x"}}}


class EducationZoneTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, **kwargs):
        return ez.EducationZoneSettings(
            **{"api_key": "fake-key", "retry_backoff_s": 0.01, **kwargs}
        )

    async def scan(self, handler, **kwargs):
        if not callable(handler):
            payload = handler
            handler = lambda request: httpx.Response(200, json=payload)  # noqa: E731
        settings = kwargs.pop("settings", None) or self.settings()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch.object(ez.asyncio, "sleep", new=AsyncMock()):
                return await ez.find_education_zones(
                    LAT, LNG, settings=settings, client=client, **kwargs
                )

    # ── 요청 ──

    async def test_point_uses_longitude_first_and_sends_layer(self):
        seen = {}

        def handler(request):
            seen.update(request.url.params)
            return httpx.Response(200, json=NOT_FOUND)

        await self.scan(handler, buffer_m=50)
        self.assertEqual(seen["data"], ez.EDUCATION_ZONE_LAYER)
        self.assertEqual(seen["geomFilter"], f"POINT({LNG} {LAT})")
        self.assertEqual(seen["buffer"], "50")
        self.assertEqual(seen["geometry"], "false")
        self.assertEqual(seen["crs"], "EPSG:4326")
        self.assertEqual(seen["request"], "GetFeature")

    async def test_geometry_is_requested_and_kept_only_when_asked(self):
        with_geom = await self.scan(found(ABSOLUTE), with_geometry=True)
        self.assertEqual(with_geom.zones[0].geometry, ABSOLUTE["geometry"])
        without = await self.scan(found(ABSOLUTE))
        self.assertIsNone(without.zones[0].geometry)

    async def test_referer_is_always_sent(self):
        """Referer가 없으면 V-World가 INCORRECT_KEY로 거절합니다(실측)."""
        seen = {}

        def handler(request):
            seen.clear()
            seen["referer"] = request.headers.get("Referer")
            seen.update(request.url.params)
            return httpx.Response(200, json=NOT_FOUND)

        await self.scan(handler)
        self.assertEqual(seen["referer"], ez.DEFAULT_REFERER)
        # 발급 때 등록한 URL이 있으면 그 값으로 덮어씁니다.
        await self.scan(handler, settings=self.settings(referer="https://example.test"))
        self.assertEqual(seen["referer"], "https://example.test")
        # 지금은 쿼리 파라미터로 보내지 않습니다. domain은 먹지 않았습니다.
        self.assertNotIn("domain", seen)

    async def test_blank_referer_is_rejected_by_settings(self):
        with self.assertRaises(ValueError):
            ez.EducationZoneSettings(api_key="k", referer="  ")

    # ── 상태 구분 ──

    async def test_zone_properties_are_preserved_as_written(self):
        scan = await self.scan(found(ABSOLUTE))
        self.assertEqual(scan.status, "ok")
        self.assertIsNone(scan.error)
        zone = scan.zones[0]
        # 교육청마다 표기가 달라 정규화하지 않고 그대로 둡니다.
        self.assertEqual(zone.name, "절대보호구역")
        self.assertEqual(zone.note, "최종확인은 관악교육청에 반드시 확인요망")
        self.assertEqual((zone.notice_year, zone.notice_no), ("2008", "0001"))
        self.assertEqual((zone.sido, zone.sigungu), ("서울특별시", "관악구"))

    async def test_overlapping_zones_are_all_collected(self):
        scan = await self.scan(found(ABSOLUTE, RELATIVE))
        self.assertEqual([z.name for z in scan.zones], ["절대보호구역", "상대보호구역"])

    async def test_unsplit_zone_name_is_kept(self):
        """교육청에 따라 절대·상대 구분 없이 '교육환경보호구역'으로만 올라옵니다."""
        plain = {"type": "Feature", "properties": {"uname": "교육환경보호구역", "remark": ""}}
        scan = await self.scan(found(plain))
        self.assertEqual(scan.zones[0].name, "교육환경보호구역")
        self.assertIsNone(scan.zones[0].note)

    async def test_not_found_is_ok_with_empty_zones(self):
        scan = await self.scan(NOT_FOUND)
        self.assertEqual(scan.status, "ok")
        self.assertEqual(scan.zones, [])
        self.assertIsNone(scan.error)

    async def test_upstream_failure_is_error_not_empty_result(self):
        """조회 실패를 '보호구역 없음'으로 읽으면 안 됩니다."""
        scan = await self.scan(failure("SYSTEM_ERROR"))
        self.assertEqual(scan.status, "error")
        self.assertEqual(scan.zones, [])
        assert scan.error is not None
        self.assertEqual(scan.error.code, "SYSTEM_ERROR")

    async def test_connection_error_is_error(self):
        def handler(request):
            raise httpx.ConnectError("boom")

        scan = await self.scan(handler)
        self.assertEqual(scan.status, "error")
        assert scan.error is not None
        self.assertEqual(scan.error.code, "UPSTREAM_FAILED")

    async def test_timeout_is_error(self):
        def handler(request):
            raise httpx.ReadTimeout("slow")

        scan = await self.scan(handler)
        assert scan.error is not None
        self.assertEqual(scan.error.code, "UPSTREAM_TIMEOUT")

    async def test_missing_zone_name_is_dropped_with_warning(self):
        nameless = {"type": "Feature", "properties": {"remark": "어느 학교"}}
        scan = await self.scan(found(ABSOLUTE, nameless))
        self.assertEqual(len(scan.zones), 1)
        self.assertTrue(scan.warnings)

    async def test_truncated_page_is_warned(self):
        scan = await self.scan(found(ABSOLUTE, total=3))
        self.assertTrue(any("3건" in w for w in scan.warnings))

    # ── 재시도 ──

    async def test_fatal_error_is_not_retried(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=failure("INVALID_KEY"))

        scan = await self.scan(handler)
        self.assertEqual(len(calls), 1)
        assert scan.error is not None
        self.assertEqual(scan.error.code, "INVALID_KEY")

    async def test_quota_exhaustion_is_not_retried(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=failure("OVER_REQUEST_LIMIT"))

        await self.scan(handler)
        self.assertEqual(len(calls), 1)

    async def test_system_error_is_retried_then_succeeds(self):
        calls = []

        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(200, json=failure("SYSTEM_ERROR"))
            return httpx.Response(200, json=found(ABSOLUTE))

        scan = await self.scan(handler)
        self.assertEqual(len(calls), 2)
        self.assertEqual(scan.status, "ok")
        self.assertEqual(len(scan.zones), 1)

    async def test_server_error_is_retried_up_to_limit(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(503)

        scan = await self.scan(handler, settings=self.settings(max_retries=2, retry_backoff_s=0.01))
        self.assertEqual(len(calls), 3)
        self.assertEqual(scan.status, "error")

    async def test_client_error_stops_immediately(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(400)

        scan = await self.scan(handler)
        self.assertEqual(len(calls), 1)
        self.assertEqual(scan.status, "error")

    # ── 입력 검증 ──

    async def test_missing_key_raises_config_error(self):
        with self.assertRaises(ez.EducationZoneError) as caught:
            await ez.find_education_zones(LAT, LNG, settings=ez.EducationZoneSettings())
        self.assertEqual(caught.exception.code, "CONFIG_ERROR")

    async def test_invalid_coordinate_and_buffer_raise(self):
        for kwargs, code in (
            ({"latitude": 91.0}, "INVALID_COORDINATE"),
            ({"longitude": 181.0}, "INVALID_COORDINATE"),
            ({"buffer_m": -1}, "INVALID_BUFFER"),
            ({"buffer_m": ez.MAX_BUFFER_M + 1}, "INVALID_BUFFER"),
        ):
            with self.subTest(**kwargs):
                args = {"latitude": LAT, "longitude": LNG, **kwargs}
                with self.assertRaises(ez.EducationZoneError) as caught:
                    await ez.find_education_zones(
                        args["latitude"],
                        args["longitude"],
                        buffer_m=args.get("buffer_m", 0),
                        settings=self.settings(),
                    )
                self.assertEqual(caught.exception.code, code)

    async def test_unknown_payload_shape_raises(self):
        for payload in (
            {"nope": 1},
            {"response": {"status": "WAT"}},
            {"response": {"status": "OK"}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(ez.EducationZoneError) as caught:
                    await self.scan(payload)
                self.assertEqual(caught.exception.code, "BAD_RESPONSE")

    async def test_secrets_never_appear_in_errors(self):
        secret = "super-secret-key"

        def handler(request):
            return httpx.Response(200, json=failure("INVALID_KEY"))

        scan = await self.scan(handler, settings=self.settings(api_key=secret))
        assert scan.error is not None
        self.assertNotIn(secret, scan.error.message)
        with self.assertRaises(ez.EducationZoneError) as caught:
            await self.scan({"nope": 1}, settings=self.settings(api_key=secret))
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn("vworld", str(caught.exception).lower())


if __name__ == "__main__":
    unittest.main()

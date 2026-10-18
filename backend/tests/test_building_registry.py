"""건축물대장 조회의 응답 해석과 부분 실패를 외부 통신 없이 검증합니다."""

import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app import main
from app.address import GeocodeError
from app.building_registry import (
    BuildingRegistryError,
    BuildingRegistrySettings,
    lookup_building,
)
from app.config import AddressSettings
from app.services.settings import ExecutionSettings

KAKAO = {
    "meta": {"total_count": 1, "pageable_count": 1, "is_end": True},
    "documents": [
        {
            "address": {
                "address_name": "서울 송파구 장지동 893",
                "b_code": "1171011400",
                "mountain_yn": "N",
                "main_address_no": "893",
                "sub_address_no": "",
            },
            "road_address": {"address_name": "서울 송파구 위례광장로 199"},
            "x": "127.1428",
            "y": "37.4816",
        }
    ],
}
TITLE = {
    "bldNm": "성희프라자",
    "dongNm": " ",
    "mainPurpsCdNm": "제2종근린생활시설",
    "grndFlrCnt": 7,
    "ugrndFlrCnt": 4,
    "totArea": 12301.78,
    # 건축HUB는 숫자도 문자열로 줍니다. 빈 칸은 더하지 않습니다.
    "indrAutoUtcnt": "30",
    "oudrAutoUtcnt": "2",
    "indrMechUtcnt": "",
    "oudrMechUtcnt": "0",
}
# 실호출 형태: 층별개요·호실은 주용도코드명이 세부 용도, 기타용도가 분류나 설명입니다.
FLOORS = [
    {"flrNoNm": "4층", "mainPurpsCdNm": "일반음식점", "etcPurps": "제2종근린생활시설", "area": 900},
    {
        "flrNoNm": "지1층",
        "mainPurpsCdNm": "기타제2종근린생활시설",
        "etcPurps": "지하주차장",
        "area": "1500.5",
    },
]
UNITS = [
    {
        "hoNm": "401호",
        "flrNoNm": "4층",
        "exposPubuseGbCdNm": "전유",
        "mainPurpsCdNm": "학원",
        "area": 200.0,
    },
    {"hoNm": "401호", "flrNoNm": "4층", "exposPubuseGbCdNm": "전유", "area": 75.49},
    {"hoNm": "401호", "flrNoNm": "4층", "exposPubuseGbCdNm": "공용", "area": 120.0},
    {"hoNm": "B101호", "flrNoNm": "지1층", "exposPubuseGbCdNm": "전유", "area": 50.0},
]
SEWAGE = {"modeCdNm": "하수종말처리장연결"}


def hub(items, total=None):
    if total is None:
        total = 1 if isinstance(items, dict) else len(items or [])
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {"items": {"item": items} if items else "", "totalCount": total},
        }
    }


def answers(**overrides):
    """오퍼레이션 이름별 응답입니다. 기본은 네 항목 모두 정상입니다."""
    return {
        "getBrTitleInfo": httpx.Response(200, json=hub(TITLE)),  # 한 건이면 객체
        "getBrFlrOulnInfo": httpx.Response(200, json=hub(FLOORS)),
        "getBrExposPubuseAreaInfo": httpx.Response(200, json=hub(UNITS)),
        "getBrWclfInfo": httpx.Response(200, json=hub(SEWAGE)),
        **overrides,
    }


def transport(responses):
    """값이 함수면 요청을 받아 응답을 만듭니다. 같은 응답을 여러 번 써도 되게 복사합니다."""
    seen = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "dapi.kakao.com":
            return httpx.Response(200, json=KAKAO)
        answer = responses[request.url.path.rsplit("/", 1)[-1]]
        answer = answer(request) if callable(answer) else answer
        return httpx.Response(answer.status_code, content=answer.content, headers=answer.headers)

    return httpx.MockTransport(handle), seen


def sequence(*responses):
    """부를 때마다 다음 응답을 돌려줍니다. 마지막 응답은 계속 씁니다."""
    queue = list(responses)
    return lambda request: queue.pop(0) if len(queue) > 1 else queue[0]


class BuildingRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def lookup(self, responses):
        mock, seen = transport(responses)
        async with httpx.AsyncClient(transport=mock) as client:
            result = await lookup_building(
                "서울 송파구 위례광장로 199 4층",
                BuildingRegistrySettings(api_key="fake", retry_delay=0),
                AddressSettings(api_key="fake"),
                client=client,
            )
        return result, seen

    async def test_parses_all_sections(self):
        result, seen = await self.lookup(answers())
        hub_params = seen[1].url.params
        self.assertEqual(
            (hub_params["sigunguCd"], hub_params["bjdongCd"], hub_params["platGbCd"]),
            ("11710", "11400", "0"),
        )
        self.assertEqual((hub_params["bun"], hub_params["ji"]), ("0893", "0000"))
        self.assertEqual(result.road_address, "서울 송파구 위례광장로 199")
        title = result.titles[0]
        self.assertEqual((title.building_name, title.dong_name), ("성희프라자", None))
        self.assertEqual((title.ground_floors, title.underground_floors), (7, 4))
        self.assertEqual((title.total_area_m2, title.parking_spaces), (12301.78, 32))
        # 지하층은 화면 표기로 바꿉니다.
        self.assertEqual(
            [(f.floor, f.use, f.use_detail, f.area_m2) for f in result.floors],
            [
                ("4층", "일반음식점", "제2종근린생활시설", 900.0),
                ("지하 1층", "기타제2종근린생활시설", "지하주차장", 1500.5),
            ],
        )
        # 공용 행은 빼고 같은 호수의 전유 행은 더합니다.
        self.assertEqual(
            [(u.unit_name, u.floor, u.use, u.area_m2) for u in result.units],
            [("401호", "4층", "학원", 275.49), ("B101호", "지하 1층", None, 50.0)],
        )
        self.assertEqual(
            [(s.method, s.method_name) for s in result.sewage],
            [("하수종말처리장 연결", "하수종말처리장연결")],
        )

    async def test_sewage_and_parking_follow_screen(self):
        rows = [
            {"modeCdNm": "부패탱크방법"},
            {"modeCdNm": "오수처리시설"},
            {"modeCdNm": "접촉폭기방법", "etcMode": "접촉폭기식"},
            # 형식코드명이 비면 기타형식 원문을 씁니다.
            {"modeCdNm": " ", "etcMode": "하수종말처리장 연결"},
            # 둘 다 빈 행은 정보가 없어 뺍니다.
            {"modeCdNm": " ", "etcMode": " "},
        ]
        result, _ = await self.lookup(
            answers(
                getBrTitleInfo=httpx.Response(200, json=hub({"bldNm": "주차 기록 없음"})),
                getBrWclfInfo=httpx.Response(200, json=hub(rows)),
            )
        )
        self.assertIsNone(result.titles[0].parking_spaces)
        # 처리 방식 이름만으로는 선택지를 못 정하므로 원문만 남기고 사용자가 고르게 둡니다.
        self.assertEqual(
            [(s.method, s.method_name) for s in result.sewage],
            [
                ("정화조", "부패탱크방법"),
                ("오수처리시설", "오수처리시설"),
                (None, "접촉폭기방법"),
                ("하수종말처리장 연결", "하수종말처리장 연결"),
            ],
        )

    async def test_main_building_first(self):
        # 한 지번에 작은 단독주택과 상가 건물이 같이 등록된 경우입니다.
        rows = [
            {"bldNm": " ", "mainPurpsCdNm": "단독주택", "totArea": 38.55},
            {
                "dongNm": "대일빌딩",
                "bldNm": "대일빌딩",
                "mainPurpsCdNm": "업무시설",
                "totArea": 23198.83,
            },
        ]
        result, _ = await self.lookup(answers(getBrTitleInfo=httpx.Response(200, json=hub(rows))))
        self.assertEqual(
            [(t.building_name, t.main_use) for t in result.titles],
            [("대일빌딩", "업무시설"), (None, "단독주택")],
        )

    async def test_reads_every_page(self):
        def paged(request):
            page = int(request.url.params["pageNo"])
            return httpx.Response(200, json=hub([{"flrNoNm": f"{page}층"}], total=2))

        result, _ = await self.lookup(answers(getBrFlrOulnInfo=paged))
        self.assertEqual([f.floor for f in result.floors], ["1층", "2층"])

    async def test_no_rows_is_empty_list(self):
        nodata = {"response": {"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"}}}
        result, _ = await self.lookup(
            answers(
                getBrExposPubuseAreaInfo=httpx.Response(200, json=hub(None)),
                getBrWclfInfo=httpx.Response(200, json=nodata),
            )
        )
        self.assertEqual((result.units, result.sewage), ([], []))

    async def test_failed_section_is_null(self):
        result, _ = await self.lookup(
            answers(
                getBrFlrOulnInfo=httpx.Response(500),
                # 미등록 키는 _type=json이어도 XML로 옵니다.
                getBrExposPubuseAreaInfo=httpx.Response(200, text="<OpenAPI_ServiceResponse/>"),
            )
        )
        self.assertEqual((len(result.titles), len(result.sewage)), (1, 1))
        self.assertIsNone(result.floors)
        self.assertIsNone(result.units)

    async def test_retries_gateway_hiccups(self):
        # 실호출에서 본 일시 오류입니다. 다시 요청하면 정상 응답이 옵니다.
        result, _ = await self.lookup(
            answers(
                getBrFlrOulnInfo=sequence(
                    httpx.Response(503, text="SERVICETIMEOUT_ERROR"),
                    httpx.Response(200, json=hub(FLOORS)),
                ),
                getBrExposPubuseAreaInfo=sequence(
                    httpx.Response(200, text=""), httpx.Response(200, json=hub(UNITS))
                ),
            )
        )
        self.assertEqual((len(result.floors), len(result.units)), (2, 2))

    async def test_gives_up_after_retries(self):
        result, seen = await self.lookup(
            answers(
                getBrFlrOulnInfo=httpx.Response(503),
                # 인증 오류는 다시 요청해도 같으므로 한 번만 부릅니다.
                getBrWclfInfo=httpx.Response(401),
            )
        )
        self.assertEqual((result.floors, result.sewage), (None, None))
        calls = Counter(request.url.path.rsplit("/", 1)[-1] for request in seen)
        self.assertEqual((calls["getBrFlrOulnInfo"], calls["getBrWclfInfo"]), (3, 1))

    async def test_all_sections_failed_raises(self):
        error = httpx.Response(200, json={"response": {"header": {"resultCode": "30"}}})
        with self.assertRaises(BuildingRegistryError) as caught:
            await self.lookup({name: error for name in answers()})
        self.assertEqual(caught.exception.code, "UPSTREAM_ERROR")

    async def test_missing_key_stops_before_calls(self):
        with self.assertRaises(BuildingRegistryError) as caught:
            await lookup_building("서울 송파구 위례광장로 199", BuildingRegistrySettings())
        self.assertEqual(caught.exception.code, "CONFIG_ERROR")


class BuildingRegistryApiTests(unittest.TestCase):
    def get(self, error=None, **params):
        target = "app.api.v1.building.lookup_building"
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.dict(os.environ, {"MOCK_MODE": ""}),
            patch(target, new=AsyncMock(side_effect=error)),
            TestClient(
                main.create_app(
                    settings=ExecutionSettings(db_path=Path(folder) / "test.sqlite3"),
                    load_env=False,
                )
            ) as client,
        ):
            return client.get(
                "/api/v1/building-registry", params={"address": "서울 어딘가", **params}
            )

    def test_bad_address_is_400(self):
        response = self.get(GeocodeError("NOT_FOUND", "x"))
        self.assertEqual(response.status_code, 400)

    def test_registry_failure_is_502(self):
        response = self.get(BuildingRegistryError("AUTH", "x"))
        self.assertEqual(response.status_code, 502)

    def test_mock_needs_no_lookup(self):
        response = self.get(AssertionError("외부 조회 금지"), mock="true")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["titles"][0]["building_name"], "성희프라자")
        self.assertEqual({f["floor"] for f in body["floors"]}, {"지하 1층", "4층"})
        self.assertEqual(body["sewage"][0]["method"], "하수종말처리장 연결")

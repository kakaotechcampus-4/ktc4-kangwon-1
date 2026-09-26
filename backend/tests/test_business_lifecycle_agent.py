"""Business Lifecycle 에이전트의 공통 인터페이스 연결을 검사합니다."""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

from app.agents.business_lifecycle.agent import (
    AGENT_ID,
    analyze,
)
from app.agents.business_lifecycle.area_resolver import (
    BusinessArea,
    BusinessAreaNoDataError,
    BusinessAreaResolverError,
)
from app.agents.business_lifecycle.config import Settings
from app.agents.business_lifecycle.llm import BusinessLifecycleAgentError
from app.industries.catalog import INDUSTRIES
from app.schemas import AgentAnalysis, AnalysisTask, Site

GARAK_SITE = Site(
    input_address="서울특별시 송파구 가락동 167",
    jibun_address="서울특별시 송파구 가락동 167",
    latitude=37.498,
    longitude=127.135,
)


def task() -> AnalysisTask:
    return AnalysisTask(
        request_id="request-business-lifecycle",
        site=GARAK_SITE,
    )


def fake_area(site: Site, settings: Settings) -> BusinessArea:
    return BusinessArea(
        area_code="3120240",
        area_name="개롱역",
        area_type_code="A",
        area_type_name="골목상권",
        district_code="11710",
        district_name="송파구",
        dong_code="11710631",
        dong_name="가락동",
        x=0,
        y=0,
        distance_m=91.2,
    )


def fake_pipeline(
    area_code: str,
    base_quarter: str,
    quarter_count: int,
    request_id: str | None,
    area_name: str | None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "agent_id": AGENT_ID,
        "scope": {
            "area_code": area_code,
            "area_name": area_name,
            "base_quarter": base_quarter,
            "period": {
                "start_quarter": "20221",
                "end_quarter": base_quarter,
                "quarter_count": quarter_count,
            },
        },
        "coverage": {
            "target_industries": 75,
            "scored_industries": 1,
            "unscored_industries": 74,
        },
        "scoring_method": {
            "score_type": "relative",
            "description": "테스트용 점수입니다.",
        },
        "summary": "테스트 요약입니다.",
        "industry_scores": [
            {
                "industry_id": "I201",
                "industry_name": "한식 음식점업",
                "lifecycle_score": 71.5,
                "type": "성장·안정형",
                "confidence": "high",
                "evidence": ["최근 1년 폐업률은 1.2%입니다."],
                "warning": None,
            }
        ],
        "unavailable_industries": [
            {
                "industry_id": industry_id,
                "industry_name": INDUSTRIES[industry_id],
                "data_available": False,
                "confidence": "none",
                "observed_quarters": 7 if industry_id == "I202" else 0,
                "missing_reason": "테스트용 데이터 부족입니다.",
            }
            for industry_id in INDUSTRIES
            if industry_id != "I201"
        ],
    }


class BusinessLifecycleAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_radius_is_recorded_but_does_not_change_polygon(self):
        results = []
        for radius in (300, 700):
            result = await analyze(
                task().model_copy(update={"radius_m": radius}),
                settings=Settings(base_quarter_override="20244"),
                area_resolver=fake_area,
                run_pipeline=fake_pipeline,
            )
            self.assertEqual(result.data["metadata"]["requested_radius_m"], radius)
            self.assertIs(result.data["metadata"]["radius_applied"], False)
            results.append(result)
        self.assertEqual(results[0].scope, results[1].scope)
        self.assertEqual(results[0].data["industries"], results[1].data["industries"])

    async def test_bundled_area_reaches_pipeline_without_external_calls(self):
        site = GARAK_SITE.model_copy(
            update={
                "latitude": 37.4975927810188,
                "longitude": 127.135121781578,
            }
        )
        with patch("socket.socket.connect", side_effect=AssertionError("외부 호출 금지")):
            result = await analyze(
                AnalysisTask(request_id="bundled-area", site=site),
                settings=Settings(base_quarter_override="20244"),
                run_pipeline=fake_pipeline,
            )
        self.assertIsNone(result.error)
        self.assertEqual(result.data["metadata"]["area_code"], "3120240")
        self.assertEqual(result.data["metadata"]["area_name"], "개롱역")
        self.assertEqual(result.data["metadata"]["area_resolver"]["method"], "official_polygon")

    async def test_analyze_preserves_request_id_and_validates_agent_analysis(self):
        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="20244"),
            area_resolver=fake_area,
            run_pipeline=fake_pipeline,
        )

        AgentAnalysis.model_validate(result.model_dump())
        self.assertEqual(result.request_id, "request-business-lifecycle")
        self.assertEqual(result.agent_id, "business_lifecycle")
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.scope.area, "개롱역 (3120240)")
        self.assertEqual(result.scope.period, "20221~20244 (12개 분기)")
        self.assertEqual(result.data["metadata"]["area_code"], "3120240")
        self.assertEqual(len(result.data["industries"]), 75)
        unavailable = next(
            industry for industry in result.data["industries"] if industry["industry_id"] == "I202"
        )
        self.assertEqual(unavailable["source_coverage"].get("observed_quarters"), 7)

    async def test_analyze_returns_no_data_for_missing_area(self):
        def missing_area(site: Site, settings: Settings) -> BusinessArea:
            raise BusinessAreaNoDataError("분석 가능한 상권이 없습니다.")

        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="20244"),
            area_resolver=missing_area,
            run_pipeline=fake_pipeline,
        )

        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.data, {})
        self.assertIsNone(result.error)

    async def test_analyze_returns_error_for_pipeline_failure(self):
        def broken_pipeline(
            area_code: str,
            base_quarter: str,
            quarter_count: int,
            request_id: str | None,
            area_name: str | None,
        ) -> dict[str, Any]:
            raise BusinessLifecycleAgentError("LLM 응답 오류")

        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="20244"),
            area_resolver=fake_area,
            run_pipeline=broken_pipeline,
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.data, {})
        self.assertIsNotNone(result.error)

    async def test_error_does_not_expose_external_details(self):
        secret = "FAKE-SECRET-KEY"

        def broken_pipeline(*args: Any) -> dict[str, Any]:
            raise BusinessLifecycleAgentError(f"https://example.test/{secret}?body=private")

        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="20244"),
            area_resolver=fake_area,
            run_pipeline=broken_pipeline,
        )
        self.assertNotIn(secret, result.model_dump_json())

        def missing_area(site: Site, settings: Settings) -> BusinessArea:
            raise BusinessAreaNoDataError(f"https://example.test/{secret}?body=private")

        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="20244"),
            area_resolver=missing_area,
            run_pipeline=fake_pipeline,
        )
        self.assertNotIn(secret, result.model_dump_json())

    async def test_error_code_does_not_expose_subclass_name(self):
        class FAKE_SECRET_KEY(BusinessLifecycleAgentError):
            pass

        def broken_pipeline(*args: Any) -> dict[str, Any]:
            raise FAKE_SECRET_KEY("private body")

        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="20244"),
            area_resolver=fake_area,
            run_pipeline=broken_pipeline,
        )

        self.assertEqual(result.error.code, "BusinessLifecycleAgentError")
        self.assertNotIn("FAKE_SECRET_KEY", result.model_dump_json())

    async def test_shape_configuration_failure_is_error_not_no_data(self):
        def broken_resolver(site: Site, settings: Settings) -> BusinessArea:
            raise BusinessAreaResolverError("잘못된 SHP 설정")

        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="20244"),
            area_resolver=broken_resolver,
            run_pipeline=fake_pipeline,
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "BusinessAreaResolverError")

    async def test_analyze_returns_no_data_for_empty_store_data(self):
        def empty_pipeline(
            area_code: str,
            base_quarter: str,
            quarter_count: int,
            request_id: str | None,
            area_name: str | None,
        ) -> dict[str, Any]:
            raise ValueError("서울시 Open API에서 조회된 데이터가 없습니다.")

        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="20244"),
            area_resolver=fake_area,
            run_pipeline=empty_pipeline,
        )

        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.data, {})
        self.assertIsNone(result.error)

    async def test_future_override_is_rejected_as_error(self):
        result = await analyze(
            task(),
            settings=Settings(base_quarter_override="29994"),
            area_resolver=fake_area,
            run_pipeline=fake_pipeline,
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "INVALID_INPUT")


class BusinessAreaResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_area_env_override_skips_resolver_and_returns_valid_analysis(self):
        def broken_resolver(site: Site, settings: Settings) -> BusinessArea:
            raise AssertionError("환경변수 override가 있으면 resolver를 호출하지 않아야 합니다.")

        with patch.dict(
            os.environ,
            {
                "BUSINESS_LIFECYCLE_AREA_CODE": "3120240",
                "BUSINESS_LIFECYCLE_AREA_NAME": "개롱역",
            },
        ):
            result = await analyze(
                task(),
                settings=Settings.from_env(base_quarter_override="20244"),
                area_resolver=broken_resolver,
                run_pipeline=fake_pipeline,
            )

        AgentAnalysis.model_validate(result.model_dump())
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.scope.area, "개롱역 (3120240)")
        self.assertEqual(result.data["metadata"]["area_code"], "3120240")
        self.assertEqual(result.data["metadata"]["area_name"], "개롱역")
        self.assertEqual(result.data["metadata"]["area_resolver"]["method"], "env_override")
        self.assertEqual(len(result.data["industries"]), 75)


if __name__ == "__main__":
    unittest.main()

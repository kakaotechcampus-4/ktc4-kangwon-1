"""Business Lifecycle 에이전트의 공통 인터페이스 연결을 검사합니다."""

from __future__ import annotations

import os
import unittest
from typing import Any
from unittest.mock import patch

from app.agents.business_lifecycle.agent import (
    AGENT_ID,
    BusinessLifecycleAgentError,
    analyze,
)
from app.agents.business_lifecycle.area_resolver import (
    BusinessArea,
    BusinessAreaNoDataError,
)
from app.agents.business_lifecycle.config import Settings
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
            "target_industries": 70,
            "scored_industries": 1,
            "unscored_industries": 69,
        },
        "scoring_method": {
            "score_type": "relative",
            "description": "테스트용 점수입니다.",
        },
        "summary": "테스트 요약입니다.",
        "industry_scores": [
            {
                "industry_id": 1,
                "industry_name": "한식음식점",
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
                "industry_name": f"테스트 업종 {industry_id}",
                "data_available": False,
                "confidence": "none",
                "missing_reason": "테스트용 데이터 부족입니다.",
            }
            for industry_id in range(2, 71)
        ],
    }


class BusinessLifecycleAgentTests(unittest.IsolatedAsyncioTestCase):
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
        self.assertEqual(len(result.data["industries"]), 70)

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
        self.assertEqual(len(result.data["industries"]), 70)


if __name__ == "__main__":
    unittest.main()

"""팀 간 전달 규약을 검사합니다."""

import unittest

import app.schemas as schemas
from app.schemas import AgentAnalysis, DecisionRequest


class SchemaTests(unittest.TestCase):
    def test_analysis_task_keeps_resolved_site(self):
        task = schemas.AnalysisTask.model_validate({
            "request_id": "request-001",
            "site": {
                "input_address": "서울특별시 강남구 테헤란로 123, ○○빌딩 3층 302호",
                "road_address": "서울특별시 강남구 테헤란로 123",
                "jibun_address": "서울특별시 강남구 역삼동 123-45",
                "detail_address": "○○빌딩 3층 302호",
                "latitude": 37.5,
                "longitude": 127.03,
            },
        })
        self.assertEqual(task.site.detail_address, "○○빌딩 3층 302호")

    def test_agent_response_accepts_request_id_and_no_data(self):
        result = AgentAnalysis.model_validate({
            "request_id": "request-001",
            "agent_id": "floating_population",
            "status": "no_data",
            "scope": {"area": "서울특별시 강남구 역삼동", "period": "2026년 2분기"},
            "data": {},
            "warnings": ["해당 기간의 유효한 자료가 없습니다."],
        })
        self.assertEqual(result.request_id, "request-001")
        self.assertEqual(result.status, "no_data")

    def test_error_response_requires_code_and_message(self):
        result = AgentAnalysis.model_validate({
            "request_id": "request-001",
            "agent_id": "floating_population",
            "status": "error",
            "data": {},
            "error": {"code": "UPSTREAM_TIMEOUT", "message": "유동인구 API 응답 시간이 초과되었습니다."},
            "warnings": [],
        })
        self.assertEqual(result.error.code, "UPSTREAM_TIMEOUT")

    def test_decision_content_uses_middle_category_and_allows_five(self):
        payload = {
            "status": "ok",
            "summary": "검증용 요약입니다.",
            "recommendations": [
                {
                    "category": {"major": "음식점", "middle": middle},
                    "score": 70 - index,
                    "reasons": ["검증용 근거입니다."],
                    "evidence": [{"agent_id": "floating_population", "path": "/value"}],
                    "risks": [],
                }
                for index, middle in enumerate(["중식", "양식", "일식", "한식", "분식"])
            ],
            "not_recommended": [],
            "limitations": [],
        }
        content = schemas.DecisionContent.model_validate(payload)
        self.assertEqual(content.recommendations[-1].category.middle, "분식")

    def test_decision_request_rejects_another_request_result(self):
        with self.assertRaises(ValueError):
            DecisionRequest.model_validate({
                "request_id": "request-001",
                "address": "서울특별시 강남구 테헤란로 123",
                "analyses": [{
                    "request_id": "request-002",
                    "agent_id": "floating_population",
                    "status": "ok",
                    "scope": {"area": "서울특별시 강남구 역삼동", "period": "2026년 2분기"},
                    "data": {"daily_average": {"value": 12000, "unit": "명/일"}},
                    "warnings": [],
                }],
            })


if __name__ == "__main__":
    unittest.main()

"""중재 에이전트 동작을 검사합니다."""

import copy
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.agents.decision import analyze


BACKEND = Path(__file__).resolve().parents[1]
EXAMPLES = BACKEND / "examples" / "decision"


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads((EXAMPLES / "input.json").read_text(encoding="utf-8"))
        self.response = json.loads((EXAMPLES / "response.json").read_text(encoding="utf-8"))
        self.generate = Mock(return_value=self.response)

    def test_returns_report_and_passes_flexible_data(self):
        result = analyze(self.request, generate=self.generate)
        self.assertEqual(result.request_id, "sample-001")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.recommendations[0].category.middle, "중식")
        self.assertEqual(result.source_analyses[0].data, self.request["analyses"][0]["data"])
        prompt, payload = self.generate.call_args.args
        self.assertIn("성공 확률", prompt)
        self.assertIn("json", prompt.casefold())
        self.assertIn('"reasons"', prompt)
        self.assertIn('"path"', prompt)
        self.assertEqual(json.loads(payload)["analyses"][0]["data"], self.request["analyses"][0]["data"])

    def test_rejects_invalid_input_before_calling_model(self):
        invalid_cases = []
        duplicate = copy.deepcopy(self.request)
        duplicate["analyses"][1] = duplicate["analyses"][0]
        invalid_cases.append(duplicate)
        unknown = copy.deepcopy(self.request)
        unknown["analyses"][0]["agent_id"] = "unknown"
        invalid_cases.append(unknown)
        empty = copy.deepcopy(self.request)
        empty["analyses"][0]["data"] = {}
        invalid_cases.append(empty)
        for request in invalid_cases:
            with self.subTest(request=request), self.assertRaises(ValueError):
                analyze(request, generate=self.generate)
        self.generate.assert_not_called()

    def test_marks_missing_and_partial_sources(self):
        self.request["analyses"].pop(1)
        self.request["analyses"][0]["status"] = "partial"
        self.response["not_recommended"] = []
        result = analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("business_lifecycle" in item for item in result.limitations))
        self.assertTrue(any("floating_population" in item for item in result.limitations))

    def test_all_failed_sources_skip_model(self):
        for analysis in self.request["analyses"]:
            analysis.update(
                status="error", data={}, scope=None,
                error={"code": "UPSTREAM_TIMEOUT", "message": "조회 시간 초과"},
            )
        result = analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.recommendations, [])
        self.generate.assert_not_called()

    def test_rejects_bad_score_duplicate_industry_and_missing_evidence(self):
        bad_score = copy.deepcopy(self.response)
        bad_score["recommendations"][0]["score"] = 101
        duplicate = copy.deepcopy(self.response)
        duplicate["not_recommended"][0]["category"] = {"major": "음식점", "middle": "중식"}
        bad_path = copy.deepcopy(self.response)
        bad_path["recommendations"][0]["evidence"][0]["path"] = "/missing"
        bad_index = copy.deepcopy(self.response)
        bad_index["not_recommended"][0]["evidence"][0]["path"] = "/industries/-1"
        for response in (bad_score, duplicate, bad_path, bad_index):
            with self.subTest(response=response), self.assertRaises(ValueError):
                analyze(self.request, generate=Mock(return_value=response))

    def test_cannot_cite_failed_source(self):
        self.request["analyses"][1].update(
            status="error", data={}, scope=None,
            error={"code": "UPSTREAM_ERROR", "message": "조회 실패"},
        )
        with self.assertRaises(ValueError):
            analyze(self.request, generate=self.generate)

    def test_accepts_insufficient_data_without_inventing_recommendations(self):
        self.response.update(
            status="no_data", recommendations=[], not_recommended=[],
            limitations=["업종 판단에 필요한 자료가 부족합니다."],
        )
        result = analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "no_data")

    def test_marks_no_data_source_as_partial(self):
        self.request["analyses"][0].update(
            status="no_data", data={}, error=None,
            warnings=["해당 기간의 유효한 자료가 없습니다."],
        )
        self.response["recommendations"][0]["evidence"] = [
            {"agent_id": "commercial_area", "path": "/industry_counts/중식"}
        ]
        result = analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("자료 없음: floating_population" in item for item in result.limitations))

    def test_scope_difference_and_escaped_evidence(self):
        self.request["analyses"][1]["scope"]["period"] = "2026년 1분기"
        self.request["analyses"][0]["data"]["시간/비율~"] = 65
        self.response["recommendations"][0]["evidence"][0]["path"] = "/시간~1비율~0"
        result = analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("기준 기간" in item for item in result.limitations))

    def test_model_failure_is_not_replaced_by_sample(self):
        with self.assertRaisesRegex(RuntimeError, "연결 실패"):
            analyze(self.request, generate=Mock(side_effect=RuntimeError("연결 실패")))

    def test_mock_input_uses_model_call(self):
        spec = importlib.util.spec_from_file_location("run_decision", BACKEND / "examples" / "run_decision.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with patch.object(sys, "argv", ["run_decision.py", "--mock"]), \
                patch("app.agents.decision.agent.generate_decision", side_effect=RuntimeError("연결 시험")), \
                patch.object(sys, "stderr", stderr):
            self.assertEqual(module.main(), 1)


if __name__ == "__main__":
    unittest.main()

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


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_corrects_invalid_evidence_once_without_changing_sources(self):
        broken = copy.deepcopy(self.response)
        broken["recommendations"][0]["evidence"][0]["path"] = "/missing"
        inputs = []

        async def generate(prompt, payload):
            inputs.append(json.loads(payload))
            return broken if len(inputs) == 1 else copy.deepcopy(self.response)

        result = await analyze(self.request, generate=generate)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(inputs), 2)
        self.assertEqual(inputs[0]["analyses"], inputs[1]["analyses"])
        self.assertEqual(inputs[1]["correction"]["reason"], "evidence_not_found")
        self.assertNotIn("supplement_operations", inputs[1])

    async def test_invalid_correction_stops_after_two_model_calls(self):
        broken = copy.deepcopy(self.response)
        broken["recommendations"][0]["evidence"][0]["path"] = "/missing"
        generate = Mock(return_value=broken)
        with self.assertRaises(ValueError):
            await analyze(self.request, generate=generate)
        self.assertEqual(generate.call_count, 2)

    async def test_schema_and_transport_failures_do_not_trigger_correction(self):
        for generate in (Mock(return_value={}), Mock(side_effect=RuntimeError("연결 실패"))):
            with self.assertRaises((ValueError, RuntimeError)):
                await analyze(self.request, generate=generate)
            self.assertEqual(generate.call_count, 1)

    async def test_risk_number_error_names_sentence_path_and_units(self):
        inputs = []

        async def generate(prompt, payload):
            inputs.append(json.loads(payload))
            content = copy.deepcopy(self.response)
            if len(inputs) == 1:
                content["recommendations"][0]["risks"] = ["주변보다 {1}% 높습니다."]
            return content

        result = await analyze(self.request, generate=generate)
        self.assertEqual(result.status, "ok")
        correction = inputs[1]["correction"]
        self.assertEqual(correction["field"], "recommendations.0.risks.0")
        self.assertEqual(correction["sentence"], "주변보다 {1}% 높습니다.")
        self.assertEqual(
            correction["problem"],
            {
                "index": 1,
                "agent_id": "commercial_area",
                "path": "/by_middle/0/lq",
                "unit": "%",
                "allowed_units": ["배"],
            },
        )
        self.assertEqual(
            correction["evidence"],
            [
                {"index": 0, "agent_id": "commercial_area", "path": "/by_middle/0/count"},
                {"index": 1, "agent_id": "commercial_area", "path": "/by_middle/0/lq"},
            ],
        )

    async def test_correction_lists_every_citation_error_in_the_output(self):
        inputs = []

        async def generate(prompt, payload):
            inputs.append(json.loads(payload))
            content = copy.deepcopy(self.response)
            if len(inputs) == 1:
                content["recommendations"][0]["risks"] = ["주변보다 {1}% 높습니다."]
                content["not_recommended"][0]["reasons"] = ["폐업이 9개입니다."]
            return content

        result = await analyze(self.request, generate=generate)
        self.assertEqual(result.status, "ok")
        correction = inputs[1]["correction"]
        self.assertEqual(correction["field"], "recommendations.0.risks.0")
        others = correction["other_problems"]
        self.assertEqual(len(others), 1)
        self.assertEqual(others[0]["field"], "not_recommended.0.reasons.0")
        self.assertEqual(others[0]["reason"], "number_uncited")
        self.assertEqual(others[0]["sentence"], "폐업이 9개입니다.")
        self.assertEqual(others[0]["problem"], {"number": "9"})
        self.assertEqual(len(others[0]["evidence"]), 2)

    async def test_single_citation_error_has_no_other_problems(self):
        inputs = []

        async def generate(prompt, payload):
            inputs.append(json.loads(payload))
            content = copy.deepcopy(self.response)
            if len(inputs) == 1:
                content["recommendations"][0]["risks"] = ["주변보다 {1}% 높습니다."]
            return content

        await analyze(self.request, generate=generate)
        self.assertNotIn("other_problems", inputs[1]["correction"])

    async def test_duplicate_key_json_gets_one_correction_without_previous_output(self):
        from app.llm.client import LLMResponseError

        calls = []

        async def generate(prompt, payload):
            calls.append((prompt, json.loads(payload)))
            if len(calls) == 1:
                raise LLMResponseError("LLM_INVALID_JSON", duplicate_key="evidence")
            return copy.deepcopy(self.response)

        result = await analyze(self.request, generate=generate)
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(calls), 2)
        prompt, payload = calls[1]
        self.assertEqual(
            payload["correction"],
            {
                "stage": "decision_output",
                "field": "output",
                "reason": "duplicate_key",
                "key": "evidence",
                "correction_attempt": 0,
            },
        )
        self.assertNotIn("previous_decision", payload)
        self.assertIn("evidence 키를 두 번", prompt)

    async def test_duplicate_key_twice_stops_after_two_calls(self):
        from app.llm.client import LLMResponseError

        generate = Mock(side_effect=LLMResponseError("LLM_INVALID_JSON", duplicate_key="evidence"))
        with self.assertRaises(RuntimeError) as caught:
            await analyze(self.request, generate=generate)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(caught.exception.failures[0]["reason"], "duplicate_key")

    async def test_other_invalid_json_is_not_corrected(self):
        from app.llm.client import LLMResponseError

        generate = Mock(side_effect=LLMResponseError("LLM_INVALID_JSON"))
        with self.assertRaises(LLMResponseError):
            await analyze(self.request, generate=generate)
        self.assertEqual(generate.call_count, 1)

    async def test_correction_cannot_switch_to_data_supplement(self):
        from app.agents.decision.agent import evaluate
        from app.schemas import SupplementOperation

        broken = copy.deepcopy(self.response)
        broken["recommendations"][0]["evidence"][0]["path"] = "/missing"
        plan = {
            "action": "supplement",
            "requests": [
                {
                    "agent_id": "commercial_area",
                    "operation": "retry_lq_baseline",
                    "decision_question": "경쟁 수준",
                    "missing_information": "비교 자료",
                    "why_needed": "추천 판단",
                    "expected_impact": "경쟁 판단 변경",
                }
            ],
        }
        generate = Mock(side_effect=[broken, plan])
        with self.assertRaises(ValueError):
            await evaluate(
                self.request,
                generate=generate,
                operations=[
                    SupplementOperation(
                        agent_id="commercial_area",
                        operation="retry_lq_baseline",
                        description="비교 조회",
                    )
                ],
            )
        self.assertEqual(generate.call_count, 2)
        self.assertNotIn("supplement_operations", json.loads(generate.call_args.args[1]))

    async def test_contract_diagnostics_distinguish_category_and_evidence_without_values(self):
        self.request["analyses"][0]["data"]["empty"] = None
        for field, value, reason in (
            ("middle", "SECRET", "unknown_industry"),
            ("major", "SECRET", "major_mismatch"),
            ("path", "/SECRET", "evidence_not_found"),
            ("path", "/~SECRET", "evidence_path_invalid"),
            ("path", "/empty", "evidence_empty"),
        ):
            response = copy.deepcopy(self.response)
            item = response["recommendations"][0]
            if field == "path":
                item["evidence"][0]["agent_id"] = "floating_population"
                item["evidence"][0][field] = value
            else:
                item["category"][field] = value
            with self.subTest(reason=reason), self.assertRaises(ValueError) as caught:
                await analyze(self.request, generate=lambda *_, response=response: response)
            self.assertEqual(getattr(caught.exception, "code", None), "DECISION_CONTRACT_INVALID")
            diagnostics = caught.exception.diagnostics
            self.assertEqual(diagnostics["reason"], reason)
            self.assertEqual(diagnostics["stage"], "decision_validation")
            self.assertTrue(diagnostics["field"].startswith("recommendations.0."))
            self.assertNotIn("SECRET", str(caught.exception) + str(diagnostics))

    def setUp(self):
        self.request = json.loads((EXAMPLES / "input.json").read_text(encoding="utf-8"))
        self.response = json.loads((EXAMPLES / "response.json").read_text(encoding="utf-8"))
        self.generate = Mock(return_value=self.response)

    async def test_bare_numbers_get_one_correction_then_are_rendered(self):
        inputs = []

        async def generate(prompt, payload):
            inputs.append(json.loads(payload))
            content = copy.deepcopy(self.response)
            if len(inputs) == 1:
                content["recommendations"][0]["reasons"] = ["점포가 96개입니다."]
            return content

        result = await analyze(self.request, generate=generate)
        self.assertEqual(len(inputs), 2)
        self.assertEqual(inputs[1]["correction"]["reason"], "number_uncited")
        reasons = " ".join(result.recommendations[0].reasons + result.recommendations[0].risks)
        self.assertNotIn("{", reasons)
        self.assertIn("96", reasons)

    async def test_correction_input_keeps_placeholders_when_a_later_item_fails(self):
        inputs = []

        async def generate(prompt, payload):
            inputs.append(json.loads(payload))
            content = copy.deepcopy(self.response)
            if len(inputs) == 1:
                content["not_recommended"][0]["reasons"] = ["폐업이 9개입니다."]
            return content

        result = await analyze(self.request, generate=generate)
        previous = inputs[1]["previous_decision"]
        self.assertEqual(
            previous["recommendations"][0]["reasons"],
            self.response["recommendations"][0]["reasons"],
        )
        self.assertNotIn("{", " ".join(result.recommendations[0].reasons))

    async def test_summary_numbers_fail_after_correction(self):
        from app.agents.decision.agent import DecisionContractError

        broken = {**copy.deepcopy(self.response), "summary": "점포 96개"}
        generate = Mock(return_value=broken)
        with self.assertRaises(DecisionContractError) as caught:
            await analyze(self.request, generate=generate)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(caught.exception.diagnostics["reason"], "number_uncited")

    async def test_returns_report_and_passes_flexible_data(self):
        result = await analyze(self.request, generate=self.generate)
        self.generate.assert_called_once()
        self.assertEqual(result.request_id, "sample-001")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.recommendations[0].category.middle, "한식 음식점업")
        self.assertEqual(result.source_analyses[0].data, self.request["analyses"][0]["data"])
        prompt, payload = self.generate.call_args.args
        self.assertIn("성공 확률", prompt)
        self.assertIn("json", prompt.casefold())
        self.assertIn('"reasons"', prompt)
        self.assertIn('"path"', prompt)
        self.assertIn("반드시 5개", prompt)
        self.assertEqual(
            json.loads(payload)["analyses"][0]["data"], self.request["analyses"][0]["data"]
        )

    async def test_sample_lifecycle_rows_are_catalog_industries(self):
        industries = self.request["analyses"][1]["data"]["industries"]
        self.assertEqual([row["industry_id"] for row in industries], ["I201", "I212"])

    async def test_rejects_invalid_input_before_calling_model(self):
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
                await analyze(request, generate=self.generate)
        self.generate.assert_not_called()

    async def test_marks_missing_and_partial_sources(self):
        self.request["analyses"].pop(1)
        self.request["analyses"][0]["status"] = "partial"
        self.response["not_recommended"] = []
        result = await analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("business_lifecycle" in item for item in result.limitations))
        self.assertTrue(any("floating_population" in item for item in result.limitations))

    async def test_all_failed_sources_skip_model(self):
        for analysis in self.request["analyses"]:
            analysis.update(
                status="error",
                data={},
                scope=None,
                error={"code": "UPSTREAM_TIMEOUT", "message": "조회 시간 초과"},
            )
        result = await analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "no_data")
        self.assertEqual(result.recommendations, [])
        self.generate.assert_not_called()

    async def test_rejects_bad_score_duplicate_industry_and_missing_evidence(self):
        bad_score = copy.deepcopy(self.response)
        bad_score["recommendations"][0]["score"] = 101
        duplicate = copy.deepcopy(self.response)
        duplicate["not_recommended"][0]["category"] = {
            "major": "음식점업",
            "middle": "중식 음식점업",
        }
        bad_path = copy.deepcopy(self.response)
        bad_path["recommendations"][0]["evidence"][0]["path"] = "/missing"
        bad_index = copy.deepcopy(self.response)
        bad_index["not_recommended"][0]["evidence"][0]["path"] = "/industries/-1"
        for response in (bad_score, duplicate, bad_path, bad_index):
            with self.subTest(response=response), self.assertRaises(ValueError):
                await analyze(self.request, generate=Mock(return_value=response))

    async def test_cannot_cite_failed_source(self):
        self.request["analyses"][1].update(
            status="error",
            data={},
            scope=None,
            error={"code": "UPSTREAM_ERROR", "message": "조회 실패"},
        )
        with self.assertRaises(ValueError):
            await analyze(self.request, generate=self.generate)

    async def test_accepts_insufficient_data_without_inventing_recommendations(self):
        self.response.update(
            status="no_data",
            recommendations=[],
            not_recommended=[],
            limitations=["업종 판단에 필요한 자료가 부족합니다."],
        )
        result = await analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "no_data")

    async def test_marks_no_data_source_as_partial(self):
        self.request["analyses"][0].update(
            status="no_data",
            data={},
            error=None,
            warnings=["해당 기간의 유효한 자료가 없습니다."],
        )
        self.response["recommendations"][0]["evidence"] = [
            {"agent_id": "commercial_area", "path": "/by_middle/0/count"}
        ]
        self.response["recommendations"][0]["reasons"] = ["반경 안 점포가 {0}개입니다."]
        result = await analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "partial")
        self.assertTrue(
            any("자료 없음: floating_population" in item for item in result.limitations)
        )

    async def test_scope_difference_and_escaped_evidence(self):
        self.request["analyses"][1]["scope"]["period"] = "2026년 1분기"
        self.request["analyses"][0]["data"]["시간/비율~"] = 65
        self.response["recommendations"][0]["evidence"][0] = {
            "agent_id": "floating_population",
            "path": "/시간~1비율~0",
        }
        self.response["recommendations"][0]["reasons"] = ["근거 값은 {0}입니다."]
        self.response["recommendations"][0]["risks"] = []
        result = await analyze(self.request, generate=self.generate)
        self.assertEqual(result.status, "partial")
        self.assertTrue(any("기준 기간" in item for item in result.limitations))

    async def test_model_failure_is_not_replaced_by_sample(self):
        with self.assertRaisesRegex(RuntimeError, "연결 실패"):
            await analyze(self.request, generate=Mock(side_effect=RuntimeError("연결 실패")))

    async def test_mock_input_uses_model_call(self):
        spec = importlib.util.spec_from_file_location(
            "run_decision", BACKEND / "examples" / "run_decision.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with (
            patch.object(sys, "argv", ["run_decision.py", "--mock"]),
            patch(
                "app.agents.decision.agent.generate_decision", side_effect=RuntimeError("연결 시험")
            ),
            patch.object(sys, "stderr", stderr),
        ):
            self.assertEqual(module.main(), 1)


if __name__ == "__main__":
    unittest.main()

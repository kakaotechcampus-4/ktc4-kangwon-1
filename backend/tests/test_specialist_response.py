"""전문가 도구 응답의 순수 해석과 부분 형식 검증을 검사합니다."""

import json
import unittest

from app.agents.specialists.response import parse_finish, parse_tool_response


def produced(arguments, *, name="finish"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": arguments,
                },
            }
        ],
    }


class SpecialistResponseTests(unittest.TestCase):
    def test_only_one_tool_call_is_allowed(self):
        for calls in ([], produced("{}")["tool_calls"] * 2):
            with self.subTest(calls=calls), self.assertRaises(ValueError):
                parse_tool_response({"role": "assistant", "tool_calls": calls})

    def test_arguments_must_be_json_object(self):
        for raw in ("broken", "[]", "null"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_tool_response(produced(raw))

    def test_parsed_call_preserves_model_message_and_unknown_tool(self):
        parsed = parse_tool_response(produced(json.dumps({"code": "I202"}), name="unknown"))
        self.assertEqual(parsed.name, "unknown")
        self.assertEqual(parsed.arguments, {"code": "I202"})
        self.assertEqual(parsed.call_id, "call")
        self.assertEqual(parsed.message.tool_calls[0].function.name, "unknown")

    def test_finish_drops_only_invalid_findings(self):
        valid = {
            "claim": "확인한 값 7",
            "signal": "context",
            "industry_code": None,
            "evidence": [{"path": "/total"}],
        }
        content = parse_finish({"headline": "요약", "findings": [valid, {}]})
        self.assertEqual(len(content.findings), 1)
        self.assertEqual(content.limitations, ["전문가 근거 제외: 2번 형식 오류"])

    def test_finish_keeps_existing_eight_finding_limit(self):
        valid = {
            "claim": "확인한 값 7",
            "signal": "context",
            "industry_code": None,
            "evidence": [{"path": "/total"}],
        }
        self.assertEqual(
            len(parse_finish({"headline": "요약", "findings": [valid] * 9}).findings), 8
        )

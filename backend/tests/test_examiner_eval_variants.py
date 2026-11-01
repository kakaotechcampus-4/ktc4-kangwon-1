"""심사위원 V0·V1·V2 바꿔 끼우기 테스트."""

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agentic import aliases, evaluators, examiner
from app.agentic.tools import ToolExecutor
from examiner_eval import frozen_v1
from examiner_eval.variants import VARIANTS, use_variant

V0_PERSONA = (
    "심사관입니다. 근거의 원천·기간·반경, L 중복 채점과 전체 업종의 unknown 이유를 검증하세요. "
    "검토 전 공간 초안이 확정 사실이나 점수 근거가 되었는지 확인하세요."
)


def examiner_tool_names():
    executor = ToolExecutor(None, None, actor="examiner")
    return {d["function"]["name"] for d in executor.definitions()}


class VariantsTest(unittest.TestCase):
    def test_variant_names(self):
        self.assertEqual(VARIANTS, ("V0", "V1", "V2"))

    def test_v0_restores_old_persona_packet_and_query_raw(self):
        persona = evaluators.PERSONAS["examiner"]
        packet = examiner.review_packet
        definitions = ToolExecutor.definitions
        self.assertNotIn("query_raw", examiner_tool_names())
        with use_variant("V0"):
            self.assertEqual(evaluators.PERSONAS["examiner"], V0_PERSONA)
            self.assertIs(examiner.review_packet, evaluators.review_packet)
            self.assertIn("query_raw", examiner_tool_names())
        self.assertEqual(evaluators.PERSONAS["examiner"], persona)
        self.assertIs(examiner.review_packet, packet)
        self.assertIs(ToolExecutor.definitions, definitions)
        self.assertNotIn("query_raw", examiner_tool_names())

    def test_v0_reserve_allows_query_raw_for_examiner(self):
        executor = ToolExecutor(None, None, actor="examiner")
        args = {"sql": "select 1"}
        with use_variant("V0"):
            self.assertIsNone(executor._reserve("query_raw", args))
        executor = ToolExecutor(None, None, actor="examiner")
        self.assertIsNotNone(executor._reserve("query_raw", args))

    def test_v0_keeps_other_actors_unchanged(self):
        before = {
            actor: {
                d["function"]["name"] for d in ToolExecutor(None, None, actor=actor).definitions()
            }
            for actor in ("decision", "advisor", "founder")
        }
        with use_variant("V0"):
            after = {
                actor: {
                    d["function"]["name"]
                    for d in ToolExecutor(None, None, actor=actor).definitions()
                }
                for actor in ("decision", "advisor", "founder")
            }
        self.assertEqual(before, after)

    def test_v0_wraps_original_definitions(self):
        fake = [{"function": {"name": "fake_tool"}}]
        with patch.object(ToolExecutor, "definitions", lambda self: list(fake)):
            with use_variant("V0"):
                names = examiner_tool_names()
                other = ToolExecutor(None, None, actor="decision").definitions()
        self.assertEqual(names, {"fake_tool", "query_raw"})
        self.assertEqual(other, fake)

    def test_v1_uses_frozen_copy(self):
        persona = evaluators.PERSONAS["examiner"]
        packet = examiner.review_packet
        with use_variant("V1"):
            self.assertEqual(evaluators.PERSONAS["examiner"], frozen_v1.PERSONA)
            self.assertIs(examiner.review_packet, frozen_v1.review_packet)
        self.assertEqual(evaluators.PERSONAS["examiner"], persona)
        self.assertIs(examiner.review_packet, packet)

    def test_v2_changes_nothing(self):
        persona = evaluators.PERSONAS["examiner"]
        packet = examiner.review_packet
        definitions = ToolExecutor.definitions
        with use_variant("V2"):
            self.assertIs(evaluators.PERSONAS["examiner"], persona)
            self.assertIs(examiner.review_packet, packet)
            self.assertIs(ToolExecutor.definitions, definitions)

    def test_baselines_keep_period_codes(self):
        for name in ("V0", "V1"):
            with use_variant(name):
                self.assertFalse(aliases.labels_periods("examiner"))
        with use_variant("V2"):
            self.assertTrue(aliases.labels_periods("examiner"))
        self.assertTrue(aliases.labels_periods("examiner"))

    def test_unknown_variant_raises(self):
        with self.assertRaises(ValueError):
            with use_variant("V9"):
                pass

    def test_restores_when_block_raises(self):
        persona = evaluators.PERSONAS["examiner"]
        packet = examiner.review_packet
        definitions = ToolExecutor.definitions
        for name in ("V0", "V1"):
            with self.assertRaises(RuntimeError):
                with use_variant(name):
                    raise RuntimeError("boom")
            self.assertIs(evaluators.PERSONAS["examiner"], persona)
            self.assertIs(examiner.review_packet, packet)
            self.assertIs(ToolExecutor.definitions, definitions)

    def test_frozen_v1_has_no_relative_imports(self):
        source = Path(frozen_v1.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*from \.", source, re.MULTILINE))


if __name__ == "__main__":
    unittest.main()

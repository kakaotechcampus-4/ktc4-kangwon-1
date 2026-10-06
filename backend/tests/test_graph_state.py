"""옛 재개 상태를 읽으면서 저장된 입력을 바꾸지 않는지 확인합니다."""

import copy
import unittest

from app.agents.orchestration.graph import normalize_resume_state


class ResumeStateTests(unittest.TestCase):
    def test_legacy_context_moves_to_top_level_without_mutating_input(self):
        old = {
            "consult_round": 1,
            "context": {"map_queries": [], "feedback": ["이전 근거"], "supplement_context": []},
        }
        before = copy.deepcopy(old)
        restored = normalize_resume_state(old, mode="multi_agent")
        self.assertNotIn("context", restored)
        self.assertEqual(restored["feedback"], ["이전 근거"])
        self.assertEqual(restored["consult_round"], 1)
        self.assertEqual(old, before)
        self.assertEqual(normalize_resume_state(restored, mode="multi_agent"), restored)

    def test_legacy_duplicate_fields_preserve_existing_mode_precedence(self):
        old = {"feedback": ["최상위"], "context": {"feedback": ["중첩"]}}
        self.assertEqual(normalize_resume_state(old, mode="multi_agent")["feedback"], ["중첩"])
        self.assertEqual(
            normalize_resume_state(old, mode="single_decision")["feedback"], ["최상위"]
        )

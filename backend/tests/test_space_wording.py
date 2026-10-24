"""검토를 마친 업종 공간 요건표를 모델 안내와 사실 자료가 초안이라고 부르지 않는지 확인합니다."""

import inspect
import unittest

from app.agentic import evaluators, examiner, landlord, runtime, space

STALE = ("공간 초안", "검토 전", "초안을 확정", "초안과 미확인", "초안이나 결측")


class SpaceWordingTests(unittest.TestCase):
    def test_model_prompts_do_not_call_requirements_a_draft(self):
        prompts = {
            "founder": evaluators.PERSONAS["founder"],
            "examiner": examiner.PERSONA,
            "landlord": landlord.PERSONA,
            "decision": runtime.SYSTEM_PROMPT,
        }
        for name, text in prompts.items():
            for word in STALE:
                with self.subTest(prompt=name, word=word):
                    self.assertNotIn(word, text)

    def test_space_fit_fact_wording_is_current(self):
        source = inspect.getsource(space.ensure_space_fits)
        for word in STALE:
            with self.subTest(word=word):
                self.assertNotIn(word, source)

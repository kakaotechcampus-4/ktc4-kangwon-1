"""재개 상태 조립이 기존 실행 경로별 값을 유지하는지 확인합니다."""

import unittest
from types import SimpleNamespace

from app.services.analysis import build_resume_state


class ResumeTests(unittest.TestCase):
    def test_resume_and_retry_keep_existing_tool_flags(self):
        observation = object()
        bundle = {
            "task": object(),
            "request": SimpleNamespace(analyses=[], map_observation=observation),
            "briefs": [],
            "specialist_answers": [],
            "consult_round": 2,
            "map_queries": [],
            "feedback": ["저장된 안내"],
            "supplement_context": [object()],
        }
        resumed = build_resume_state(bundle)
        self.assertNotIn("map_done", resumed)
        self.assertNotIn("supplement_done", resumed)
        self.assertIs(resumed["map_observation"], observation)
        self.assertEqual(resumed["feedback"], ["저장된 안내"])
        retried = build_resume_state(bundle, retry=True)
        self.assertTrue(retried["map_done"])
        self.assertTrue(retried["supplement_done"])
        self.assertEqual(retried["consult_round"], 2)

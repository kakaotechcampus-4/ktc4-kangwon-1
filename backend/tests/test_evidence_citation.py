"""세 판단 경로에서 공유하는 근거 허용과 진단 사유를 확인합니다."""

import unittest

from test_map_matching import observation

from app.evidence import can_cite
from app.schemas import MapObservation


class CitationTests(unittest.TestCase):
    def test_analysis_paths_preserve_diagnostic_reasons(self):
        data = {
            "by_middle": [{"code": "I201", "count": 3}],
            "empty": None,
            "blocked": {"citable": False, "count": 1},
        }
        for path, code, reason in (
            ("/by_middle/0/count", "I201", None),
            ("/by_middle/0/count", "I202", "evidence_industry_mismatch"),
            ("/by_middle/0/count", None, "evidence_industry_mismatch"),
            ("not/a/path", None, "evidence_path_invalid"),
            ("/missing", None, "evidence_not_found"),
            ("/empty", None, "evidence_empty"),
            ("/blocked/count", None, "evidence_unavailable"),
        ):
            with self.subTest(path=path, code=code):
                self.assertEqual(can_cite(data, path, code), reason)

    def test_map_model_preserves_shared_places_and_disallows_search_totals(self):
        data = MapObservation.model_validate(observation()).data
        for code in ("I212", "I210"):
            self.assertIsNone(can_cite(data, "/places/x/distance_m", code))
        self.assertEqual(can_cite(data, "/places/x/name", "I201"), "업종")
        self.assertEqual(can_cite(data, "/queries/q1/total_count", "I212"), "필드")

"""심사위원 시험 사례 자료형 테스트."""

import tempfile
import unittest
from pathlib import Path

from examiner_eval.cases import Case, Seed, dump_cases, load_cases, split_requests


class CasesTest(unittest.TestCase):
    def test_round_trip(self):
        seed = Seed(
            kind="E1",
            industry_code="CS100001",
            field="reasons_segments",
            expected_kind="missing_evidence",
            support_fact_ids=("f1", "f2"),
            wrong_fact_id=None,
        )
        seed2 = Seed(
            kind="E3",
            industry_code="CS100002",
            field="risks_segments",
            expected_kind="scope_mismatch",
            support_fact_ids=(),
            wrong_fact_id="f9",
        )
        cases = [
            Case(
                case_id="c1",
                request_id="r1",
                split="tune",
                source="seeded",
                draft={"reasons_segments": [{"text": "한글"}]},
                seeds=(seed, seed2),
            ),
            Case(
                case_id="c2",
                request_id="r2",
                split="test",
                source="clean",
                draft={},
                seeds=(),
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            dump_cases(cases, path)
            self.assertIn("한글", path.read_text(encoding="utf-8"))
            self.assertEqual(load_cases(path), cases)

    def test_split_is_half_and_stable(self):
        ids = [f"addr{i}" for i in range(10)]
        result = split_requests(ids)
        self.assertEqual(sum(v == "tune" for v in result.values()), 5)
        self.assertEqual(sum(v == "test" for v in result.values()), 5)
        self.assertEqual(result, split_requests(ids))
        self.assertEqual(result, split_requests(list(reversed(ids))))

    def test_odd_count(self):
        result = split_requests([f"a{i}" for i in range(5)])
        self.assertEqual(sum(v == "tune" for v in result.values()), 3)
        self.assertEqual(sum(v == "test" for v in result.values()), 2)


if __name__ == "__main__":
    unittest.main()

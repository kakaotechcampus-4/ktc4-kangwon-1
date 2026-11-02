"""입력 평균의 반올림 때문에 실제 노출량 40을 미확인으로 낮추지 않는지 검사합니다."""

import unittest
from collections import defaultdict

from app.agentic.inputs import format_inputs
from app.agentic.scoring import score_item
from app.agents.business_lifecycle.baseline import BASELINE_BASE_QUARTER, BASELINE_QUARTER_COUNT
from app.agents.business_lifecycle.client import get_recent_quarters
from app.schemas import AnalysisTask, Site


class LifecycleInputPrecisionTests(unittest.TestCase):
    def formatted(self, total):
        counts = [total // 12] * 12
        for i in range(total % 12):
            counts[i] += 1
        raw = defaultdict(list)
        for quarter, count in zip(
            get_recent_quarters(BASELINE_BASE_QUARTER, BASELINE_QUARTER_COUNT), counts, strict=True
        ):
            raw["business_lifecycle"].append(
                {
                    "raw_row_id": None,
                    "row": {
                        "STDR_YYQU_CD": quarter,
                        "TRDAR_CD": "a",
                        "SVC_INDUTY_CD": "CS100001",
                        "SIMILR_INDUTY_STOR_CO": count,
                        "STOR_CO": count,
                        "FRC_STOR_CO": 0,
                        "OPBIZ_STOR_CO": 0,
                        "CLSBIZ_STOR_CO": 0,
                        "OPBIZ_RT": 0,
                        "CLSBIZ_RT": 0,
                    },
                }
            )
        task = AnalysisTask(
            request_id="precision",
            site=Site(
                input_address="서울 테스트",
                road_address="서울 테스트",
                latitude=37.5,
                longitude=127.0,
            ),
            radius_m=500,
        )
        data, _, _ = format_inputs(task, raw, [], set())
        return data

    def test_exactly_40_store_quarters_survive_formatting_and_are_observed(self):
        data = self.formatted(40)
        row = next(
            r for r in data["business_lifecycle"]["industries"] if r["industry_id"] == "I201"
        )
        self.assertEqual(row["metrics"]["avg_store_count"] * 12, 40)
        for name in ("S1", "S3"):
            item = score_item(name, {}, "I201", data)
            self.assertEqual(item["status"], "observed")
            self.assertEqual(item["value"], 0)
        self.assertEqual(score_item("S2", {}, "I201", data)["status"], "unknown")

    def test_39_store_quarters_remain_unknown(self):
        data = self.formatted(39)
        self.assertEqual(score_item("S1", {}, "I201", data)["status"], "unknown")

    def test_zero_denominator_is_not_observed_zero_rate(self):
        data = self.formatted(0)
        row = next(
            r for r in data["business_lifecycle"]["industries"] if r["industry_id"] == "I201"
        )
        self.assertIsNone(row["metrics"]["recent_year_close_rate"])
        self.assertEqual(score_item("S1", {}, "I201", data)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()

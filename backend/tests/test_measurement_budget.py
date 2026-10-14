"""측정 모드는 역할 제한을 풀어도 누적 예산과 재개 이력을 지킵니다."""

import unittest
from unittest.mock import patch

from app.agents.agentic.budget import RuntimeBudget
from app.llm.budget import BudgetExceeded


class MeasurementBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_has_no_role_call_limits(self):
        for role, final, limit in [
            ("decision", False, 8),
            ("decision", True, 4),
            ("advisor", False, 2),
            ("evaluator", False, 3),
        ]:
            with self.subTest(role=role, final=final):
                budget = RuntimeBudget()
                for attempt in range(1, limit + 1):
                    self.assertEqual(await budget.reserve(role, final=final), attempt)
                await budget.reserve(role, final=final)
                self.assertEqual(budget.used, limit + 1)

    async def test_default_cumulative_limits_are_preserved(self):
        for saved in [
            {"used": 40},
            {"active_seconds": 600},
            {
                "used": 1,
                "calls": [{"role": "decision", "input_tokens": 400000, "output_tokens": 0}],
            },
            {
                "used": 1,
                "calls": [{"role": "decision", "input_tokens": 0, "output_tokens": 60000}],
            },
        ]:
            with self.subTest(saved=saved):
                budget = RuntimeBudget(saved)
                with self.assertRaises(BudgetExceeded):
                    await budget.reserve("decision", input_chars=2)

    async def test_measurement_allows_more_than_each_role_limit(self):
        for role, final in [
            ("decision", False),
            ("decision", True),
            ("advisor", False),
            ("evaluator", False),
        ]:
            with self.subTest(role=role, final=final):
                budget = RuntimeBudget(measurement=True)
                for attempt in range(1, 10):
                    self.assertEqual(await budget.reserve(role, final=final), attempt)

    async def test_measurement_stops_after_forty_calls(self):
        budget = RuntimeBudget(measurement=True)
        for attempt in range(1, 41):
            self.assertEqual(await budget.reserve("decision"), attempt)
        with self.assertRaises(BudgetExceeded):
            await budget.reserve("decision")
        self.assertEqual(budget.used, 40)

    async def test_measurement_cumulative_limits_are_enforced(self):
        for saved in [
            {"active_seconds": 600},
            {
                "used": 1,
                "calls": [{"role": "decision", "input_tokens": 400000, "output_tokens": 0}],
            },
            {
                "used": 1,
                "calls": [{"role": "decision", "input_tokens": 0, "output_tokens": 60000}],
            },
        ]:
            with self.subTest(saved=saved):
                budget = RuntimeBudget(saved, measurement=True)
                with self.assertRaises(BudgetExceeded):
                    await budget.reserve("decision", input_chars=2)
                self.assertEqual(budget.used, saved.get("used", 0))

    async def test_measurement_resumes_saved_counters_and_estimates(self):
        with patch("app.agents.agentic.budget.monotonic", return_value=100):
            budget = RuntimeBudget({"active_seconds": 599}, measurement=True)
            budget.schema_chars = 10000
            self.assertEqual(await budget.reserve("decision", input_chars=790000), 1)
            resumed = RuntimeBudget(budget.snapshot(), measurement=True)
            self.assertEqual(resumed.used, 1)
            self.assertEqual(resumed.totals(), (400000, 0))
            self.assertEqual(resumed.active_seconds, 599)
            with self.assertRaises(BudgetExceeded):
                await resumed.reserve("decision", input_chars=2)
        with patch("app.agents.agentic.budget.monotonic", return_value=101):
            with self.assertRaises(BudgetExceeded):
                await resumed.reserve("decision")

    async def test_saved_measurement_does_not_enable_measurement(self):
        budget = RuntimeBudget({"measurement": True})
        for _ in range(8):
            await budget.reserve("decision")
        await budget.reserve("decision")
        self.assertFalse(budget.measurement)

    async def test_parallel_output_reservations_never_exceed_total(self):
        budget = RuntimeBudget()
        reservations = [await budget.claim_output() for _ in range(4)]
        self.assertEqual(reservations, [16000, 16000, 16000, 12000])
        with self.assertRaises(BudgetExceeded):
            await budget.claim_output()
        await budget.release_output(16000)
        self.assertEqual(await budget.claim_output(), 16000)


if __name__ == "__main__":
    unittest.main()

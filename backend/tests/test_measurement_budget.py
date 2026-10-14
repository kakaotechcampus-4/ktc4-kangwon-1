"""측정 모드도 역할 예약·누적 예산·재개 이력을 지킵니다."""

import unittest
from unittest.mock import patch

from app.agentic.budget import RuntimeBudget
from app.llm.budget import BudgetExceeded


class MeasurementBudgetTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_preserves_role_call_reservations(self):
        for role, final, limit in [
            ("decision", False, 20),
            ("decision", True, 2),
            ("advisor", False, 2),
            ("examiner", False, 4),
        ]:
            with self.subTest(role=role, final=final):
                budget = RuntimeBudget()
                for attempt in range(1, limit + 1):
                    self.assertEqual(await budget.reserve(role, final=final), attempt)
                with self.assertRaises(BudgetExceeded):
                    await budget.reserve(role, final=final)
                self.assertEqual(budget.used, limit)

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

    async def test_measurement_preserves_role_reservations(self):
        for role, final, limit in [
            ("decision", False, 20),
            ("decision", True, 2),
            ("advisor", False, 2),
            ("examiner", False, 4),
        ]:
            with self.subTest(role=role, final=final):
                budget = RuntimeBudget(measurement=True)
                for attempt in range(1, limit + 1):
                    self.assertEqual(await budget.reserve(role, final=final), attempt)
                with self.assertRaises(BudgetExceeded):
                    await budget.reserve(role, final=final)

    async def test_measurement_stops_after_forty_calls(self):
        budget = RuntimeBudget(measurement=True)
        roles = (
            [("decision", False)] * 20
            + [("advisor", False)] * 2
            + [
                (role, False)
                for role in ("examiner", "founder", "customer", "landlord_advocate")
                for _ in range(4)
            ]
            + [("decision", True)] * 2
        )
        for attempt, (role, final) in enumerate(roles, 1):
            self.assertEqual(await budget.reserve(role, final=final), attempt)
        with self.assertRaises(BudgetExceeded):
            await budget.reserve("decision", final=True)
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
        with patch("app.agentic.budget.monotonic", return_value=100):
            budget = RuntimeBudget({"active_seconds": 599}, measurement=True)
            budget.schema_chars = 10000
            self.assertEqual(await budget.reserve("decision", input_chars=350000), 1)
            resumed = RuntimeBudget(budget.snapshot(), measurement=True)
            self.assertEqual(resumed.used, 1)
            self.assertEqual(resumed.totals(), (180000, 0))
            self.assertEqual(resumed.active_seconds, 599)
            with self.assertRaises(BudgetExceeded):
                await resumed.reserve("decision", input_chars=2)
        with patch("app.agentic.budget.monotonic", return_value=101):
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
        roles = ["examiner", "founder", "customer", "landlord_advocate"]
        reservations = [await budget.claim_output(4000, role=role) for role in roles]
        self.assertEqual(reservations, [4000] * 4)
        extra = await budget.claim_output(4000, role="examiner")
        self.assertEqual(extra, 1500)
        self.assertLessEqual(budget.pending_output, budget.output_limit)
        with self.assertRaises(BudgetExceeded):
            await budget.claim_output(1, role="examiner")
        await budget.release_output(extra, role="examiner")
        for role, reserved in zip(roles, reservations, strict=True):
            await budget.release_output(reserved, role=role)
        self.assertEqual(budget.pending_output, 0)


if __name__ == "__main__":
    unittest.main()

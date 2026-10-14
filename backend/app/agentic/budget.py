"""도구 루프의 호출·토큰·활성 시간 예산은 질문 재개에도 누적합니다."""

import math
from time import monotonic

from app.llm.budget import FINAL_RESERVE, BudgetExceeded, LLMBudget


class RuntimeBudget(LLMBudget):
    def __init__(self, saved=None, on_change=None, *, measurement: bool = False):
        saved = saved or {}
        self.measurement = measurement
        self.input_limit = 400000
        self.output_limit = 60000
        self.seconds_limit = 600
        self.pending_output = 0
        super().__init__(
            limit=40,
            used=saved.get("used", 0),
            calls=saved.get("calls", []),
            on_change=on_change,
        )
        self.active_base = saved.get("active_seconds", 0)
        self.started = monotonic()
        self.schema_chars = 0

    @property
    def active_seconds(self):
        return self.active_base + monotonic() - self.started

    def totals(self):
        return (
            sum(
                c.get("input_tokens")
                if c.get("input_tokens") is not None
                else c.get("estimated_input", 0)
                for c in self.calls
            ),
            sum(c.get("output_tokens") or 0 for c in self.calls),
        )

    def snapshot(self):
        return super().snapshot() | {
            "measurement": self.measurement,
            "active_seconds": self.active_seconds,
            "input_tokens": self.totals()[0],
            "output_tokens": self.totals()[1],
        }

    async def reserve(self, role, *, final=False, input_chars=None):
        async with self._lock:
            phase = "final" if final else "draft"
            estimate = math.ceil(
                ((input_chars or 0) + (self.schema_chars if role != "advisor" else 0)) / 2
            )
            inputs, outputs = self.totals()
            evaluator = role in {"examiner", "founder", "customer", "landlord_advocate"}
            call_limit = self.limit - (FINAL_RESERVE if evaluator and not final else 0)
            if (
                self.used >= call_limit
                or inputs + estimate > self.input_limit
                or outputs >= self.output_limit
                or self.active_seconds >= self.seconds_limit
            ):
                raise BudgetExceeded()
            self.used += 1
            self.calls.append(
                {
                    "attempt": self.used,
                    "role": role,
                    "phase": phase,
                    "status": "started",
                    "input_chars": input_chars,
                    "estimated_input": estimate,
                    "input_tokens": None,
                    "output_tokens": None,
                }
            )
            await self._save()
            return self.used

    async def claim_output(self, requested=16000):
        if type(requested) is not int or not 0 < requested <= 16000:
            raise ValueError("출력 예약은 한 호출 출력 상한 안의 양수여야 합니다.")
        async with self._lock:
            available = self.output_limit - self.totals()[1] - self.pending_output
            if available <= 0:
                raise BudgetExceeded()
            reserved = min(requested, available)
            self.pending_output += reserved
            return reserved

    async def release_output(self, reserved):
        async with self._lock:
            self.pending_output -= reserved

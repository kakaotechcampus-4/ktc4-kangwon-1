"""도구 루프의 호출·토큰·활성 시간 예산은 질문 재개에도 누적합니다."""

import math
from time import monotonic

from app.llm.budget import BudgetExceeded, LLMBudget


class RuntimeBudget(LLMBudget):
    def __init__(self, saved=None, on_change=None, *, measurement: bool = False):
        saved = saved or {}
        self.measurement = measurement
        self.input_limit = 400000 if measurement else 160000
        self.output_limit = 60000 if measurement else 24000
        self.seconds_limit = 600 if measurement else 300
        super().__init__(
            limit=40 if measurement else 26,
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
            role_used = sum(
                c["role"] == role and c.get("phase", "draft") == phase for c in self.calls
            )
            role_limit = (
                4
                if role == "decision" and final
                else 8
                if role == "decision"
                else 2
                if role == "advisor"
                else 3
            )
            estimate = math.ceil(
                ((input_chars or 0) + (self.schema_chars if role == "decision" else 0)) / 2
            )
            inputs, outputs = self.totals()
            if (
                self.used >= self.limit
                or (not self.measurement and role_used >= role_limit)
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

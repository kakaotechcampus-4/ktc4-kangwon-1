"""도구 루프의 호출·토큰·활성 시간 예산은 질문 재개에도 누적합니다."""

import math
from collections import Counter
from time import monotonic

from app.llm.budget import FINAL_RESERVE, BudgetExceeded, LLMBudget

ROLE_LIMITS = {
    "decision": (230000, 36000, 22),
    "advisor": (10000, 2000, 2),
    "examiner": (40000, 5500, 4),
    "founder": (40000, 5500, 4),
    "customer": (40000, 5500, 4),
    "landlord_advocate": (40000, 5500, 4),
}
DECISION_PHASE_LIMITS = {False: (180000, 30000, 20), True: (50000, 6000, 2)}


class RuntimeBudget(LLMBudget):
    def __init__(self, saved=None, on_change=None, *, measurement: bool = False):
        saved = saved or {}
        self.measurement = measurement
        self.input_limit = 400000
        self.output_limit = 60000
        self.seconds_limit = 600
        self.pending_output = 0
        self.pending_by_role: Counter[tuple[str, bool]] = Counter()
        super().__init__(
            limit=40,
            used=saved.get("used", 0),
            calls=saved.get("calls", []),
            on_change=on_change,
        )
        self.active_base = saved.get("active_seconds", 0)
        self.started = monotonic()
        self.schema_chars = 0
        self.schema_chars_by_role: dict[str, int] = {}

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
            "role_usage": {role: self.usage(role) for role in ROLE_LIMITS},
        }

    def quota(self, role, final=False):
        if role not in ROLE_LIMITS:
            raise ValueError("모델 역할이 올바르지 않습니다.")
        return DECISION_PHASE_LIMITS[final] if role == "decision" else ROLE_LIMITS[role]

    def usage(self, role, final=None):
        calls = [
            call
            for call in self.calls
            if call.get("role", "decision") == role
            and (
                role != "decision"
                or final is None
                or (call.get("phase", "draft") == "final") == final
            )
        ]
        return (
            sum(
                call["input_tokens"]
                if call.get("input_tokens") is not None
                else call.get("estimated_input", 0)
                for call in calls
            ),
            sum(call.get("output_tokens") or 0 for call in calls),
            len(calls),
        )

    async def reserve(self, role, *, final=False, input_chars=None):
        if input_chars is not None and (type(input_chars) is not int or input_chars < 0):
            raise ValueError("입력 문자 수는 음수가 아닌 정수여야 합니다.")
        async with self._lock:
            phase = "final" if final else "draft"
            quota_input, quota_output, quota_calls = self.quota(role, final)
            role_inputs, role_outputs, role_calls = self.usage(role, final)
            schema_chars = self.schema_chars_by_role.get(
                role, self.schema_chars if role != "advisor" else 0
            )
            estimate = math.ceil(((input_chars or 0) + schema_chars) / 2)
            inputs, outputs = self.totals()
            slot = (role, final if role == "decision" else False)
            call_limit = self.limit - (0 if role == "decision" and final else FINAL_RESERVE)
            if (
                self.used >= call_limit
                or inputs + estimate > self.input_limit
                or outputs >= self.output_limit
                or outputs + self.pending_output > self.output_limit
                or role_calls >= quota_calls
                or role_inputs + estimate > quota_input
                or role_outputs >= quota_output
                or role_outputs + self.pending_by_role[slot] > quota_output
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

    async def claim_output(self, requested=16000, *, role="decision", final=False):
        if type(requested) is not int or not 0 < requested <= 16000:
            raise ValueError("출력 예약은 한 호출 출력 상한 안의 양수여야 합니다.")
        async with self._lock:
            _, quota_output, _ = self.quota(role, final)
            slot = (role, final if role == "decision" else False)
            available = min(
                self.output_limit - self.totals()[1] - self.pending_output,
                quota_output - self.usage(role, final)[1] - self.pending_by_role[slot],
            )
            if available <= 0:
                raise BudgetExceeded()
            reserved = min(requested, available)
            self.pending_output += reserved
            self.pending_by_role[slot] += reserved
            return reserved

    async def release_output(self, reserved, *, role="decision", final=False):
        async with self._lock:
            slot = (role, final if role == "decision" else False)
            if type(reserved) is not int or reserved <= 0 or self.pending_by_role[slot] < reserved:
                raise ValueError("출력 예약의 역할 또는 반환량이 다릅니다.")
            self.pending_output -= reserved
            self.pending_by_role[slot] -= reserved

from dataclasses import dataclass
from typing import Any, Protocol

from app.application.ports.slot import Slot


@dataclass
class LoopOutcome:
    status: str
    result: object = None
    question_session_id: str | None = None
    questions: list | None = None
    budget: dict | None = None


class DecisionLoop(Protocol):
    def begin(self, limitations: list[str], timings: dict[str, float]) -> None: ...
    def adopt_shared(self, shared: Any) -> None: ...
    async def run(self) -> LoopOutcome: ...
    async def review_and_finalize(self) -> LoopOutcome: ...
    async def save(self, status: str = ..., result_model: Any = None) -> None: ...


class DecisionEngine(Protocol):
    def budget(self, *, measurement: bool) -> Any: ...
    async def create(self, scope: Any, site: Any, **options: Any) -> DecisionLoop: ...
    async def validate_resume(self, scope: Any, answers: Any) -> Any: ...
    async def resume(self, scope: Any, site: Any, answers: Any, **options: Any) -> DecisionLoop: ...


decision: Slot[DecisionEngine] = Slot()

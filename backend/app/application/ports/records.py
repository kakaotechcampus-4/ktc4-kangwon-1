import json
from dataclasses import dataclass
from typing import Any

from app.domain.schemas import FactView, Site


@dataclass(frozen=True)
class AnswerGate:
    """답변 접수 전 409·422 판정에 필요한 최소 정보입니다.

    상태 한 글자를 보려고 저장된 리포트 전체를 꺼내 다시 검증하지 않기 위해
    상세 조회와 따로 둡니다.
    """

    status: str
    question_session_id: str | None
    fields: frozenset[str]


@dataclass(frozen=True)
class ResumeContext:
    """답변으로 재개할 때 필요한 자리와 실행 식별자입니다."""

    site: Site
    snapshot_id: str
    run_id: str


@dataclass(frozen=True)
class SnapshotFacts:
    """요청 스냅샷의 전체 fact입니다. 보고서가 인용했는지와 무관합니다."""

    snapshot_id: str | None
    facts: list[FactView]


@dataclass(frozen=True)
class ToolCallRecord:
    tool_call_id: str
    reply_text: str

    @property
    def reply(self) -> dict[str, Any]:
        return json.loads(self.reply_text)


@dataclass(frozen=True)
class ToolCallHistory:
    arguments_text: str
    reply_text: str


@dataclass(frozen=True)
class RunState:
    state: dict[str, Any]
    status: str


@dataclass(frozen=True)
class QuestionSession:
    question_session_id: str
    questions: list[dict[str, Any]]
    status: str


@dataclass(frozen=True)
class FactScope:
    industry_code: str | None
    status: str
    citable: bool


@dataclass(frozen=True)
class SpaceFitInput:
    fact_id: str
    industry_code: str | None
    source: str
    metric: str
    value: Any


@dataclass(frozen=True)
class SpaceAnswer:
    fact_id: str
    metric: str
    value: Any
    unit: str


@dataclass(frozen=True)
class ScoreSnapshot:
    score_snapshot_id: str
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class ItemScore:
    industry_code: str
    item: str
    status: str
    grade: int | None
    points: float | None
    fact_ids: list[str]


@dataclass(frozen=True)
class RawRow:
    raw_row_id: str
    value: Any


@dataclass(frozen=True)
class RawRowSource:
    value: Any
    source: str

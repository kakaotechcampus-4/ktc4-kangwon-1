"""공개 API가 돌려주는 응답 모양입니다."""

from typing import Any, Literal

from pydantic import BaseModel

from app.domain.schemas import AgentError, DecisionResult, FactView, RequestStatus, Schema, Text


class AcceptedAnalysis(BaseModel):
    request_id: str
    status: Literal["pending", "running"]


class AnalysisEvent(BaseModel):
    seq: int
    at: str
    stage: str
    event: str
    detail: dict[str, Any]


class AnalysisEvents(BaseModel):
    request_id: str
    status: str
    finished: bool
    events: list[AnalysisEvent]
    next_after: int


class StoredQuestions(BaseModel):
    question_session_id: str
    questions: list[dict[str, str]]
    status: str


class StoredAnalysis(BaseModel):
    """저장된 요청 한 건의 조회 응답입니다.

    DB 행을 그대로 흘려보내면 컬럼 이름이 곧 공개 계약이 되므로 여기에 적어 고정합니다.
    site·rendered는 화면이 불투명하게 쓰는 값이라 모양을 조이지 않습니다.
    """

    request_id: str
    input_address: str
    catalog_version: str | None
    radius_m: int | None
    status: RequestStatus
    created_at: str
    completed_at: str | None
    site: dict[str, Any] | None
    result: DecisionResult | None
    error: AgentError | None
    questions: StoredQuestions | None
    rendered: dict[str, Any] | None


class RequestFacts(Schema):
    request_id: Text
    snapshot_id: Text | None
    facts: list[FactView]

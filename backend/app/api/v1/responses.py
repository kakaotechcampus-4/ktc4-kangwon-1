"""조회 응답의 바깥 구조만 문서화하며 과거 저장 JSON은 그대로 보존합니다."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class AcceptedAnalysis(BaseModel):
    request_id: str
    status: Literal["running"]


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


class AnalysisDetail(BaseModel):
    # 저장 당시 스키마의 추가 필드를 삭제하거나 현재 업종 계약으로 재검증하지 않습니다.
    model_config = ConfigDict(extra="allow")
    request_id: str
    input_address: str
    catalog_version: str | None
    analysis_mode: str
    radius_m: int | None
    status: str
    created_at: str
    completed_at: str | None
    site: Any
    result: Any
    error: Any
    decision_failures: list[dict[str, Any]]
    questions: Any
    analyses: list[dict[str, Any]]
    supplements: list[dict[str, Any]]
    map_status: str | None
    map_observation: Any
    evaluation: dict[str, Any] | None = None
    deliberation: dict[str, Any] | None = None

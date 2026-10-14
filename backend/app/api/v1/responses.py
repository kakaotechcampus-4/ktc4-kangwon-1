"""단일 실행의 수락·진행 이벤트 응답입니다."""

from typing import Any, Literal

from pydantic import BaseModel


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

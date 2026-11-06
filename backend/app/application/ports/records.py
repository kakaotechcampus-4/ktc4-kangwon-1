from dataclasses import dataclass

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

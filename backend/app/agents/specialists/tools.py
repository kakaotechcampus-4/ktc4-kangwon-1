"""전문가 도구의 공통 실행 계약과 실패 시 원자료 요약입니다."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.evidence import scalar_records, validate_findings
from app.schemas import AgentAnalysis, AgentBrief, AnalysisTask, EvidenceRef, Finding


class ToolArgumentError(ValueError):
    """모델이 선택한 도구의 인자 오류입니다. 실행 결과 계약 오류와 구분합니다."""


@dataclass(frozen=True)
class SpecialistTool:
    definition: dict
    execute: Callable[[dict], Awaitable[dict]]


def fallback_brief(task: AnalysisTask, analysis: AgentAnalysis) -> AgentBrief:
    findings: list[Finding] = []
    records = scalar_records(analysis.data, analysis.agent_id)
    scores = sorted(
        (r for r in records if r["path"].endswith("/score") and type(r["value"]) in {int, float}),
        key=lambda r: r["value"],
    )
    selected = {r["path"]: r for r in [*scores[:4], *scores[-4:], *records]}
    for item in selected.values():
        if type(item["value"]) not in {int, float} or len(findings) >= 8:
            continue
        finding = Finding(
            claim="원자료 값 {0}",
            signal="context",
            industry_code=item["industry_code"],
            evidence=[EvidenceRef(path=item["path"])],
        )
        findings.extend(
            validate_findings([finding], agent_id=analysis.agent_id, data=analysis.data)[0]
        )
    return AgentBrief(
        request_id=task.request_id,
        agent_id=analysis.agent_id,
        source="fallback",
        headline="검증된 원자료 요약",
        findings=findings,
        limitations=["전문가 브리핑 없이 요약표로 판단합니다.", *analysis.warnings],
    )

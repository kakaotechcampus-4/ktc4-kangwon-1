"""전문가 도구의 공통 실행 계약과 실패 시 원자료 요약입니다."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import ValidationError, create_model

from app.evidence import SourceIndex, validate_findings
from app.schemas import AgentAnalysis, AgentBrief, AnalysisTask, EvidenceRef, Finding, Schema


class ToolArgumentError(ValueError):
    """모델이 선택한 도구의 인자 오류입니다. 실행 결과 계약 오류와 구분합니다."""


@dataclass(frozen=True)
class SpecialistTool:
    definition: dict
    execute: Callable[[dict], Awaitable[dict]]


def fallback_brief(task: AnalysisTask, analysis: AgentAnalysis) -> AgentBrief:
    findings: list[Finding] = []
    index = SourceIndex.build(analysis.data, analysis.agent_id)
    records = index.records
    scores = sorted(
        (r for r in records if r.path.endswith("/score") and type(r.value) in {int, float}),
        key=lambda r: r.value if isinstance(r.value, (int, float)) else 0,
    )
    selected = {r.path: r for r in [*scores[:4], *scores[-4:], *records]}
    for item in selected.values():
        if type(item.value) not in {int, float} or len(findings) >= 8:
            continue
        finding = Finding(
            claim="원자료 값 {0}",
            signal="context",
            industry_code=item.owner,
            evidence=[EvidenceRef(path=item.path)],
        )
        findings.extend(
            validate_findings(
                [finding], agent_id=analysis.agent_id, data=analysis.data, index=index
            )[0]
        )
    return AgentBrief(
        request_id=task.request_id,
        agent_id=analysis.agent_id,
        source="fallback",
        headline="검증된 원자료 요약",
        findings=findings,
        limitations=["전문가 브리핑 없이 요약표로 판단합니다.", *analysis.warnings],
    )


def _tool(name, description, parameters, execute):
    arguments = create_model(name + "Arguments", __base__=Schema, **parameters)

    async def validated(raw):
        try:
            parsed = arguments.model_validate(raw).model_dump()
        except ValidationError:
            raise ToolArgumentError("도구 인자가 올바르지 않습니다.") from None
        return await execute(parsed)

    return SpecialistTool(
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": arguments.model_json_schema(),
            },
        },
        validated,
    )

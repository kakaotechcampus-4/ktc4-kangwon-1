"""분석 결과를 모아 검증된 최종 판단을 반환합니다."""

import re
from collections.abc import Callable
from importlib.resources import files

from app.schemas import AGENT_IDS, AgentAnalysis, DecisionContent, DecisionRequest, DecisionResult

from .llm import generate_decision


def analyze(
    request: DecisionRequest | dict,
    *,
    generate: Callable[[str, str], DecisionContent | dict] | None = None,
) -> DecisionResult:
    """입력을 검증하고 모델 판단을 리포트용 결과로 반환합니다."""
    request = DecisionRequest.model_validate(request)
    sources = {item.agent_id: item for item in request.analyses}
    available = {
        key: item for key, item in sources.items()
        if item.status in {"ok", "partial"}
    }
    limitations = []

    for agent_id in AGENT_IDS:
        source = sources.get(agent_id)
        if source is None:
            limitations.append(f"분석 누락: {agent_id}")
        elif source.status == "error":
            limitations.append(f"분석 실패: {agent_id} ({source.error.message})")
        elif source.status == "no_data":
            limitations.append(f"자료 없음: {agent_id}")
        else:
            if source.status == "partial":
                limitations.append(f"부분 분석: {agent_id}")
            limitations.extend(f"{agent_id}: {warning}" for warning in source.warnings)

    scopes = {(item.scope.area, item.scope.period) for item in available.values()}
    if len(scopes) > 1:
        limitations.append("분석 지역 또는 기준 기간이 달라 지표를 직접 비교하기 어렵습니다.")

    if available:
        prompt = files(__package__).joinpath("prompt.md").read_text(encoding="utf-8")
        content = DecisionContent.model_validate(
            (generate or generate_decision)(prompt, request.model_dump_json())
        )
        _validate_evidence(content, available)
    else:
        content = DecisionContent(
            status="no_data",
            summary="사용 가능한 분석 결과가 없어 업종 판단을 보류했습니다.",
            recommendations=[],
            not_recommended=[],
            limitations=["분석 자료를 확보한 뒤 다시 요청해 주세요."],
        )

    # 요청 정보와 자료 부족 표시는 모델이 변경하지 못하게 붙입니다.
    payload = content.model_dump()
    if content.status == "ok" and limitations:
        payload["status"] = "partial"
    payload["limitations"] = list(dict.fromkeys(limitations + content.limitations))
    payload["recommendations"] = sorted(payload["recommendations"], key=lambda x: -x["score"])
    payload["not_recommended"] = sorted(payload["not_recommended"], key=lambda x: x["score"])
    return DecisionResult(
        schema_version="1.0",
        agent_id="decision",
        request_id=request.request_id,
        address=request.address,
        source_analyses=request.analyses,
        **payload,
    )


def _validate_evidence(content: DecisionContent, sources: dict[str, AgentAnalysis]) -> None:
    """근거가 사용 가능한 자료의 실제 필드를 가리키는지 확인합니다."""
    for item in content.recommendations + content.not_recommended:
        for evidence in item.evidence:
            if evidence.agent_id not in sources:
                raise ValueError(f"사용할 수 없는 분석을 인용했습니다: {evidence.agent_id}")
            path = evidence.path
            if not path.startswith("/") or re.search(r"~(?![01])", path):
                raise ValueError(f"근거 경로 형식이 잘못되었습니다: {path}")
            value = sources[evidence.agent_id].data
            try:
                for part in path[1:].split("/"):
                    key = part.replace("~1", "/").replace("~0", "~")
                    if isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
                        value = value[int(key)]
                    elif isinstance(value, dict):
                        value = value[key]
                    else:
                        raise KeyError(key)
            except (KeyError, IndexError, ValueError) as exc:
                raise ValueError(f"입력에 없는 근거입니다: {evidence.agent_id}{path}") from exc

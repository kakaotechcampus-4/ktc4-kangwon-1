"""분석 결과를 모아 검증된 최종 판단을 반환합니다."""

import inspect
import json
import re
from collections.abc import Awaitable, Callable
from importlib.resources import files
from typing import Any

from app.agents.floating_population.llm import SELECTABLE
from app.industries import lookup
from app.industries.catalog import INDUSTRIES, INDUSTRY_MAJORS
from app.schemas import AGENT_IDS, AgentAnalysis, DecisionContent, DecisionRequest, DecisionResult

from .llm import generate_decision

GenerateDecision = Callable[[str, str], DecisionContent | dict | Awaitable[DecisionContent | dict]]


async def analyze(
    request: DecisionRequest | dict,
    *,
    generate: GenerateDecision | None = None,
) -> DecisionResult:
    """입력을 검증하고 모델 판단을 리포트용 결과로 반환합니다."""
    request = DecisionRequest.model_validate(request)
    sources: dict[str, AgentAnalysis] = {item.agent_id: item for item in request.analyses}
    available = {key: item for key, item in sources.items() if item.status in {"ok", "partial"}}
    limitations = []

    for agent_id in AGENT_IDS:
        source = sources.get(agent_id)
        if source is None:
            limitations.append(f"분석 누락: {agent_id}")
        elif source.status == "error":
            detail = source.error.message if source.error else "사유 없음"
            limitations.append(f"분석 실패: {agent_id} ({detail})")
        elif source.status == "no_data":
            limitations.append(f"자료 없음: {agent_id}")
        else:
            if source.status == "partial":
                limitations.append(f"부분 분석: {agent_id}")
            limitations.extend(f"{agent_id}: {warning}" for warning in source.warnings)

    scopes = {
        (item.scope.area, item.scope.period)
        for item in available.values()
        if item.scope is not None
    }
    if len(scopes) > 1:
        limitations.append("분석 지역 또는 기준 기간이 달라 지표를 직접 비교하기 어렵습니다.")

    if available:
        prompt = files(__package__).joinpath("prompt.md").read_text(encoding="utf-8")
        prompt += "\n\n## 공통 중분류 목록 (코드 | 대분류 공식명 | 중분류 공식명)\n"
        prompt += "\n".join(
            f"{code} | {INDUSTRY_MAJORS[code][1]} | {name}" for code, name in INDUSTRIES.items()
        )
        produced = (generate or generate_decision)(prompt, _decision_input(request))
        if inspect.isawaitable(produced):
            produced = await produced
        content = DecisionContent.model_validate(produced)
        _validate_categories(content)
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


def _decision_input(request: DecisionRequest) -> str:
    """선별은 직렬화된 복사본에만 적용해 반환·저장용 원본과 배열 위치를 보존합니다."""
    payload = request.model_dump(mode="json")
    for source in payload["analyses"]:
        if source["agent_id"] != "floating_population":
            continue
        data = source["data"]
        selection = data.get("selection")
        if not isinstance(selection, dict) or selection.get("applied") is not True:
            continue
        included = selection.get("included")
        # 과거·자유 형식 자료의 선별 메타데이터가 불완전하면 원본을 전부 전달합니다.
        if not isinstance(included, list) or any(block not in SELECTABLE for block in included):
            continue
        for block in ("trade_areas", "trend", "radius_profile"):
            if block not in included:
                data.pop(block, None)
        if "population_raw" not in included and isinstance(data.get("population"), dict):
            for field in ("by_age", "by_time", "by_day"):
                data["population"].pop(field, None)
    return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def _validate_categories(content: DecisionContent) -> None:
    """기존 이름 조회로 코드를 확인하고 두 목록을 통틀어 중복을 거절합니다."""
    seen = set()
    for item in content.recommendations + content.not_recommended:
        industry = lookup.find_by_name(item.category.middle)
        if industry is None:
            raise ValueError(f"공통 목록에 없는 중분류 업종입니다: {item.category.middle}")
        if item.category.major != industry.major_name:
            raise ValueError(f"업종의 대분류가 일치하지 않습니다: {item.category.middle}")
        if industry.code in seen:
            raise ValueError(f"같은 중분류 업종을 여러 번 판단할 수 없습니다: {industry.code}")
        seen.add(industry.code)
        item.category.middle = industry.name


def _validate_evidence(content: DecisionContent, sources: dict[str, AgentAnalysis]) -> None:
    """근거가 사용 가능한 자료의 실제 필드를 가리키는지 확인합니다."""
    for item in content.recommendations + content.not_recommended:
        for evidence in item.evidence:
            if evidence.agent_id not in sources:
                raise ValueError(f"사용할 수 없는 분석을 인용했습니다: {evidence.agent_id}")
            path = evidence.path
            if not path.startswith("/") or re.search(r"~(?![01])", path):
                raise ValueError(f"근거 경로 형식이 잘못되었습니다: {path}")
            value: Any = sources[evidence.agent_id].data
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
            if (
                value is None
                or isinstance(value, str)
                and not value.strip()
                or isinstance(value, (list, dict))
                and not value
            ):
                raise ValueError(f"빈 자료는 근거로 사용할 수 없습니다: {evidence.agent_id}{path}")

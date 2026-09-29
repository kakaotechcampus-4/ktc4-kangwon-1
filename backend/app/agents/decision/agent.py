"""분석 결과를 모아 검증된 최종 판단을 반환합니다."""

import asyncio
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from difflib import get_close_matches
from importlib.resources import files
from typing import Any, cast

from app.agents.floating_population.selection import SELECTABLE
from app.industries import lookup
from app.industries.catalog import INDUSTRIES, INDUSTRY_MAJORS
from app.schemas import (
    AGENT_IDS,
    AgentAnalysis,
    ConsultPlan,
    DecisionContent,
    DecisionRequest,
    DecisionResult,
    LandlordAnswer,
    MapLookupPlan,
    MapObservation,
    QuestionField,
    QuestionPlan,
    Site,
    SupplementEvent,
    SupplementOperation,
    SupplementPlan,
)

from .evidence import index_paths, industry_catalog
from .llm import InvalidDecisionCategory, generate_decision, validate_content

GenerateDecision = Callable[
    [str, str],
    DecisionContent
    | SupplementPlan
    | QuestionPlan
    | MapLookupPlan
    | ConsultPlan
    | dict
    | Awaitable[
        DecisionContent | SupplementPlan | QuestionPlan | MapLookupPlan | ConsultPlan | dict
    ],
]


class DecisionContractError(ValueError):
    """모델이 만든 값 대신 코드가 정한 검증 위치와 사유만 공개합니다."""

    code = "DECISION_CONTRACT_INVALID"

    def __init__(self, field: str, reason: str):
        messages = {
            "invalid_category": "업종 코드 또는 명칭이 공통 업종표와 일치하지 않습니다.",
            "unknown_industry": "공통 목록에 없는 중분류 업종입니다.",
            "major_mismatch": "업종의 대분류가 일치하지 않습니다.",
            "duplicate_industry": "같은 중분류 업종을 여러 번 판단할 수 없습니다.",
            "source_unavailable": "사용할 수 없는 분석을 인용했습니다.",
            "evidence_path_invalid": "근거 경로 형식이 잘못되었습니다.",
            "evidence_not_found": "입력에 없는 근거입니다.",
            "evidence_empty": "빈 자료는 근거로 사용할 수 없습니다.",
            "evidence_industry_mismatch": "판단 업종과 근거 업종이 다릅니다.",
            "evidence_unavailable": "제외되거나 사용 불가능한 자료는 근거로 사용할 수 없습니다.",
        }
        super().__init__(messages[reason])
        self.diagnostics = {
            "stage": "decision_validation",
            "field": field,
            "reason": reason,
        }
        self.failures: list[dict[str, Any]] = []


async def analyze(
    request: DecisionRequest | dict,
    *,
    generate: GenerateDecision | None = None,
) -> DecisionResult:
    """입력을 검증하고 모델 판단을 리포트용 결과로 반환합니다."""
    result = await evaluate(request, generate=generate)
    if not isinstance(result, DecisionResult):
        raise ValueError("최종 결과가 필요한 단계에서는 보완을 요청할 수 없습니다.")
    return result


async def evaluate(
    request: DecisionRequest | dict,
    *,
    generate: GenerateDecision | None = None,
    operations: list[SupplementOperation] | None = None,
    feedback: list[str] | None = None,
    supplement_context: list[SupplementEvent] | None = None,
    question_fields: list[QuestionField] | None = None,
    user_answers: list[LandlordAnswer] | None = None,
    site: Site | None = None,
    allow_map_lookup: bool = False,
    deliberation: dict | None = None,
) -> DecisionResult | SupplementPlan | QuestionPlan | MapLookupPlan | ConsultPlan:
    """보완 가능 작업이 있을 때만 내부 보완 요청을 허용합니다."""
    request = DecisionRequest.model_validate(request)
    sources: dict[str, AgentAnalysis] = {item.agent_id: item for item in request.analyses}
    available = {key: item for key, item in sources.items() if item.status in {"ok", "partial"}}
    observation = request.map_observation
    answers = [LandlordAnswer.model_validate(a) for a in user_answers or []]
    allowed_questions = set(question_fields or []) - {a.field for a in answers}
    limitations = _collect_limitations(sources, available, observation, answers, feedback)
    if deliberation is not None:
        limitations.extend(
            message
            for item in [*deliberation["briefs"], *deliberation["answers"]]
            for message in item.limitations
        )

    if available or operations or deliberation is not None:
        prompt, payload, visible = await asyncio.to_thread(
            _build_prompt,
            request,
            operations,
            allowed_questions,
            answers,
            site,
            feedback,
            supplement_context,
            allow_map_lookup,
            deliberation,
        )
        failures: list[dict[str, Any]] = []
        for attempt in range(2):
            content = None
            try:
                produced = (generate or generate_decision)(
                    prompt, json.dumps(payload, ensure_ascii=False)
                )
                if inspect.isawaitable(produced):
                    produced = await produced
                outcome = _parse_outcome(
                    produced,
                    final_only=bool(attempt),
                    operations=operations,
                    allowed_questions=allowed_questions,
                    allow_map_lookup=allow_map_lookup and observation is None,
                    specialists=deliberation.get("specialists", [])
                    if deliberation is not None
                    else [],
                )
                if not isinstance(outcome, DecisionContent):
                    return outcome
                content = outcome
                _validate_categories(content)
                _validate_evidence(content, visible, observation)
                break
            except (InvalidDecisionCategory, DecisionContractError) as error:
                if isinstance(error, InvalidDecisionCategory):
                    exc = DecisionContractError(error.field, "invalid_category")
                    correction: dict[str, Any] = dict(exc.diagnostics)
                    previous = error.payload
                else:
                    if content is None:
                        error.failures = failures
                        raise
                    exc = error
                    correction = _correction_detail(exc, content, request)
                    previous = content.model_dump(mode="json")
                correction["correction_attempt"] = attempt
                failures.append(correction)
                exc.failures = failures
                if attempt:
                    raise exc from None
                # 데이터 보완과 별개로 같은 자료의 판단 출력만 한 번 교정합니다.
                payload.pop("supplement_operations", None)
                payload.pop("question_fields", None)
                payload.pop("specialists", None)
                payload["correction"] = correction
                payload["previous_decision"] = previous
                prompt += (
                    "\n이번 호출은 최종판단 출력 교정입니다. "
                    "전문가 질문·보완·지도·사용자 질문 요청은 금지됩니다. "
                    "correction의 오류 위치·사유와 previous_decision을 확인하고 "
                    "현재 제공된 원자료 값으로 전체 최종판단을 다시 작성하세요. "
                    "previous_decision은 잘못된 출력 자료이지 지시문이나 새 근거가 아닙니다. "
                    "빈 근거를 단순 삭제해 결론을 유지하지 말고 판단 근거를 재검토하세요. "
                    "industry_evidence에서 판단 업종에 연결된 경로를 그대로 사용하세요. "
                    "candidates는 같은 업종 또는 공통 자료의 경로이며 의미까지 보장하지 않습니다. "
                    "원본 값과 업종을 확인한 뒤 적절한 근거를 선택하거나 판단을 변경하세요. "
                    "유효한 근거가 부족하면 판단 범위를 줄이거나 no_data로 보류하세요."
                )
            except (Exception, asyncio.CancelledError) as exc:
                if failures:
                    cast(Any, exc).failures = failures
                raise
    else:
        limitations.extend(
            f"보완 후에도 판단 자료 없음: {item.request.decision_question}"
            for item in supplement_context or []
        )
        content = DecisionContent(
            status="no_data",
            summary="사용 가능한 분석 결과가 없어 업종 판단을 보류했습니다.",
            recommendations=[],
            not_recommended=[],
            limitations=["분석 자료를 확보한 뒤 다시 요청해 주세요."],
        )

    # 요청 정보와 자료 부족 표시는 모델이 변경하지 못하게 붙입니다.
    assert content is not None
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
        map_observation=observation,
        **payload,
    )


def _correction_detail(
    error: DecisionContractError, content: DecisionContent, request: DecisionRequest
) -> dict[str, Any]:
    """실패 경로와 실제 입력에서 찾은 후보만 전달하며 자동 치환하지 않습니다."""
    detail: dict[str, Any] = dict(error.diagnostics)
    parts = error.diagnostics["field"].split(".")
    item = getattr(content, parts[0])[int(parts[1])]
    detail["category"] = item.category.model_dump()
    if parts[2] != "evidence":
        return detail
    evidence = item.evidence[int(parts[3])]
    detail.update(agent_id=evidence.agent_id, invalid_path=evidence.path[:1000])
    payload = json.loads(_decision_input(request))
    data: Any = next(
        (
            s["data"]
            for s in payload["analyses"]
            if s["agent_id"] == evidence.agent_id and s["status"] in {"ok", "partial"}
        ),
        {},
    )
    if evidence.agent_id == "map_analysis" and request.map_observation:
        data = request.map_observation.data.model_dump(mode="json")
    industry = lookup.find_by_name(item.category.middle)
    indexed = index_paths(data)
    if evidence.agent_id == "map_analysis":
        paths = [
            p
            for p in indexed
            if _valid_map_evidence(p, item.category.middle, request.map_observation)
        ]
    else:
        # 업종 자료가 있으면 공통 메타데이터보다 해당 업종을 우선합니다.
        paths = [p for p, code in indexed.items() if industry and code == industry.code]
        if not paths:
            paths = [p for p, code in indexed.items() if code is None]
    detail["candidates"] = [
        {"path": path} for path in get_close_matches(evidence.path, paths, n=8, cutoff=0.2)
    ]
    return detail


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
        removed = [f"/{block}" for block in SELECTABLE if block not in included]
        if "population_raw" not in included:
            removed.extend(f"/population/{field}" for field in ("by_age", "by_time", "by_day"))
        if isinstance(data.get("interpretation"), list):
            # 원본 근거 경로의 배열 위치는 유지하고 제외한 자료의 문장만 가립니다.
            data["interpretation"] = [
                None
                if isinstance(finding, dict)
                and isinstance(finding.get("path"), str)
                and any(
                    finding["path"] == path or finding["path"].startswith(path + "/")
                    for path in removed
                )
                else finding
                for finding in data["interpretation"]
            ]
    return json.dumps(payload, ensure_ascii=False, allow_nan=False)


def _validate_categories(content: DecisionContent) -> None:
    """기존 이름 조회로 코드를 확인하고 두 목록을 통틀어 중복을 거절합니다."""
    seen = set()
    for index, item in enumerate(content.recommendations + content.not_recommended):
        field = (
            f"recommendations.{index}.category"
            if index < len(content.recommendations)
            else f"not_recommended.{index - len(content.recommendations)}.category"
        )
        industry = lookup.find_by_name(item.category.middle)
        if industry is None:
            raise DecisionContractError(field + ".middle", "unknown_industry")
        if item.category.major != industry.major_name:
            raise DecisionContractError(field + ".major", "major_mismatch")
        if industry.code in seen:
            raise DecisionContractError(field + ".middle", "duplicate_industry")
        seen.add(industry.code)
        item.category.code = industry.code
        item.category.middle = industry.name


def _validate_evidence(
    content: DecisionContent,
    sources: dict[str, AgentAnalysis],
    observation: MapObservation | None = None,
) -> None:
    """근거가 사용 가능한 자료의 실제 필드를 가리키는지 확인합니다."""
    indexes = {agent_id: index_paths(source.data) for agent_id, source in sources.items()}
    for index, item in enumerate(content.recommendations + content.not_recommended):
        field = (
            f"recommendations.{index}"
            if index < len(content.recommendations)
            else f"not_recommended.{index - len(content.recommendations)}"
        )
        for evidence_index, evidence in enumerate(item.evidence):
            location = f"{field}.evidence.{evidence_index}"
            if evidence.agent_id == "map_analysis":
                if not _valid_map_evidence(evidence.path, item.category.middle, observation):
                    raise DecisionContractError(location + ".path", "source_unavailable")
                continue
            if evidence.agent_id not in sources:
                raise DecisionContractError(location + ".agent_id", "source_unavailable")
            path = evidence.path
            if not path.startswith("/") or re.search(r"~(?![01])", path):
                raise DecisionContractError(location + ".path", "evidence_path_invalid")
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
            except (KeyError, IndexError, ValueError):
                raise DecisionContractError(location + ".path", "evidence_not_found") from None
            if (
                value is None
                or isinstance(value, str)
                and not value.strip()
                or isinstance(value, (list, dict))
                and not value
            ):
                raise DecisionContractError(location + ".path", "evidence_empty")
            indexed = indexes[evidence.agent_id]
            if path not in indexed:
                raise DecisionContractError(location + ".path", "evidence_unavailable")
            owner = indexed[path]
            industry = lookup.find_by_name(item.category.middle)
            if owner is not None and (industry is None or owner != industry.code):
                raise DecisionContractError(location + ".path", "evidence_industry_mismatch")


def _valid_map_evidence(path: str, industry_name: str, observation: MapObservation | None) -> bool:
    """지도 근거는 정상 조회의 허용 필드와 일치 업종만 인용합니다."""
    from app.evidence import valid_map_path

    if observation is None or observation.status == "error":
        return False
    industry = lookup.find_by_name(industry_name)
    return bool(industry and valid_map_path(path, industry.code, observation.data.model_dump()))


def _collect_limitations(sources, available, observation, answers, feedback) -> list[str]:
    """원본의 실패·범위 차이·미확인 답변을 모읍니다."""
    limitations = list(feedback or [])
    if observation is not None:
        limitations.extend(observation.warnings)
        if observation.status in {"error", "partial"}:
            limitations.append("지도 조회·매핑 일부 또는 전체 실패: 확인된 자료만 사용합니다.")
    if answers:
        limitations.append(
            "임대인 답변은 사용자 제공 정보이며 시설·용도·입점 가능성을 검증한 자료가 아닙니다."
        )
        limitations.extend(
            f"사용자 정보 미확인: {a.field}" for a in answers if a.status != "answered"
        )

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

    return limitations


def _build_prompt(
    request,
    operations,
    allowed_questions,
    answers,
    site,
    feedback,
    supplement_context,
    allow_map_lookup,
    deliberation=None,
):
    """모델에 노출할 자료와 허용 작업만 구성합니다."""
    observation = request.map_observation
    prompt = files(__package__).joinpath("prompt.md").read_text(encoding="utf-8")
    prompt += "\n\n## 공통 중분류 목록 (코드 | 대분류 공식명 | 중분류 공식명)\n"
    prompt += "\n".join(
        f"{code} | {INDUSTRY_MAJORS[code][1]} | {name}" for code, name in INDUSTRIES.items()
    )
    if operations:
        prompt += (
            "\n'최종판단 전에 확인 도구를 먼저 검토' 규칙에 해당하면 "
            "다음 JSON 스키마로 보완을 요청합니다. "
            "일반 최종판단은 기존 DecisionContent 형식을 유지합니다.\n"
            + json.dumps(SupplementPlan.model_json_schema(), ensure_ascii=False)
        )
    else:
        prompt += "\n데이터 보완 요청은 금지됩니다."
    payload = json.loads(_decision_input(request))
    visible = {
        item["agent_id"]: AgentAnalysis.model_validate(item)
        for item in payload["analyses"]
        if item["status"] in {"ok", "partial"}
    }
    payload["industry_evidence"] = industry_catalog(
        {key: item.data for key, item in visible.items()}
    )
    if deliberation is not None:
        from app.llm.budget import current_scope

        from .context import build_context

        payload = build_context(
            request, briefs=deliberation["briefs"], answers=deliberation["answers"]
        )
        payload["analysis_mode"] = "multi_agent"
        payload["specialists"] = deliberation.get("specialists", [])
        payload["consult_round"] = deliberation.get("consult_round", 0)
        budget = current_scope()[0]
        payload["limits"] = {
            "remaining_consult_rounds": max(0, 2 - payload["consult_round"]),
            "remaining_model_calls": budget.limit - budget.used if budget else None,
            "reserved_final_calls": 2,
        }
        visible = {a.agent_id: a for a in request.analyses if a.status in {"ok", "partial"}}
        if payload["specialists"]:
            prompt += "\n멀티에이전트 모드: 부족한 정보는 ask_specialists로 전문가에게 묻습니다.\n"
            prompt += json.dumps(ConsultPlan.model_json_schema(), ensure_ascii=False)
        else:
            prompt += "\n전문가 추가 질문은 금지됩니다. 현재 자료로 판단하세요."
    if allow_map_lookup and observation is None:
        prompt += (
            "\n위 확인 도구 규칙에 해당하면 다음 JSON으로 지도 조회를 요청합니다:\n"
            + json.dumps(MapLookupPlan.model_json_schema(), ensure_ascii=False)
        )
    elif deliberation is not None:
        prompt += "\n직접 map_lookup은 금지됩니다. 지도 확인은 등록된 전문가에게만 요청하세요."
    else:
        prompt += "\n지도 추가 조회는 금지됩니다."
    if allowed_questions:
        prompt += (
            "\n위 확인 도구 규칙에 해당하면 허용 항목으로 질문합니다. JSON 스키마:\n"
            + json.dumps(QuestionPlan.model_json_schema(), ensure_ascii=False)
        )
        payload["question_fields"] = sorted(allowed_questions)
    else:
        prompt += (
            "\n사용자 질문은 금지됩니다. 허용된 전문가 질문·데이터 보완·지도 조회가 없으면 "
            "최종판단 또는 no_data를 반환하세요."
        )
    if answers:
        payload["user_answers"] = [a.model_dump(mode="json") for a in answers]
    if site is not None:
        payload["site"] = Site.model_validate(site).model_dump(mode="json")
    if operations:
        payload["supplement_operations"] = [item.model_dump() for item in operations]
    if feedback:
        payload["supplement_feedback"] = feedback
    if supplement_context:
        payload["supplement_context"] = [
            item.model_dump(mode="json", exclude={"analysis"}) for item in supplement_context
        ]
    return prompt, payload, visible


def _parse_outcome(
    produced, *, final_only, operations, allowed_questions, allow_map_lookup, specialists=()
):
    """모델의 행동을 한 번 구분하고 현재 허용 범위를 검증합니다."""
    action = (
        produced.get("action") if isinstance(produced, dict) else getattr(produced, "action", None)
    )
    if action in {"map_lookup", "ask_user", "supplement", "ask_specialists"} and final_only:
        raise ValueError("교정 단계에서는 최종판단만 허용합니다.")
    if action == "ask_specialists":
        # 같은 전문가에게 겹친 질문이나 허용되지 않은 전문가는 요청 전체를 실패시키지 않고
        # 전문가별 첫 질문만 남깁니다. 남는 질문이 없으면 계약 오류입니다.
        raw = produced if isinstance(produced, dict) else produced.model_dump(mode="json")
        queries, seen = [], set()
        for query in raw.get("queries") or []:
            agent_id = query.get("agent_id") if isinstance(query, dict) else None
            if agent_id in specialists and agent_id not in seen:
                seen.add(agent_id)
                queries.append(query)
        if not queries:
            raise ValueError("현재 단계에서 해당 전문가에게 질문할 수 없습니다.")
        return ConsultPlan.model_validate({**raw, "queries": queries[:3]})
    if action == "map_lookup":
        if not allow_map_lookup:
            raise ValueError("현재 단계에서는 지도 조회를 요청할 수 없습니다.")
        return MapLookupPlan.model_validate(produced)
    if action == "ask_user":
        questions = QuestionPlan.model_validate(produced)
        if not allowed_questions or not {q.field for q in questions.questions} <= allowed_questions:
            raise ValueError("현재 단계에서는 해당 사용자 질문을 허용하지 않습니다.")
        return questions
    if action == "supplement":
        if not operations:
            raise ValueError("현재 단계에서는 보완 요청을 허용하지 않습니다.")
        return SupplementPlan.model_validate(produced)
    return validate_content(produced)

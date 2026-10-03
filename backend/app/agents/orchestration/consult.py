"""전문가 도구를 기존 읽기·보완·지도 실행에 연결합니다."""

from typing import Annotated, Any, Literal, TypedDict

from pydantic import Field

from app.agents.orchestration.constants import DEFAULT_AGENT_TIMEOUT
from app.agents.specialists.facts import build_facts
from app.agents.specialists.tools import SpecialistTool, _tool
from app.evidence import MAP_AGENT_ID, SourceIndex
from app.schemas import (
    AgentAnalysis,
    IndustryCode,
    MapObservation,
    MapQuery,
    SupplementEvent,
    SupplementPlan,
    SupplementRequest,
    Text,
)

from .map_tools import _map_tools
from .map_tools import map_adoptable as map_adoptable
from .map_tools import query_key as query_key
from .supplement import execute_supplement


class SpecialistChanges(TypedDict, total=False):
    analysis: AgentAnalysis
    feedback: list[str]
    supplement_context: list[SupplementEvent]
    map_observation: MapObservation
    map_queries: list[MapQuery]


def merge_specialist_changes(state, changes: list[SpecialistChanges]) -> dict:
    """병렬 전문가가 갱신한 자기 자료만 합치고 공통 피드백은 모두 보존합니다."""
    result: dict[str, Any] = {}
    replaced = {
        change["analysis"].agent_id: change["analysis"]
        for change in changes
        if "analysis" in change
    }
    if replaced:
        result["analyses"] = [replaced.get(item.agent_id, item) for item in state["analyses"]]
    feedback = [item for change in changes for item in change.get("feedback", [])]
    if feedback:
        result["feedback"] = [*state.get("feedback", []), *feedback]
    events = [item for change in changes for item in change.get("supplement_context", [])]
    if events:
        result["supplement_context"] = [*state.get("supplement_context", []), *events]
    for change in changes:
        if "map_observation" in change:
            result["map_observation"] = change["map_observation"]
        if "map_queries" in change:
            result["map_queries"] = change["map_queries"]
    return result


def build_specialist_tools(
    task,
    agent_id,
    *,
    analyses,
    supplements,
    map_lookup,
    hooks,
    state,
    query=None,
    operation_timeout=DEFAULT_AGENT_TIMEOUT,
) -> tuple[dict[str, SpecialistTool], SpecialistChanges]:
    """자료 소유자는 고정하고 모델이 요청·반경을 변경하지 못하게 합니다."""
    changes: SpecialistChanges = {}
    analyses = list(analyses)
    if agent_id == MAP_AGENT_ID:
        tools = (
            _map_tools(task, map_lookup, hooks, dict(state), query, operation_timeout, changes)
            if map_lookup
            else {}
        )
        return tools, changes

    def source():
        return next(a for a in analyses if a.agent_id == agent_id)

    async def read(arguments, *, name):
        data = source().data
        index = SourceIndex.build(data)
        records = list(index.records)
        all_records = records
        codes = arguments.get("codes", [arguments["code"]] if "code" in arguments else [])
        if codes:
            records = [r for r in records if r.owner in codes]
        if name == "get_summary":
            records = [
                r
                for r in records
                if not any(
                    f"/{key}/" in r.path
                    for key in ("by_age", "by_time", "by_day", "quarters", "trade_areas")
                )
            ]
        elif name == "get_trend":
            points = data.get("trend", {}).get("quarters", [])
            indices = range(max(0, len(points) - arguments["quarters"]), len(points))
            prefixes = [f"/trend/quarters/{i}/" for i in indices]
            records = [r for r in records if any(r.path.startswith(p) for p in prefixes)]
        elif name == "get_time_profile":
            block = "population" if arguments["segment"] == "floating" else arguments["segment"]
            records = [
                r
                for r in records
                if r.path.startswith(f"/{block}/")
                and any(s in r.path for s in ("time", "peak", "unit"))
            ]
        elif name == "compare_seoul":
            records = [
                r
                for r in records
                if "/benchmark/" in r.path and r.path.rsplit("/", 1)[-1] == arguments["metric"]
            ]
        elif name == "get_radius_breakdown":
            records = [r for r in records if r.path.startswith("/by_radius/")]
            radius_paths = {"/".join(r.path.split("/")[:3]) + "/radius_m" for r in records}
            records.extend(r for r in all_records if r.path in radius_paths)
        elif name == "get_district_specialization":
            records = [
                r
                for r in records
                if r.path.startswith(("/district_", "/by_middle/"))
                and ("district" in r.path or r.path.endswith("/code"))
            ]
        return {
            "facts": build_facts(SourceIndex(index.owners, tuple(records), index.radii)),
            "scope": source().scope.model_dump() if source().scope else None,
            "warnings": source().warnings,
            "available": bool(records),
        }

    codes_field = (Annotated[list[IndustryCode], Field(min_length=1, max_length=5)], ...)
    definitions: dict[str, dict[str, Any]] = {
        "floating_population": {
            "get_summary": ("유동·상주·직장 인구 요약을 별도로 확인합니다.", {}),
            "get_trend": (
                "원본 위치를 유지한 분기 추세입니다.",
                {"quarters": (Annotated[int, Field(ge=1, le=12)], 4)},
            ),
            "get_time_profile": (
                "해당 인구의 제공된 시간대만 조회합니다.",
                {"segment": (Literal["floating", "resident", "worker"], ...)},
            ),
            "compare_seoul": ("원자료의 서울 비교 지표입니다.", {"metric": (Text, ...)}),
        },
        "business_lifecycle": {
            "get_industry_metrics": ("지정 업종의 원본 지표와 경로입니다.", {"codes": codes_field}),
            "compare_industries": ("여러 업종의 계산된 값을 비교합니다.", {"codes": codes_field}),
        },
        "commercial_area": {
            "get_industry_counts": ("업종별 점포 수와 지표입니다.", {"codes": codes_field}),
            "get_radius_breakdown": (
                "기존 계산 결과의 반경별 업종 자료입니다.",
                {"code": (IndustryCode, ...)},
            ),
            "get_district_specialization": ("자치구 비교 자료입니다.", {}),
        },
    }
    result = {}
    for name, (description, arguments) in definitions[agent_id].items():

        async def execute(args, name=name):
            return await read(args, name=name)

        result[name] = _tool(name, description, arguments, execute)
    for tool in supplements:
        if tool.operation.agent_id != agent_id or not tool.eligible(
            task, source().model_copy(deep=True)
        ):
            continue
        name = tool.operation.operation
        if name not in {"fetch_quarter_details", "retry_lq_baseline"}:
            continue

        async def refresh(args, tool=tool):
            asked = SupplementRequest(
                agent_id=agent_id,
                operation=tool.operation.operation,
                decision_question=query.question if query else "브리핑에 필요한 지표 확인",
                missing_information=tool.operation.description,
                why_needed=query.why_needed if query else "자료 확인",
                expected_impact=query.expected_impact if query else "근거 보완",
            )
            updated, feedback, events = await execute_supplement(
                task,
                analyses,
                SupplementPlan(action="supplement", requests=[asked]),
                tools=[tool],
                on_event=hooks.on_supplement,
                operation_timeout=operation_timeout,
            )
            # 병렬 작업이 다른 전문가의 갱신을 덮어쓰지 않도록 자기 결과만 교체합니다.
            index = next(i for i, a in enumerate(analyses) if a.agent_id == agent_id)
            analyses[index] = next(a for a in updated if a.agent_id == agent_id)
            changes["analysis"] = analyses[index]
            changes.setdefault("supplement_context", []).extend(events)
            changes.setdefault("feedback", []).extend(feedback)
            payload = await read(args, name="get_industry_metrics")
            payload["adopted"] = any(e.adopted for e in events)
            return payload

        args = {"codes": codes_field} if name == "fetch_quarter_details" else {}
        result[name] = _tool(name, tool.operation.description, args, refresh)
    return result, changes

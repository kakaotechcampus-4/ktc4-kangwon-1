"""전문가 도구를 기존 읽기·보완·지도 실행에 연결합니다."""

from typing import Annotated, Any, Literal

from pydantic import Field, ValidationError, create_model

from app.agents.specialists.tools import SpecialistTool, ToolArgumentError
from app.evidence import MAP_AGENT_ID, map_citations, scalar_records
from app.schemas import (
    FacilityCode,
    IndustryCode,
    MapLookupPlan,
    MapObservation,
    MapQuery,
    Schema,
    SupplementPlan,
    SupplementRequest,
    Text,
)

from .map import execute_map_lookup
from .supplement import execute_supplement


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


def map_adoptable(previous: MapObservation | None, candidate: MapObservation) -> bool:
    """기존 정상 검색이나 업종별 동종 장소를 잃는 재조회는 채택하지 않습니다."""
    if previous is None or previous.status == "error":
        return True
    current = {query_key(q.request): q for q in candidate.data.queries.values()}
    return all(
        q.status != "ok"
        or (query_key(q.request) in current and current[query_key(q.request)].status == "ok")
        for q in previous.data.queries.values()
    ) and all(
        code in candidate.data.industries
        and set(group.place_ids) <= set(candidate.data.industries[code].place_ids)
        for code, group in previous.data.industries.items()
    )


def query_key(q: MapQuery) -> tuple:
    return q.kind, q.industry_code, q.facility_code, q.query


def build_specialist_tools(
    task,
    agent_id,
    *,
    analyses,
    supplements,
    map_lookup,
    hooks,
    context,
    query=None,
    operation_timeout=180.0,
) -> dict[str, SpecialistTool]:
    """자료 소유자는 고정하고 모델이 요청·반경을 변경하지 못하게 합니다."""
    if agent_id == MAP_AGENT_ID:
        return (
            _map_tools(task, map_lookup, hooks, context, query, operation_timeout)
            if map_lookup
            else {}
        )

    def source():
        return next(a for a in analyses if a.agent_id == agent_id)

    async def read(arguments, *, name):
        data = source().data
        records = scalar_records(data)
        all_records = records
        codes = arguments.get("codes", [arguments["code"]] if "code" in arguments else [])
        if codes:
            records = [r for r in records if r["industry_code"] in codes]
        if name == "get_summary":
            records = [
                r
                for r in records
                if not any(
                    f"/{key}/" in r["path"]
                    for key in ("by_age", "by_time", "by_day", "quarters", "trade_areas")
                )
            ]
        elif name == "get_trend":
            points = data.get("trend", {}).get("quarters", [])
            indices = range(max(0, len(points) - arguments["quarters"]), len(points))
            prefixes = [f"/trend/quarters/{i}/" for i in indices]
            records = [r for r in records if any(r["path"].startswith(p) for p in prefixes)]
        elif name == "get_time_profile":
            block = "population" if arguments["segment"] == "floating" else arguments["segment"]
            records = [
                r
                for r in records
                if r["path"].startswith(f"/{block}/")
                and any(s in r["path"] for s in ("time", "peak", "unit"))
            ]
        elif name == "compare_seoul":
            records = [
                r
                for r in records
                if "/benchmark/" in r["path"]
                and r["path"].rsplit("/", 1)[-1] == arguments["metric"]
            ]
        elif name == "get_radius_breakdown":
            records = [r for r in records if r["path"].startswith("/by_radius/")]
            radius_paths = {"/".join(r["path"].split("/")[:3]) + "/radius_m" for r in records}
            records.extend(r for r in all_records if r["path"] in radius_paths)
        elif name == "get_district_specialization":
            records = [
                r
                for r in records
                if r["path"].startswith(("/district_", "/by_middle/"))
                and ("district" in r["path"] or r["path"].endswith("/code"))
            ]
        return {
            "records": records,
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
            context.setdefault("supplement_context", []).extend(events)
            context.setdefault("feedback", []).extend(feedback)
            payload = await read(args, name="get_industry_metrics")
            payload["adopted"] = any(e.adopted for e in events)
            return payload

        args = {"codes": codes_field} if name == "fetch_quarter_details" else {}
        result[name] = _tool(name, tool.operation.description, args, refresh)
    return result


def _map_tools(task, lookup, hooks, context, question, timeout):
    def result_data():
        data = context["map_observation"].data.model_dump(mode="json")
        return {
            "data": data,
            "citations": map_citations(context["map_observation"].data),
            "match_summary": {
                key: {
                    "query": q["request"]["query"],
                    "industry_code": q["request"]["industry_code"],
                    **{
                        status: list(q["matches"].values()).count(status)
                        for status in ("same", "different", "unclear")
                    },
                }
                for key, q in data["queries"].items()
            },
        }

    async def search(args, *, kind):
        target = MapQuery(
            kind=kind,
            industry_code=args["code"] if kind == "industry" else None,
            facility_code=args["code"] if kind == "infrastructure" else None,
            query=args.get("query"),
            why_needed=question.why_needed if question else "주변 정보 확인",
            expected_impact=question.expected_impact if question else "후보 판단 검토",
        )
        previous = context.get("map_observation")
        # 미채택 조회도 상한에 포함하며 재개 시 저장된 계획에서 복원합니다.
        queries = list(
            context.get(
                "map_queries",
                [q.request for q in previous.data.queries.values()] if previous else [],
            )
        )
        existing = (
            next(
                (
                    q
                    for q in previous.data.queries.values()
                    if query_key(q.request) == query_key(target)
                ),
                None,
            )
            if previous
            else None
        )
        if existing and existing.status == "ok":
            return {**result_data(), "cached": True}
        if query_key(target) not in {query_key(q) for q in queries}:
            queries.append(target)
        if len(queries) > 8:
            return {"error": "요청당 지도 조회 대상은 최대 8개입니다."}
        plan = MapLookupPlan(action="map_lookup", queries=queries)
        if hooks.on_map_requested:
            await hooks.on_map_requested(task.model_copy(deep=True), plan.model_copy(deep=True))
        context["map_queries"] = queries
        raw = await execute_map_lookup(task, plan, lookup, timeout)
        observed = MapObservation.model_validate(raw)
        if (
            observed.request_id != task.request_id
            or observed.site != task.site
            or observed.radius_m != task.radius_m
            or [q.request for q in observed.data.queries.values()] != plan.unique_queries()
        ):
            raise ValueError("지도 요청과 관측이 일치하지 않습니다.")
        adopted = map_adoptable(previous, observed)
        if hooks.on_map_result:
            await hooks.on_map_result(observed.model_copy(deep=True), adopted)
        elif hooks.on_map_completed:
            await hooks.on_map_completed(observed.model_copy(deep=True))
        if adopted:
            context["map_observation"] = observed
        return {
            **result_data(),
            "adopted": adopted,
            **(
                {"error": "지도 추가 자료를 확보하지 못했습니다."}
                if not adopted or observed.status == "error"
                else {}
            ),
        }

    async def industry(args):
        return await search(args, kind="industry")

    async def facility(args):
        return await search(args, kind="infrastructure")

    return {
        "search_industry": _tool(
            "search_industry",
            "물어본 업종(code)의 주변 동종 점포를 일상어 검색어(query)로 찾습니다. "
            "같은 업종을 다른 검색어로 여러 번 부를 수 있습니다.",
            {
                "code": (IndustryCode, ...),
                "query": (Annotated[str, Field(min_length=1, max_length=50)], ...),
            },
            industry,
        ),
        "search_facility": _tool(
            "search_facility",
            "주변 교통·시설을 검색합니다.",
            {"code": (FacilityCode, ...)},
            facility,
        ),
    }

"""지도 전문가 도구의 조회·재사용·채택을 구성합니다."""

from typing import Annotated

from pydantic import Field

from app.agents.specialists.map_inputs import query_summary, selected_citations
from app.agents.specialists.tools import _tool
from app.schemas import FacilityCode, IndustryCode, MapLookupPlan, MapObservation, MapQuery

from .map import execute_map_lookup


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


def _map_tools(task, lookup, hooks, context, question, timeout, changes):
    def result_data(observed, target, adopted):
        query_id, query = next(
            (key, value)
            for key, value in observed.data.queries.items()
            if query_key(value.request) == query_key(target)
        )
        if not adopted or query.status == "error" or observed.status == "error":
            return {
                "query_id": query_id,
                "status": query.status,
                "error": query.error or "지도 추가 자료를 확보하지 못했습니다.",
                "adopted": False,
            }
        return {
            "query_id": query_id,
            **query_summary(query),
            "citations": selected_citations(observed.data, {target.industry_code or "_facility"}),
            "adopted": True,
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
            return {**result_data(previous, target, True), "cached": True}
        if query_key(target) not in {query_key(q) for q in queries}:
            queries.append(target)
        if len(queries) > 8:
            return {"error": "요청당 지도 조회 대상은 최대 8개입니다."}
        plan = MapLookupPlan(action="map_lookup", queries=queries)
        if hooks.on_map_requested:
            await hooks.on_map_requested(task.model_copy(deep=True), plan.model_copy(deep=True))
        context["map_queries"] = queries
        changes["map_queries"] = queries
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
            changes["map_observation"] = observed
        return result_data(observed, target, adopted)

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

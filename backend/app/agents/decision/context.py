"""원자료에서 계산 없이 판정용 값·경로만 추립니다."""

from app.evidence import (
    industry_catalog,
    rate_basis,
    resolve_pointer,
    scalar_records,
    valid_map_path,
    validate_findings,
)
from app.industries.catalog import INDUSTRIES
from app.schemas import AgentBrief, DecisionRequest, SpecialistAnswer

_METRICS = {
    "count",
    "lq",
    "lq_district",
    "score",
    "confidence",
    "latest_store_count",
    "recent_year_close_rate",
    "recent_year_net_change",
    "recent_year_net_change_rate",
    "period_open_count",
    "period_close_count",
    "observed_quarters",
}
_NEIGHBORHOOD = {
    "population",
    "resident",
    "worker",
    "population_summary",
    "benchmark",
    "type",
    "reliability",
    "restaurant_density",
    "diversity",
    "store_total",
    "radius_m",
    "rate_basis",
    "daily_average",
    "office_worker_share",
    "peak_hours",
    "trend",
}


def build_context(
    request: DecisionRequest, *, briefs: list[AgentBrief], answers: list[SpecialistAnswer]
) -> dict:
    sources: dict[str, dict] = {
        a.agent_id: a.data for a in request.analyses if a.status in {"ok", "partial"}
    }
    if request.map_observation and request.map_observation.status != "error":
        sources["map_analysis"] = request.map_observation.data.model_dump(mode="json")
    digest: dict[str, dict] = {
        code: {"code": code, "name": name, "metrics": []} for code, name in INDUSTRIES.items()
    }
    neighborhood = []
    for agent_id, data in sources.items():
        for record in scalar_records(data):
            owner = record.pop("industry_code")
            path = record["path"]
            entry = {"agent_id": agent_id, **record}
            if owner in digest and path.rsplit("/", 1)[-1] in _METRICS and "/quarters/" not in path:
                if path.startswith("/by_radius/"):
                    radius_path = "/".join(path.split("/")[:3]) + "/radius_m"
                    entry["radius_m"] = {
                        "path": radius_path,
                        "value": resolve_pointer(data, radius_path),
                    }
                digest[owner]["metrics"].append(entry)
            elif (
                owner is None
                and path.split("/")[1] in _NEIGHBORHOOD
                and not any(
                    f"/{block}/" in path for block in ("by_age", "by_time", "by_day", "quarters")
                )
            ):
                neighborhood.append(entry)
            elif agent_id == "map_analysis" and valid_map_path(path, owner, data):
                neighborhood.append(entry)
    safe_briefs: list[dict] = []
    safe_answers: list[dict] = []
    candidates: set[str] = set()
    for items, output in ((briefs, safe_briefs), (answers, safe_answers)):
        for item in items:
            agent_id = item.agent_id if isinstance(item, AgentBrief) else item.query.agent_id
            findings, warnings = validate_findings(
                item.findings, agent_id=agent_id, data=sources.get(agent_id, {})
            )
            payload = item.model_dump(
                mode="json", exclude={"analysis", "map_observation", "tool_calls"}
            )
            payload["findings"] = [f.model_dump(mode="json") for f in findings]
            payload["limitations"] = list(dict.fromkeys([*item.limitations, *warnings]))
            output.append(payload)
            candidates.update(f.industry_code for f in findings if f.industry_code)
    scores = sorted(
        (m["value"], code)
        for code, row in digest.items()
        for m in row["metrics"]
        if m["path"].endswith("/score") and type(m["value"]) in {int, float}
    )
    candidates.update(code for _, code in scores[:5] + scores[-5:])
    return {
        "request_id": request.request_id,
        "address": request.address,
        "sources": [
            {
                "agent_id": a.agent_id,
                "status": a.status,
                "scope": a.scope.model_dump() if a.scope else None,
                "warnings": a.warnings,
                "rate_basis": rate_basis(a.data),
                "metadata": a.data.get("metadata"),
            }
            for a in request.analyses
        ],
        "map_context": {
            "status": request.map_observation.status,
            "queried_at": request.map_observation.queried_at,
            "radius_m": request.map_observation.radius_m,
            "warnings": request.map_observation.warnings,
            "queries": {
                key: q.model_dump(mode="json", exclude={"place_ids"})
                for key, q in request.map_observation.data.queries.items()
            },
        }
        if request.map_observation
        else None,
        "industry_digest": list(digest.values()),
        "neighborhood": neighborhood,
        "briefs": safe_briefs,
        "answers": safe_answers,
        "industry_evidence": [
            row for row in industry_catalog(sources) if row["industry_code"] in candidates
        ],
    }

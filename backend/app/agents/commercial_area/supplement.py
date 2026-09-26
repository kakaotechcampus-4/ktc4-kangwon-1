"""주변 비교 조회만 재실행하고 원본과 구분된 LQ 근거를 추가합니다."""

import math
from datetime import UTC, datetime

from app.schemas import AgentAnalysis, AnalysisTask

from .client import StoreClient
from .config import Settings
from .metrics import _ratio_against, count_by_middle


def eligible(task: AnalysisTask, previous: AgentAnalysis, *, settings: Settings) -> bool:
    data = previous.model_dump()["data"]
    rows = data.get("by_middle")
    return (
        previous.agent_id == "commercial_area"
        and previous.request_id == task.request_id
        and previous.status in {"ok", "partial"}
        and previous.data.get("radius_m") == task.radius_m
        and previous.data.get("lq_retryable") is True
        and "supplement_lq" not in previous.data
        and type(data.get("store_total")) is int
        and data["store_total"] > 0
        and isinstance(rows, list)
        and bool(rows)
        and all(
            isinstance(row, dict)
            and isinstance(row.get("code"), str)
            and type(row.get("count")) is int
            and 0 <= row["count"] <= data["store_total"]
            for row in rows
        )
        and any(r > task.radius_m for r in settings.lq_radius_candidates)
        and (task.site.latitude, task.site.longitude) != (0, 0)
    )


async def supplement(
    task: AnalysisTask, previous: AgentAnalysis, *, settings: Settings
) -> AgentAnalysis:
    task = AnalysisTask.model_validate(task)
    previous = AgentAnalysis.model_validate(previous)
    if not eligible(task, previous, settings=settings):
        raise ValueError("주변 비교 보완의 실행 조건이 맞지 않습니다.")
    client = StoreClient(settings)
    candidates = tuple(r for r in settings.lq_radius_candidates if r > task.radius_m)
    try:
        stores, meta = await client.stores_in_radius_with_fallback(
            task.site.latitude,
            task.site.longitude,
            candidates,
            grid_m=settings.lq_cache_grid_m,
        )
    finally:
        await client.aclose()
    if meta.get("truncated") or not stores or meta.get("radius_m") not in candidates:
        raise ValueError("완전한 주변 비교 자료를 확보하지 못했습니다.")
    counts = dict(count_by_middle(stores))
    result = previous.model_copy(deep=True)
    data = previous.model_dump()["data"]
    result.data["supplement_lq"] = {
        "analysis_radius_m": task.radius_m,
        "baseline_radius_m": meta["radius_m"],
        "baseline_store_total": sum(counts.values()),
        "checked_at": datetime.now(UTC).isoformat(),
        "baseline_reference_date": meta.get("reference_date"),
        "from_cache": meta.get("from_cache"),
        "industries": [
            {
                "industry_id": row["code"],
                "lq": _ratio_against(
                    row["count"],
                    data["store_total"],
                    counts,
                    sum(counts.values()),
                    row["code"],
                ),
            }
            for row in data["by_middle"]
        ],
        "note": "최초 점포와 재조회한 주변 구성의 비교입니다. 원래 지표·요약은 보존했습니다.",
    }
    return AgentAnalysis.model_validate(result)


def accept(previous: AgentAnalysis, candidate: AgentAnalysis) -> bool:
    block = candidate.model_dump()["data"].get("supplement_lq")
    data = previous.model_dump()["data"]
    if not isinstance(block, dict) or block.get("analysis_radius_m") != data.get("radius_m"):
        return False
    baseline_radius = block.get("baseline_radius_m")
    if type(baseline_radius) is not int or baseline_radius <= data["radius_m"]:
        return False
    rows = block.get("industries")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return False
    if [row.get("industry_id") for row in rows] != [row["code"] for row in data["by_middle"]]:
        return False
    values = [row.get("lq") for row in rows]
    return any(value is not None for value in values) and all(
        value is None or (type(value) in (int, float) and math.isfinite(value) and value >= 0)
        for value in values
    )

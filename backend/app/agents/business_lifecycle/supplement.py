"""같은 상권·기간의 분기별 근거를 추가하고 최초 점수는 보존합니다."""

import math
from datetime import UTC, datetime

from app.industries.catalog import INDUSTRIES
from app.schemas import AgentAnalysis, AnalysisTask

from .client import get_recent_quarters
from .config import Settings
from .preprocess import preprocess_business_lifecycle_data


def eligible(task: AnalysisTask, previous: AgentAnalysis) -> bool:
    metadata = previous.model_dump()["data"].get("metadata")
    if (
        previous.agent_id != "business_lifecycle"
        or previous.request_id != task.request_id
        or previous.status not in {"ok", "partial"}
        or not isinstance(metadata, dict)
        or "supplement_quarters" in previous.data
        or (task.site.latitude, task.site.longitude) == (0, 0)
    ):
        return False
    count = metadata.get("quarter_count")
    if not isinstance(metadata.get("area_code"), str) or not metadata["area_code"]:
        return False
    if type(count) is not int or not 1 <= count <= 12:
        return False
    if not isinstance(metadata.get("base_quarter"), str):
        return False
    try:
        get_recent_quarters(metadata["base_quarter"], count)
    except (TypeError, ValueError):
        return False
    return True


async def supplement(
    task: AnalysisTask, previous: AgentAnalysis, *, settings: Settings
) -> AgentAnalysis:
    task = AnalysisTask.model_validate(task)
    previous = AgentAnalysis.model_validate(previous)
    if not eligible(task, previous):
        raise ValueError("분기 상세 보완의 실행 조건이 맞지 않습니다.")
    metadata = previous.model_dump()["data"]["metadata"]
    frame = await preprocess_business_lifecycle_data(
        area_code=metadata["area_code"],
        base_quarter=metadata["base_quarter"],
        quarter_count=metadata["quarter_count"],
        settings=settings,
    )
    result = previous.model_copy(deep=True)
    detail = {
        **frame.attrs["quarterly_detail"],
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
    originals = {
        row["industry_id"]: row
        for row in previous.model_dump()["data"].get("industries", [])
        if isinstance(row, dict) and isinstance(row.get("industry_id"), str)
    }
    for row in detail["industries"]:
        row["confidence"] = originals.get(row["industry_id"], {}).get("confidence", "none")
    result.data["supplement_quarters"] = detail
    return AgentAnalysis.model_validate(result)


def accept(previous: AgentAnalysis, candidate: AgentAnalysis) -> bool:
    block = candidate.model_dump()["data"].get("supplement_quarters")
    metadata = previous.model_dump()["data"].get("metadata", {})
    if not isinstance(block, dict) or block.get("area_code") != metadata.get("area_code"):
        return False
    quarters = get_recent_quarters(metadata["base_quarter"], metadata["quarter_count"])
    rows = block.get("industries")
    if block.get("quarters") != quarters or not isinstance(rows, list) or not rows:
        return False
    observed = False
    seen = set()
    originals = {
        row["industry_id"]: row
        for row in previous.model_dump()["data"].get("industries", [])
        if isinstance(row, dict) and isinstance(row.get("industry_id"), str)
    }
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("industry_id") not in INDUSTRIES
            or row["industry_id"] in seen
        ):
            return False
        seen.add(row["industry_id"])
        original = originals.get(row["industry_id"], {})
        metrics = original.get("metrics", {})
        if (
            row.get("confidence") != original.get("confidence", "none")
            or not isinstance(metrics, dict)
            or not {"period_open_count", "period_close_count"} <= metrics.keys()
        ):
            return False
        for field in ("store_counts", "opened_counts", "closed_counts", "close_rates"):
            values = row.get(field)
            if not isinstance(values, list) or len(values) != len(quarters):
                return False
            for value in values:
                if value is None:
                    continue
                if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                    return False
                if field != "close_rates" and not float(value).is_integer():
                    return False
                observed |= field in {"opened_counts", "closed_counts"}
        if not _matches_metrics(row, metrics):
            return False
    return observed


def _matches_metrics(row: dict, metrics: dict) -> bool:
    """결측은 합계에도 전파하고 최초 지표와 같은 기간으로 비교합니다."""

    def total(values):
        return None if any(value is None for value in values) else sum(values)

    calculated = {}
    for prefix, length in (("period", len(row["store_counts"])), ("recent_year", 4)):
        opened = total(row["opened_counts"][-length:])
        closed = total(row["closed_counts"][-length:])
        calculated.update(
            {
                f"{prefix}_open_count": opened,
                f"{prefix}_close_count": closed,
                f"{prefix}_net_change": None
                if opened is None or closed is None
                else opened - closed,
            }
        )
    stores = total(row["store_counts"])
    calculated["latest_store_count"] = row["store_counts"][-1]
    calculated["avg_store_count"] = (
        None if stores is None else round(stores / len(row["store_counts"]), 2)
    )
    for field, actual in calculated.items():
        if field in metrics and metrics[field] != actual:
            return False
    for stores, closed, rate in zip(
        row["store_counts"], row["closed_counts"], row["close_rates"], strict=True
    ):
        expected = (
            None
            if stores is None or closed is None or stores == 0
            else round(closed / stores * 100, 2)
        )
        if rate != expected:
            return False
    return True

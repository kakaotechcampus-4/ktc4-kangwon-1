"""완전한 소량 관측의 제한적 추정 기여를 실제 관측 점수와 분리합니다."""

import math

from app.agentic.scoring import WEIGHTS, valid
from app.agents.business_lifecycle.client import get_recent_quarters
from backtest.lifecycle_scores import grade_for, ratio_for
from backtest.rank_variant import s_grade
from backtest.temporal_score import metrics

S_ITEMS = ("S1", "S2", "S3", "S4")
EXPOSURE_GATE = 40.0
POWERS = {"linear": 1, "quadratic": 2}


def reliability(exposure: float, power: int) -> float:
    if not valid(exposure) or exposure < 0 or power not in POWERS.values():
        raise ValueError("양수 관측량과 고정 할인 방식이 필요합니다.")
    return min(1.0, exposure / EXPOSURE_GATE) ** power


def sparse_evidence(row: dict, data: dict, calibration: dict) -> dict:
    """라벨 없이 12분기 원문·서울 기준선·계산 가능한 비율을 확인합니다."""
    code = row["code"]
    if calibration["quarter_count"] != 12:
        raise ValueError("소량 관측 실험은 정확히12분기만 사용합니다.")
    city = calibration["lifecycle"].get(code)
    if not city:
        return {"eligible": {}, "reason": "unsupported_industry"}
    if not city.get("data_complete") or city.get("zero_filled_sources") != 0:
        raise ValueError("누락 보충 없는 완전한 서울 기준선이 필요합니다.")
    life = data.get("business_lifecycle", {})
    detail = data.get("lifecycle_quarterly", {})
    if life.get("metadata") != {
        "base_quarter": calibration["cutoff"],
        "quarter_count": calibration["quarter_count"],
    } or detail.get("quarters") != get_recent_quarters(calibration["cutoff"], 12):
        raise ValueError("소량 관측과 서울 기준선의 12분기 시점이 다릅니다.")
    if "business_lifecycle" in data.get("runtime_partial_sources", []):
        return {"eligible": {}, "reason": "partial_source"}
    raw = next((r for r in life.get("industries", []) if r["industry_id"] == code), {})
    series = next((r for r in detail.get("industries", []) if r["industry_id"] == code), {})
    if (
        not raw.get("data_complete")
        or raw.get("zero_filled_sources") != 0
        or series.get("zero_filled_sources") != 0
    ):
        return {"eligible": {}, "reason": "incomplete_or_filled_raw"}
    columns = [series.get(k, []) for k in ("store_counts", "opened_counts", "closed_counts")]
    if any(len(v) != 12 for v in columns):
        return {"eligible": {}, "reason": "incomplete_quarter_counts"}
    local = metrics(list(zip(*columns, strict=True)))
    local["avg_store_count"] = local["exposure"] / 12
    for name in (
        "avg_store_count",
        "recent_year_close_rate",
        "oldest_year_close_rate",
        "net_change_rate",
        "turnover_rate",
    ):
        actual, saved = local[name], raw.get("metrics", {}).get(name)
        if actual is None or saved is None:
            if actual is not saved:
                raise ValueError("건수와 저장 비율의 결측 상태가 다릅니다.")
        elif not math.isclose(actual, saved, rel_tol=1e-12, abs_tol=1e-12) and not (
            name == "avg_store_count" and round(actual, 2) == saved
        ):
            raise ValueError("소량 관측의 분기별 건수와 저장된 비율이 다릅니다.")
    eligible, skipped = {}, {}
    for name in S_ITEMS:
        if row["items"][name]["status"] != "unknown":
            continue
        total = local["exposure"]
        window = min(local["old_exposure"], local["recent_exposure"])
        exposure = min(total, window) if name in {"S2", "S4"} else total
        # 실제 관측량 문턱만 완화합니다. 분모가 없거나 원문이 불완전한 경우는 보완하지 않습니다.
        saved_total = raw["metrics"]["avg_store_count"] * 12
        blocked_by_gate = saved_total < EXPOSURE_GATE or (
            name in {"S2", "S4"} and window < EXPOSURE_GATE
        )
        if not blocked_by_gate or not 0 < exposure <= EXPOSURE_GATE:
            skipped[name] = "not_positive_low_exposure"
            continue
        try:
            ratio = ratio_for(name, local, city)
        except ValueError:
            skipped[name] = "undefined_rate_denominator"
            continue
        eligible[name] = {
            "ratio": ratio,
            "exposure": exposure,
            "total_exposure": total,
            "old_exposure": local["old_exposure"],
            "recent_exposure": local["recent_exposure"],
            "original_status": "unknown",
            "contribution_kind": "discounted_estimate_from_complete_low_exposure_counts",
        }
    return {"eligible": eligible, "skipped": skipped, "reason": "verified_complete_counts"}


def apply_sparse(base: dict, evidence: dict, *, power: int, curve: str) -> dict:
    if power not in POWERS.values() or curve not in {"stored", "ratio"}:
        raise ValueError("미리 고정한 두 할인 방식과 두 기준 점수식만 사용합니다.")
    estimates, details = {}, {}
    for name, value in evidence["eligible"].items():
        if name not in S_ITEMS or base["item_points"][name] is not None:
            raise ValueError("기존 관측 점수를 추정 기여로 덮을 수 없습니다.")
        grade = (
            grade_for(name, value["ratio"], continuous=True)
            if curve == "stored"
            else s_grade(name, value["ratio"], curve)
        )
        factor = reliability(value["exposure"], power)
        estimates[name] = WEIGHTS[name] * grade / 4 * factor
        details[name] = {**value, "undiscounted_grade": grade, "reliability": factor}
    estimated = sum(estimates.values())
    total = base["points"] + estimated
    return {
        **base,
        "points": total,
        "normalized": 80 * total / base["applicable"],
        "observed_points": base["points"],
        "estimated_points": estimated,
        "estimated_item_points": estimates,
        "estimate_evidence": details,
        "original_item_points_preserved": True,
    }

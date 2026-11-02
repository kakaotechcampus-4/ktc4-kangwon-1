"""관측 상태를 보존하며 개폐업 점수의 계산 근거와 고정 비교안을 계산합니다."""

import copy
import math
from bisect import bisect_right

from app.agentic.scoring import WEIGHTS, valid
from app.agents.business_lifecycle.baseline import (
    BASELINE_BASE_QUARTER,
    BASELINE_QUARTER_COUNT,
    SEOUL_INDUSTRY_LIFECYCLE_BASELINE,
)
from app.agents.business_lifecycle.client import get_recent_quarters
from backtest.followup import C_ITEMS
from backtest.missing_scores import MODEL_WEIGHT, RANK_DECIMALS

S_ITEMS = ("S1", "S2", "S3", "S4")
EXPOSURE_PRIOR = 40.0
LINEAR_SLOPE = 10.0
PROPOSALS = ("baseline", "continuous_S", "exposure_S", "continuous_exposure_S", "without_turnover")
METHODS = {
    "baseline": "기존 구간 등급",
    "continuous_S": "S 등급 경계를 연속 점수로 완화",
    "exposure_S": "관측량에 따라 S 극단 점수를 중간값으로 완화",
    "continuous_exposure_S": "연속 점수와 관측량 완화 결합",
    "without_turnover": "S3 제외 후 S1·S2·S4에 각 10점 배분",
    **{f"neutral_{name}": f"진단 대조: 관측 {name}만 중간 등급" for name in S_ITEMS},
    "neutral_S": "진단 대조: 관측 S 전체를 중간 등급",
}


def rates_from_counts(counts: dict) -> dict:
    stores, opened, closed = (counts[k] for k in ("stores", "opened", "closed"))
    if not (len(stores) == len(opened) == len(closed) == BASELINE_QUARTER_COUNT):
        raise ValueError("분기별 건수 길이가 고정 분석 기간과 다릅니다.")
    if any(type(v) is not int or v < 0 for series in (stores, opened, closed) for v in series):
        raise ValueError("분기별 건수에 실제 관측된 음이 아닌 정수가 필요합니다.")

    def rate(numerator, denominator):
        return round(numerator / denominator * 100, 2) if denominator > 0 else None

    return {
        "avg_store_count": sum(stores) / len(stores),
        "recent_year_close_rate": rate(sum(closed[-4:]), sum(stores[-4:])),
        "oldest_year_close_rate": rate(sum(closed[:4]), sum(stores[:4])),
        "net_change_rate": rate(sum(opened) - sum(closed), sum(stores)),
        "turnover_rate": rate(sum(opened) + sum(closed), sum(stores)),
    }


def ratio_for(name: str, local: dict, city: dict) -> float:
    if name in {"S1", "S3"}:
        key = "recent_year_close_rate" if name == "S1" else "turnover_rate"
        if not valid(local.get(key)) or not valid(city.get(key)) or city[key] <= 0:
            raise ValueError("관측 개폐업 비율의 분모를 검증할 수 없습니다.")
        return local[key] / city[key]
    if name == "S2":
        if (
            not valid(local.get("net_change_rate"))
            or not valid(city.get("turnover_rate"))
            or city["turnover_rate"] <= 0
        ):
            raise ValueError("점포 순증감 비교 분모를 검증할 수 없습니다.")
        return 1 + (local["net_change_rate"] - city["net_change_rate"]) / city["turnover_rate"]
    if name != "S4":
        raise ValueError("개폐업 항목이 아닙니다.")
    values = [
        local.get("recent_year_close_rate"),
        local.get("oldest_year_close_rate"),
        city.get("recent_year_close_rate"),
        city.get("oldest_year_close_rate"),
    ]
    if not all(map(valid, values)) or min(values[1:]) <= 0:
        raise ValueError("폐업률 추세의 과거 또는 서울 분모를 검증할 수 없습니다.")
    return (values[0] / values[1]) / (values[2] / values[3])


def grade_for(name: str, ratio: float, *, continuous=False) -> float:
    if name not in S_ITEMS or not valid(ratio):
        raise ValueError("개폐업 항목·비교 비율이 잘못되었습니다.")
    forward = (
        max(0.0, min(4.0, 2 + LINEAR_SLOPE * (ratio - 1)))
        if continuous
        else bisect_right([0.8, 0.95, 1.05, 1.2], ratio)
    )
    return forward if name == "S2" else 4 - forward


def exposure_for(name: str, counts: dict) -> int:
    stores = counts["stores"]
    if name == "S1":
        return sum(stores[-4:])
    if name == "S4":
        return min(sum(stores[:4]), sum(stores[-4:]))
    return sum(stores)


def trace_row(row: dict, data: dict) -> dict:
    observed = [name for name in S_ITEMS if row["items"][name]["status"] == "observed"]
    out = {
        "code": row["code"],
        "items": {name: dict(row["items"][name]) for name in S_ITEMS},
        "counts": None,
        "local_metrics": None,
        "city_baseline": None,
    }
    if not observed:
        return out
    city = SEOUL_INDUSTRY_LIFECYCLE_BASELINE.get(row["code"])
    life = data.get("business_lifecycle", {})
    raw = next((v for v in life.get("industries", []) if v["industry_id"] == row["code"]), {})
    detail = data.get("lifecycle_quarterly", {})
    quarterly = next(
        (v for v in detail.get("industries", []) if v["industry_id"] == row["code"]), {}
    )
    if (
        not city
        or not raw.get("data_complete")
        or "business_lifecycle" in data.get("runtime_partial_sources", [])
    ):
        raise ValueError("관측 개폐업 점수에 완전한 원천·서울 기준선이 필요합니다.")
    meta = life.get("metadata", {})
    if (
        meta.get("base_quarter") != BASELINE_BASE_QUARTER
        or meta.get("quarter_count") != BASELINE_QUARTER_COUNT
        or detail.get("quarters")
        != get_recent_quarters(BASELINE_BASE_QUARTER, BASELINE_QUARTER_COUNT)
    ):
        raise ValueError("개폐업 점수와 원자료·서울 기준선의 기간이 다릅니다.")
    counts = {
        key: list(quarterly.get(field, []))
        for key, field in (
            ("stores", "store_counts"),
            ("opened", "opened_counts"),
            ("closed", "closed_counts"),
        )
    }
    local = rates_from_counts(counts)
    for key, value in local.items():
        saved = raw.get("metrics", {}).get(key)
        if value is None or saved is None:
            if value is not saved:
                raise ValueError("원자료 재계산과 저장된 개폐업 결측 상태가 다릅니다.")
        elif not math.isclose(value, saved, rel_tol=1e-12, abs_tol=1e-12) and not (
            key == "avg_store_count" and round(value, 2) == saved
        ):
            raise ValueError("분기별 원자료 재계산과 저장된 개폐업 비율이 다릅니다.")
    if sum(counts["stores"]) < 40:
        raise ValueError("관측 개폐업 점수의 전체 노출량이 부족합니다.")
    out.update(
        counts=counts,
        local_metrics=local,
        city_baseline=dict(city),
        quarters=list(detail["quarters"]),
        zero_filled_sources=raw.get("zero_filled_sources", 0),
    )
    out["average_count_precision"] = {
        "stored": raw["metrics"]["avg_store_count"],
        "exact_from_counts": local["avg_store_count"],
        "legacy_rounded": raw["metrics"]["avg_store_count"] != local["avg_store_count"],
    }
    for name in observed:
        if name in {"S2", "S4"} and min(sum(counts["stores"][:4]), sum(counts["stores"][-4:])) < 40:
            raise ValueError("관측 개폐업 점수의 과거·최근 노출량이 부족합니다.")
        ratio = ratio_for(name, local, city)
        original = row["items"][name]
        grade = grade_for(name, ratio)
        if (
            not valid(original.get("value"))
            or not math.isclose(ratio, original["value"], rel_tol=1e-12, abs_tol=1e-12)
            or grade != original["grade"]
            or WEIGHTS[name] * grade / 4 != original["points"]
        ):
            raise ValueError("원자료·서울 기준선에서 관측 등급·점수가 재현되지 않았습니다.")
        out["items"][name].update(ratio=ratio, exposure=exposure_for(name, counts))
    return out


def adjusted_grade(name: str, trace: dict, method: str) -> float:
    item = trace["items"][name]
    if item["status"] != "observed":
        raise ValueError("미확인 자료를 관측된 점수로 보완할 수 없습니다.")
    if method == "neutral_S" or method == "neutral_" + name:
        return 2.0
    grade = grade_for(name, item["ratio"], continuous="continuous" in method)
    if method in {"exposure_S", "continuous_exposure_S"}:
        fraction = item["exposure"] / (item["exposure"] + EXPOSURE_PRIOR)
        grade = 2 + fraction * (grade - 2)
    return grade


def score_row(row: dict, trace: dict, method: str) -> float | None:
    if method not in METHODS:
        raise ValueError("개폐업 비교 방식이 잘못되었습니다.")
    applicable, points = 0.0, 0.0
    for name in C_ITEMS:
        item = row["items"][name]
        weight = (
            (0 if name == "S3" else 10)
            if method == "without_turnover" and name in S_ITEMS
            else WEIGHTS[name]
        )
        if item["status"] == "n.a.":
            continue
        applicable += weight
        if item["status"] == "observed":
            points += (
                weight * adjusted_grade(name, trace, method) / 4
                if name in S_ITEMS
                else item["points"]
            )
    return MODEL_WEIGHT * points / applicable if applicable else None


def order_rows(rows: list[dict], values: dict[str, float], method: str) -> list[str]:
    if any(values[row["code"]] is None for row in rows):
        raise ValueError("관측 후보 점수를 만들 수 없습니다.")
    return [
        r["code"]
        for r in sorted(
            rows,
            key=lambda row: (
                -(
                    values[row["code"]]
                    if method == "baseline"
                    else round(values[row["code"]], RANK_DECIMALS)
                ),
                -(row["coverage"] or 0),
                row["code"],
            ),
        )
    ]


def extra_close(trace: dict) -> dict | None:
    counts = trace["counts"]
    if counts is None or counts["stores"][-1] <= counts["closed"][-1]:
        return None
    changed = copy.deepcopy(trace)
    changed["counts"]["closed"][-1] += 1
    changed["local_metrics"] = rates_from_counts(changed["counts"])
    for name, item in changed["items"].items():
        if item["status"] == "observed":
            ratio = ratio_for(name, changed["local_metrics"], changed["city_baseline"])
            grade = grade_for(name, ratio)
            item.update(
                ratio=ratio,
                value=ratio,
                grade=grade,
                points=WEIGHTS[name] * grade / 4,
                exposure=exposure_for(name, changed["counts"]),
            )
    changed["perturbation"] = "감도 시험: 마지막 분기 폐업 건수만 1 증가. 원자료 변경 아님."
    return changed

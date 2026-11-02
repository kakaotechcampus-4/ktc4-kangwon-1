"""과거 구간의 비교 기준만 사용해 S 점수를 만들고 이후 개폐업 지표를 평가합니다."""

import math
import random
from collections import defaultdict
from itertools import combinations
from statistics import mean

from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.lifecycle_scores import grade_for, ratio_for

METHODS = ("step", "continuous")
PAST_N = 8
FUTURE_N = 4


def metrics(series: list, *, rounded=True) -> dict | None:
    if not series or any(row is None for row in series):
        return None
    if any(len(row) != 3 or any(type(v) is not int or v < 0 for v in row) for row in series):
        raise ValueError("분기 건수에는 관측된 음이 아닌 정수가 필요합니다.")
    stores = [r[0] for r in series]
    opened, closed = sum(r[1] for r in series), sum(r[2] for r in series)

    def rate(a, b):
        value = 100 * a / b if b else None
        return round(value, 2) if rounded and value is not None else value

    return {
        "exposure": sum(stores),
        "old_exposure": sum(stores[:4]),
        "recent_exposure": sum(stores[-4:]),
        "recent_year_close_rate": rate(sum(r[2] for r in series[-4:]), sum(stores[-4:])),
        "oldest_year_close_rate": rate(sum(r[2] for r in series[:4]), sum(stores[:4])),
        "net_change_rate": rate(opened - closed, sum(stores)),
        "turnover_rate": rate(opened + closed, sum(stores)),
        "period_close_rate": rate(closed, sum(stores)),
    }


def fit_baselines(panel: dict, reference_areas: list[str], *, min_areas=20) -> dict:
    baselines = {}
    for code in INDUSTRY_TO_SEOUL:
        complete = [
            panel[a][code]
            for a in reference_areas
            if len(panel[a][code]) == PAST_N and all(v is not None for v in panel[a][code])
        ]
        if len(complete) < min_areas:
            continue
        pooled = [tuple(sum(v[q][k] for v in complete) for k in range(3)) for q in range(PAST_N)]
        stats = metrics(pooled)
        if (
            min(
                stats["recent_year_close_rate"] or 0,
                stats["oldest_year_close_rate"] or 0,
                stats["turnover_rate"] or 0,
            )
            <= 0
        ):
            continue
        baselines[code] = {**stats, "reference_area_n": len(complete), "pooled_counts": pooled}
    return baselines


def score_history(series: list, baseline: dict | None) -> tuple[dict | None, str | None]:
    if len(series) != PAST_N:
        raise ValueError("과거 입력은 정확히 8개 분기여야 합니다.")
    local = metrics(series)
    if local is None:
        return None, "missing_past_source_cells"
    if baseline is None:
        return None, "insufficient_reference_areas"
    if min(local["old_exposure"], local["recent_exposure"]) < 40:
        return None, "insufficient_past_exposure"
    if local["oldest_year_close_rate"] is None or local["oldest_year_close_rate"] <= 0:
        return None, "undefined_past_trend"
    ratios = {name: ratio_for(name, local, baseline) for name in ("S1", "S2", "S3", "S4")}
    grades = {
        method: {
            name: grade_for(name, ratio, continuous=method == "continuous")
            for name, ratio in ratios.items()
        }
        for method in METHODS
    }
    return {
        "past_counts": series,
        "past_metrics": local,
        "ratios": ratios,
        "grades": grades,
        "scores": {
            method: sum(7.5 * value / 4 for value in values.values())
            for method, values in grades.items()
        },
    }, None


def make_features(
    panel: dict, baselines: dict, areas: dict, selected: list[str], *, min_candidates=5
) -> dict:
    cases, exclusions = [], []
    for area in selected:
        candidates, reasons = {}, defaultdict(int)
        for code, series in panel[area].items():
            value, reason = score_history(series, baselines.get(code))
            if reason:
                reasons[reason] += 1
            else:
                candidates[code] = value
        if len(candidates) < min_candidates:
            exclusions.append(
                {"area": area, "candidate_n": len(candidates), "reasons": dict(reasons)}
            )
            continue
        cases.append(
            {
                "area": area,
                "name": areas[area]["name"],
                "district": areas[area]["district"],
                "district_name": areas[area]["district_name"],
                "candidate_n": len(candidates),
                "candidates": candidates,
                "orders": {
                    m: sorted(
                        candidates,
                        key=lambda code: (-round(candidates[code]["scores"][m], 10), code),
                    )
                    for m in METHODS
                },
                "exclusion_reasons": dict(reasons),
            }
        )
    return {"cases": cases, "past_only_exclusions": exclusions, "baselines": baselines}


def future_outcome(series: list, baseline: dict) -> dict:
    if len(series) != FUTURE_N:
        raise ValueError("이후 결과는 정확히 4개 분기여야 합니다.")
    value = metrics(series, rounded=False)
    if value is None:
        return {"status": "unknown", "reason": "missing_future_source_cells"}
    if not value["exposure"]:
        return {"status": "unknown", "reason": "zero_future_exposure"}
    return {
        "status": "observed",
        "future_counts": series,
        "exposure": value["exposure"],
        "close_rate": value["period_close_rate"],
        "net_change_rate": value["net_change_rate"],
        "closure_ratio": value["period_close_rate"] / baseline["recent_year_close_rate"],
    }


def concordance(candidates: dict, labels: dict, method: str) -> tuple[float | None, int]:
    values = []
    available = [code for code in candidates if labels[code]["status"] == "observed"]
    for a, b in combinations(available, 2):
        future_gap = labels[a]["closure_ratio"] - labels[b]["closure_ratio"]
        if math.isclose(future_gap, 0, abs_tol=1e-12):
            continue
        score_gap = candidates[a]["scores"][method] - candidates[b]["scores"][method]
        values.append(
            0.5 if math.isclose(score_gap, 0, abs_tol=1e-10) else float(score_gap * future_gap < 0)
        )
    return (mean(values) if values else None), len(values)


def paired_interval(rows: list[dict], metric: str, *, rounds=2000, seed=20261026) -> dict:
    usable = [
        row for row in rows if all(row["metrics"][m].get(metric) is not None for m in METHODS)
    ]
    groups = defaultdict(list)
    for row in usable:
        groups[row["district"]].append(
            row["metrics"]["continuous"][metric] - row["metrics"]["step"][metric]
        )
    delta = mean(v for values in groups.values() for v in values) if groups else None
    ci = None
    if len(groups) >= 2:
        groups = list(groups.values())
        rng = random.Random(seed)
        draws = []
        for _ in range(rounds):
            selected = [groups[rng.randrange(len(groups))] for _ in groups]
            draws.append(mean(v for group in selected for v in group))
        draws.sort()

        def quantile(q):
            position = q * (len(draws) - 1)
            index = int(position)
            return draws[index] + (position - index) * (
                draws[min(index + 1, len(draws) - 1)] - draws[index]
            )

        ci = [quantile(0.025), quantile(0.975)]
    return {
        "area_n": len(usable),
        "district_n": len({r["district"] for r in usable}),
        "delta_continuous_minus_step": delta,
        "ci95": ci,
        "rounds": rounds if ci else 0,
        "seed": seed,
    }


def evaluate(features: dict, future: dict) -> dict:
    rows, missing = [], defaultdict(int)
    for case in features["cases"]:
        labels = {
            code: future_outcome(future[case["area"]][code], features["baselines"][code])
            for code in case["candidates"]
        }
        for value in labels.values():
            if value["status"] != "observed":
                missing[value["reason"]] += 1
        paired = all(
            labels[code]["status"] == "observed" for m in METHODS for code in case["orders"][m][:5]
        )
        result = {
            "area": case["area"],
            "district": case["district"],
            "candidate_n": case["candidate_n"],
            "paired_top5_outcomes_complete": paired,
            "labels": labels,
            "metrics": {},
        }
        for method in METHODS:
            top = [labels[code] for code in case["orders"][method][:5]]
            complete = all(v["status"] == "observed" for v in top)
            pair_score, pair_n = concordance(case["candidates"], labels, method)
            result["metrics"][method] = {
                "top5_outcomes_complete": complete,
                "top5_closure_ratio": mean(v["closure_ratio"] for v in top) if paired else None,
                "top5_close_rate": mean(v["close_rate"] for v in top) if paired else None,
                "top5_net_change_rate": mean(v["net_change_rate"] for v in top) if paired else None,
                "pairwise_concordance": pair_score,
                "comparable_pair_n": pair_n,
            }
        rows.append(result)
    if not rows:
        raise ValueError("과거 조건을 만족하는 검증 상권이 없습니다.")
    metrics = (
        "top5_closure_ratio",
        "top5_close_rate",
        "top5_net_change_rate",
        "pairwise_concordance",
    )
    return {
        "area_n": len(rows),
        "candidate_n": sum(r["candidate_n"] for r in rows),
        "paired_top5_area_n": sum(r["paired_top5_outcomes_complete"] for r in rows),
        "future_missing_reasons": dict(missing),
        "methods": {
            m: {
                "top5_outcomes_complete_area_n": sum(
                    r["metrics"][m]["top5_outcomes_complete"] for r in rows
                ),
                **{
                    metric: mean(v)
                    if (
                        v := [
                            r["metrics"][m][metric]
                            for r in rows
                            if r["metrics"][m][metric] is not None
                        ]
                    )
                    else None
                    for metric in metrics
                },
            }
            for m in METHODS
        },
        "paired_difference": {metric: paired_interval(rows, metric) for metric in metrics},
        "top5_set_changed_n": sum(
            set(c["orders"]["step"][:5]) != set(c["orders"]["continuous"][:5])
            for c in features["cases"]
        ),
        "cases": rows,
        "interpretation": "과거 S와 이후 개폐업 지표 비교. 개별 점포 생존율·전체 추천 정확도 아님",
    }

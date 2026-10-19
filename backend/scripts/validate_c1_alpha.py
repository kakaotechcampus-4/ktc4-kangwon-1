"""저장된 8곳 자료로 C1 수요 보정 강도와 개폐업의 순위상관을 확인한다."""

from __future__ import annotations

import json
import math
import statistics
import sys
from bisect import bisect_right
from collections import Counter
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agentic.c1_units import CLUSTER_UNIT, PROFILE_UNIT, c1_unit  # noqa: E402
from app.agents.floating_population.baseline import DAILY_TOTAL_PERCENTILES  # noqa: E402
from scripts.rubric_dryrun import evaluate, result, summarize, valid  # noqa: E402

ALPHAS = (0, 0.5, 0.75, 1.0)
FOOD = {"I201", "I202", "I203", "I204", "I210"}


def ranks(values: list[float]) -> list[float]:
    """동점은 평균 순위로 처리한다."""
    ordered = sorted(range(len(values)), key=values.__getitem__)
    output = [0.0] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        for index in ordered[start:end]:
            output[index] = (start + 1 + end) / 2
        start = end
    return output


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 2 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return statistics.correlation(ranks(x), ranks(y))


def alpha_reports(samples: list[dict], alpha: float, threshold: float = 0.65) -> list[dict]:
    reports = []
    for sample in samples:
        base = evaluate(sample, c1_alpha=0)
        daily = (
            sample.get("floating_population", {})
            .get("benchmark", {})
            .get("mean_daily_per_trade_area")
        )
        factor = daily / DAILY_TOTAL_PERCENTILES[50] if valid(daily) and daily > 0 else None
        rows = []
        for row in base["rows"]:
            if c1_unit(row["items"]["C1"]["reason"]) in (CLUSTER_UNIT, PROFILE_UNIT):
                continue
            items = deepcopy(row["items"])
            if items["C1"]["status"] == "observed":
                q = items["C1"]["value"]
                if alpha > 0 and factor is None:
                    items["C1"] = result("C1", reason="유동 규모 결측·0")
                else:
                    q /= factor**alpha if alpha else 1
                    items["C1"] = result(
                        "C1",
                        4 - bisect_right([0.5, 0.8, 1.2, 1.5], q),
                        value=q,
                        reason=f"시험 α={alpha}",
                    )
            rows.append(summarize(row["code"], items, row["regulation"], lower_min=threshold))
        reports.append(
            {
                "address": base["address"],
                "rows": rows,
                "badges": dict(Counter(r["badge"] for r in rows)),
            }
        )
    return reports


def correlations(reports: list[dict], food_only: bool, metric: str) -> dict:
    rows = [r for report in reports for r in report["rows"] if not food_only or r["code"] in FOOD]
    eligible = [
        r for r in rows if all(r["items"][k]["status"] == "observed" for k in {"C1", "S1", metric})
    ]
    positive = [r for r in eligible if r["items"]["C1"]["value"] > 0]
    x = [math.log(r["items"]["C1"]["value"]) for r in positive]
    y = [r["items"][metric]["value"] for r in positive]
    return {
        "rho": spearman(x, y),
        "n": len(positive),
        "eligible": len(eligible),
        "excluded_q_zero": len(eligible) - len(positive),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "cache/rubric_samples"
    samples = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("sample-*.json"))
    ]
    reports = {str(alpha): alpha_reports(samples, alpha) for alpha in ALPHAS}
    comparison = {
        alpha: {
            group: {metric: correlations(rows, group == "food", metric) for metric in ("S1", "S3")}
            for group in ("all", "food")
        }
        for alpha, rows in reports.items()
    }
    primary = {
        float(a): data["all"]["S1"]["rho"]
        for a, data in comparison.items()
        if data["all"]["S1"]["rho"] is not None
    }
    best = max(primary.values())
    recommended = min(alpha for alpha, rho in primary.items() if best - rho <= 0.05)
    thresholds = {str(t): alpha_reports(samples, recommended, t) for t in (0.60, 0.65, 0.70)}
    output = {
        "http_calls": 0,
        "llm_calls": 0,
        "comparison": comparison,
        "recommended_alpha": recommended,
        "selection_rule": "전체 S1 주 기준·S3/음식 보조. 최고 상관과 차이≤0.05인 최소 α",
        "threshold_reports": thresholds,
        "reports": reports,
    }
    (root / "c1-alpha-validation.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: output[k] for k in ("comparison", "recommended_alpha", "selection_rule")},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

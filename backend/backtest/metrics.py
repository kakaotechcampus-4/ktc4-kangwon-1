from collections import Counter
from statistics import mean, median
from typing import Any

import numpy as np

SEED = 20261017
DONE = "완료"


def bootstrap_mean(
    values: list[float], rounds: int = 1000, seed: int = SEED
) -> tuple[float, float, float]:
    array = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = rng.choice(array, size=(rounds, len(array)), replace=True).mean(axis=1)
    return float(array.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def rank_metrics(ranks: list[int]) -> dict[str, Any]:
    if not ranks:
        return {"주소 수": 0}
    share, low, high = bootstrap_mean([1.0 if rank <= 5 else 0.0 for rank in ranks])
    return {
        "주소 수": len(ranks),
        "상위5 비율": round(share, 3),
        "상위5 95% 구간": [round(low, 3), round(high, 3)],
        "상위10 비율": round(sum(rank <= 10 for rank in ranks) / len(ranks), 3),
        "순위 중앙값": median(ranks),
    }


def summarize(summaries: list[dict]) -> dict[str, Any]:
    done = [s for s in summaries if s.get("상태") == DONE]
    result: dict[str, Any] = {
        "상태": dict(Counter(s.get("상태") for s in summaries)),
        "서비스": rank_metrics([s["순위"] for s in done]),
        "점포 수 기준": rank_metrics([s["점포 수 순위"] for s in done]),
    }
    if not done:
        return result
    result["무작위 상위5 기대 비율"] = round(
        mean(s["상위5 업종 수"] / s["업종 수"] for s in done), 3
    )
    result["평균 대비 평균"] = round(mean(s["평균 대비"] for s in done), 2)
    result["배지"] = dict(Counter(s["배지"] for s in done))
    result["항목 차이 평균"] = {d: round(mean(s[f"{d} 차이"] for s in done), 2) for d in "DCS"}
    groups = sorted({s["그룹"] for s in done})
    result["그룹별"] = {
        g: rank_metrics([s["순위"] for s in done if s["그룹"] == g]) for g in groups
    }
    result["서울 자료 없음 대상"] = sum(bool(s["서울 자료 없음"]) for s in done)
    result["현재 시점 자료 대상"] = sum(bool(s["현재 시점 C4"] or s["현재 시점 G"]) for s in done)
    return result

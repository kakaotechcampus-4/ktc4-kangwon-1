"""같은 주소의 순위를 짝지어 비교하고 판단 보류를 전체 분모에 남깁니다."""

from collections import Counter, defaultdict
from statistics import mean

import numpy as np


def rank_of(order: list[str], target: str) -> int | None:
    if len(order) != len(set(order)):
        raise ValueError("순위에 같은 업종이 중복됩니다.")
    return order.index(target) + 1 if target in order else None


def summarize(cases: list[dict], method: str) -> dict:
    if not cases:
        raise ValueError("평가할 주소가 없습니다.")
    by_industry = defaultdict(list)
    ranks, returned, frequency = [], [], Counter()
    for case in cases:
        order = case["orders"][method]
        rank = rank_of(order, case["target"])
        ranks.append(rank)
        returned.append(bool(order))
        by_industry[case["target"]].append(rank)
        frequency.update(order[:5])

    def hit(rank, k):
        return rank is not None and rank <= k

    industries = {
        code: {
            "n": len(values),
            "hit5_n": sum(hit(rank, 5) for rank in values),
            "hit5": mean(hit(rank, 5) for rank in values),
        }
        for code, values in sorted(by_industry.items())
    }
    hit_n = sum(hit(rank, 5) for rank in ranks)
    return {
        "n": len(cases),
        "hit5_n": hit_n,
        "hit5": hit_n / len(cases),
        "hit10": mean(hit(rank, 10) for rank in ranks),
        "hit15": mean(hit(rank, 15) for rank in ranks),
        "macro_hit5": mean(item["hit5"] for item in industries.values()),
        "mrr": mean(1 / rank if rank is not None else 0 for rank in ranks),
        "returned_n": sum(returned),
        "returned_rate": mean(returned),
        "hit5_given_returned": hit_n / sum(returned) if any(returned) else None,
        "industries": industries,
        "top5_frequency": dict(frequency),
        "top10_concentration": (
            sum(count for _, count in frequency.most_common(10)) / sum(frequency.values())
            if frequency
            else None
        ),
    }


def paired_cluster_interval(cases: list[dict], a="A", b="B", *, rounds=2000, seed=20261025) -> dict:
    if not cases:
        raise ValueError("평가할 주소가 없습니다.")
    groups = defaultdict(list)
    for case in cases:
        ranks = [rank_of(case["orders"][method], case["target"]) for method in (a, b)]
        hits = [int(rank is not None and rank <= 5) for rank in ranks]
        groups[case["cluster"]].append(hits[1] - hits[0])
    delta = mean(value for values in groups.values() for value in values)
    if len(groups) < 2:
        return {"delta": delta, "ci95": None, "clusters": len(groups), "rounds": 0}
    sums = np.array([sum(values) for values in groups.values()], dtype=float)
    counts = np.array([len(values) for values in groups.values()], dtype=float)
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(groups), size=(rounds, len(groups)))
    estimates = sums[samples].sum(axis=1) / counts[samples].sum(axis=1)
    return {
        "delta": delta,
        "ci95": [float(value) for value in np.quantile(estimates, [0.025, 0.975])],
        "clusters": len(groups),
        "rounds": rounds,
        "seed": seed,
    }

import math
from itertools import combinations

import numpy as np

from backtest.data import quarters_until
from backtest.outcome import StoreTable


def concordance(scores: dict[str, float], outcomes: dict[str, float]) -> float | None:
    common = [
        k
        for k in outcomes
        if k in scores and math.isfinite(scores[k]) and math.isfinite(outcomes[k])
    ]
    pairs = [(a, b) for a, b in combinations(common, 2) if outcomes[a] != outcomes[b]]
    if not pairs:
        return None
    total = 0.0
    for a, b in pairs:
        sign = (scores[a] - scores[b]) * (outcomes[a] - outcomes[b])
        total += 1.0 if sign > 0 else 0.5 if sign == 0 else 0.0
    return total / len(pairs)


def bootstrap_mean(
    values: list[float], rounds: int = 1000, seed: int = 20261005
) -> tuple[float, float, float]:
    array = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = rng.choice(array, size=(rounds, len(array)), replace=True).mean(axis=1)
    return float(array.mean()), float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def cluster_bootstrap_ratio(
    groups: list[list[float]], rounds: int = 1000, seed: int = 20261005
) -> tuple[float, float, float]:
    kept = [group for group in groups if group]
    sums = np.asarray([sum(group) for group in kept], dtype=float)
    sizes = np.asarray([len(group) for group in kept], dtype=float)
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(kept), size=(rounds, len(kept)))
    ratios = sums[picks].sum(axis=1) / sizes[picks].sum(axis=1)
    return (
        float(sums.sum() / sizes.sum()),
        float(np.quantile(ratios, 0.025)),
        float(np.quantile(ratios, 0.975)),
    )


def seoul_baseline(table: StoreTable, base: str) -> dict[str, float]:
    past = quarters_until(base, 12)
    return {
        industry: value
        for industry in table.industries
        if (value := table.seoul_survival(industry, past)) is not None
    }


def persistence_baseline(table: StoreTable, area: str, base: str) -> dict[str, float]:
    past = quarters_until(base, 4)
    return {
        industry: value
        for industry in table.industries
        if (value := table.survival(area, industry, past)) is not None
    }


def popularity_baseline(table: StoreTable, area: str, base: str) -> dict[str, float]:
    return table.stores_at(area, base)

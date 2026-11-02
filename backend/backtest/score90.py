"""D·C1·S 80점과 C4 10점의 실제 배점을 유지하는 비교용 계산입니다."""

import math
from dataclasses import dataclass

from backtest.c4_policy import POLICIES, score_policy

S_RATIOS = {
    "equal": (1, 1, 1, 1),
    "closure": (2, 1, 1, 1),
    "stable": (2, 1, 2, 1),
    "turnover": (1, 1, 2, 1),
    "recent": (1, 1, 1, 2),
    "growth": (1, 2, 1, 1),
}
C4_POLICY = next(p for p in POLICIES if p.name == "mean_mild_unknown")


@dataclass(frozen=True)
class Score90Configuration:
    competition_weight: int
    survival_ratio: str
    repair_S4_zero: bool = False

    def __post_init__(self):
        if self.competition_weight not in (25, 30) or self.survival_ratio not in S_RATIOS:
            raise ValueError("사전에 정한 90점 배점 조합만 허용합니다.")

    @property
    def name(self):
        suffix = "_S4zero" if self.repair_S4_zero else ""
        group = f"C{self.competition_weight}S{45 - self.competition_weight}"
        return group + "_" + self.survival_ratio + suffix

    @property
    def weights(self):
        ratios = S_RATIOS[self.survival_ratio]
        total = 45 - self.competition_weight
        return {
            "D1": 10,
            "D2": 10,
            "D3": 10,
            "D4": 5,
            "C1": self.competition_weight,
            **{f"S{i + 1}": total * r / sum(ratios) for i, r in enumerate(ratios)},
        }


CONFIGURATIONS = tuple(
    Score90Configuration(c, ratio, repair)
    for c in (25, 30)
    for ratio in S_RATIOS
    for repair in (False, True)
)
CONTROL = Score90Configuration(30, "equal").name


def score90(
    fractions: dict, statuses: dict, profile: dict, facilities: dict, config, *, S4_repair=None
):
    if (
        config not in CONFIGURATIONS
        or set(fractions) != set(config.weights)
        or set(statuses) != set(fractions)
    ):
        raise ValueError("고정한 90점 항목·관측 상태·배점이 필요합니다.")
    effective = dict(fractions)
    repaired = False
    if config.repair_S4_zero and S4_repair is not None:
        if statuses["S4"] != "unknown" or not math.isfinite(S4_repair) or not 0 <= S4_repair <= 1:
            raise ValueError("실제 0건 원문으로 검증한 미확인 S4만 보완할 수 있습니다.")
        effective["S4"] = S4_repair
        repaired = True
    for name, fraction in effective.items():
        if (
            type(fraction) not in (int, float)
            or not math.isfinite(fraction)
            or not -1e-12 <= fraction <= 1 + 1e-12
        ):
            raise ValueError("항목별 기여 비율은 0~1이어야 합니다.")
        if statuses[name] not in ("observed", "unknown", "n.a."):
            raise ValueError("관측·미확인·미적용 상태를 구분해야 합니다.")
        if statuses[name] == "n.a." and fraction != 0:
            raise ValueError("미적용 항목에 점수를 부여할 수 없습니다.")
    weights = config.weights
    if not math.isclose(sum(weights.values()) + 10, 90, abs_tol=1e-12):
        raise ValueError("명목 배점 합계가 90점이어야 합니다.")
    contributions = {n: weights[n] * effective[n] for n in weights}
    applicable80 = sum(w for n, w in weights.items() if statuses[n] != "n.a.")
    common80 = 80 * sum(contributions.values()) / applicable80
    result = score_policy(common80, applicable80, profile, facilities, C4_POLICY)
    if result["effective_C4_weight"] not in (0, 10):
        raise ValueError("C4의 실제 최대 배점10점을 유지해야 합니다.")
    return {
        **result,
        "D_points": sum(p for n, p in contributions.items() if n.startswith("D")),
        "C1_points": contributions["C1"],
        "S_points": sum(p for n, p in contributions.items() if n.startswith("S")),
        "item_contributions": contributions,
        "common80": common80,
        "common80_applicable": applicable80,
        "source_status": dict(statuses),
        "C4_source_status": result["source_status"],
        "S4_separate_repair_applied": repaired,
    }

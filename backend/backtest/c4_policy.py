"""시설 가정의 확신도와 실제 관측을 분리하는 C4 비교용 순수 계산입니다."""

import math
from dataclasses import dataclass
from statistics import mean

from app.agentic.scoring import score_item


@dataclass(frozen=True)
class FacilityPolicy:
    name: str
    aggregation: str = "min"
    unknown: str = "zero"
    low_confidence_scale: float = 1.0

    def __post_init__(self):
        if (
            self.aggregation not in ("min", "mean")
            or self.unknown not in ("zero", "one_grade_discount")
            or self.low_confidence_scale not in (0.5, 1.0)
        ):
            raise ValueError("사전에 고정한 C4 비교 정책만 사용할 수 있습니다.")


POLICIES = (
    FacilityPolicy("original_min_zero"),
    FacilityPolicy("min_mild_unknown", unknown="one_grade_discount"),
    FacilityPolicy("mean_zero", aggregation="mean"),
    FacilityPolicy("mean_mild_unknown", aggregation="mean", unknown="one_grade_discount"),
    FacilityPolicy(
        "mean_mild_low_confidence_half",
        aggregation="mean",
        unknown="one_grade_discount",
        low_confidence_scale=0.5,
    ),
)


def observe_components(profile: dict, code: str, facilities: dict) -> dict:
    required = profile.get("required_facilities", "")
    if not required:
        return {}
    return {
        category: score_item(
            "C4", {**profile, "required_facilities": category}, code, {"facilities": facilities}
        )
        for category in required.split(";")
    }


def score_policy(
    score80: float,
    applicable80: float,
    profile: dict,
    components: dict,
    policy: FacilityPolicy,
) -> dict:
    if (
        type(score80) not in (int, float)
        or not math.isfinite(score80)
        or not 0 <= score80 <= 80 + 1e-9
        or type(applicable80) not in (int, float)
        or not math.isfinite(applicable80)
        or not 0 < applicable80 <= 80
    ):
        raise ValueError("기존 80점과 적용 배점이 유효해야 합니다.")
    required = profile.get("required_facilities", "")
    categories = required.split(";") if required else []
    if len(categories) != len(set(categories)) or set(components) != set(categories):
        raise ValueError("업종별 시설 목록과 개별 관측이 같아야 합니다.")
    raw80 = score80 * applicable80 / 80
    # 미적용은 미확인으로 바꾸거나 임의로 시설 점수를 부여하지 않습니다.
    if not categories:
        return {
            "normalized": 90 * raw80 / applicable80,
            "source_status": "n.a.",
            "observed_aggregate_points": None,
            "policy_aggregate_points": None,
            "effective_C4_weight": 0.0,
            "effective_C4_contribution": 0.0,
            "applicable_weight": applicable80,
            "derived_from_unknown": False,
            "component_status": {},
        }
    values, states = [], {}
    # 미확인은 기존 점수 비율에서 한 등급(10점 중 2.5점)을 뺀 정책 기여입니다.
    # 시설 거리 관측으로 표시하지 않으며, 전부 미확인이면 C4 제외안보다 낮게 평가합니다.
    estimate = 10 * max(0.0, min(1.0, score80 / 80) - 0.25)
    for category in categories:
        item = components[category]
        state, point = item["status"], item["points"]
        if state not in ("observed", "unknown"):
            raise ValueError("적용 시설은 관측 또는 미확인 상태여야 합니다.")
        if state == "observed":
            if type(point) not in (int, float) or not math.isfinite(point) or not 0 <= point <= 10:
                raise ValueError("관측 시설 점수는 0~10점이어야 합니다.")
            values.append(point)
        elif point is not None:
            raise ValueError("미확인 시설의 원래 관측 점수는 비어 있어야 합니다.")
        else:
            values.append(estimate if policy.unknown == "one_grade_discount" else 0.0)
        states[category] = state
    aggregate = min(values) if policy.aggregation == "min" else mean(values)
    complete = all(state == "observed" for state in states.values())
    confidence = profile.get("required_facilities_confidence")
    distance_confidence = profile.get("max_distance_m_confidence")
    scale = policy.low_confidence_scale if "low" in (confidence, distance_confidence) else 1.0
    weight = 10 * scale
    contribution = aggregate * scale
    value = 90 * (raw80 + contribution) / (applicable80 + weight)
    if not math.isfinite(value) or not 0 <= value <= 90 + 1e-9:
        raise ValueError("C4 정책 결과가 90점 환산 범위를 벗어났습니다.")
    return {
        "normalized": value,
        "source_status": "observed" if complete else "unknown",
        "observed_aggregate_points": aggregate if complete else None,
        "policy_aggregate_points": aggregate,
        "effective_C4_weight": weight,
        "effective_C4_contribution": contribution,
        "applicable_weight": applicable80 + weight,
        "derived_from_unknown": not complete,
        "unknown_component_policy_points": estimate if policy.unknown != "zero" else 0.0,
        "component_status": states,
        "profile_scale_is_not_measurement_confidence": True,
    }

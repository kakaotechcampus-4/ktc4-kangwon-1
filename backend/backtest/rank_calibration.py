"""가까운 평가 위치를 제외한 관측 분포로만 업종별 점수의 상대 위치를 보정합니다."""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from statistics import mean

from app.agentic.scoring import WEIGHTS, valid
from app.geo import haversine_m
from backtest.followup import C_ITEMS

MIN_REFERENCE_CLUSTERS = 20
EXCLUSION_RADIUS_M = 1000
CALIBRATIONS = {
    "cal_S_half": (("S",), 0.5),
    "cal_C1_half": (("C1",), 0.5),
    "cal_both_half": (("C1", "S"), 0.5),
    "cal_S_full": (("S",), 1.0),
}


def feature_value(name: str, item: dict) -> float | None:
    if item["status"] != "observed":
        return None
    if name == "C1":
        # 무관 업종의 고정 7.5점은 관측 분포에 섞거나 상대 평가하지 않습니다.
        return item["grade"] if item.get("value") is not None else None
    if name not in ("S1", "S2", "S3", "S4"):
        return None
    ratio = item.get("value")
    if not valid(ratio):
        raise ValueError("관측 S 문항의 비교 비율이 없습니다.")
    return ratio if name == "S2" else -ratio


def reference_for(records: list[dict], site: dict, cluster: str) -> dict:
    observations = defaultdict(lambda: defaultdict(list))
    training, excluded = [], []
    for record in records:
        overlaps = (
            haversine_m(
                site["latitude"],
                site["longitude"],
                record["site"]["latitude"],
                record["site"]["longitude"],
            )
            <= EXCLUSION_RADIUS_M
        )
        if record["cluster"] == cluster or overlaps:
            excluded.append(record["id"])
            continue
        training.append(record["id"])
        for row in record["scores"]:
            for name in ("C1", "S1", "S2", "S3", "S4"):
                value = feature_value(name, row["items"][name])
                if value is not None:
                    observations[(row["code"], name)][record["cluster"]].append(value)
    return {
        "values": {
            key: sorted(mean(values) for values in clusters.values())
            for key, clusters in observations.items()
        },
        "training_ids": sorted(training),
        "excluded_ids": sorted(excluded),
    }


def apply_calibration(row: dict, base: dict, reference: dict, name: str) -> dict:
    if name not in CALIBRATIONS:
        return base
    domains, blend = CALIBRATIONS[name]
    points, grades = dict(base["item_points"]), dict(base["item_grades"])
    details = {}
    for item_name in C_ITEMS:
        domain = "S" if item_name.startswith("S") else item_name
        if domain not in domains:
            continue
        value = feature_value(item_name, row["items"][item_name])
        if value is None:
            continue
        observed = reference["values"].get((row["code"], item_name), [])
        if len(observed) < MIN_REFERENCE_CLUSTERS:
            details[item_name] = {"reference_n": len(observed), "source": "base_curve_fallback"}
            continue
        # 같은 값은 중간 순위를 사용해 동일 관측값의 점수가 임의로 갈리지 않게 합니다.
        fraction = (bisect_left(observed, value) + bisect_right(observed, value)) / (
            2 * len(observed)
        )
        grade = (1 - blend) * grades[item_name] + blend * 4 * fraction
        grades[item_name] = grade
        points[item_name] = WEIGHTS[item_name] * grade / 4
        details[item_name] = {
            "reference_n": len(observed),
            "percentile": fraction,
            "source": "other_area_observed_distribution",
        }
    total = sum(v for v in points.values() if v is not None)
    return {
        **base,
        "points": total,
        "normalized": 80 * total / base["applicable"],
        "item_points": points,
        "item_grades": grades,
        "calibration": details,
    }

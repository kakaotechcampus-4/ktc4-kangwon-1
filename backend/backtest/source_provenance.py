"""원문에 있는 0과 없는 행을 분리하고 같은 세부 업종끼리만 비교합니다."""

import math

from app.agents.business_lifecycle.client import get_recent_quarters
from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.rank_variant import s_grade

ITEMS = ("S1", "S2", "S3", "S4")
MODES = (
    "control",
    "withhold_partial",
    "row_fraction",
    "matched_city_share",
    "matched_city_share_squared",
)


def counts(row: dict) -> tuple:
    values = []
    for name in ("SIMILR_INDUTY_STOR_CO", "OPBIZ_STOR_CO", "CLSBIZ_STOR_CO"):
        value = row.get(name)
        if value is None:
            values.append(None)
        else:
            if type(value) not in (int, float, str):
                raise ValueError("원문 건수는 결측 또는 음이 아닌 정수여야 합니다.")
            try:
                numeric = float(value)
            except ValueError as error:
                raise ValueError("보관 CSV의 건수가 숫자 형식이 아닙니다.") from error
            if not math.isfinite(numeric) or numeric < 0 or int(numeric) != numeric:
                raise ValueError("원문 건수는 결측 또는 음이 아닌 정수여야 합니다.")
            values.append(int(numeric))
    return tuple(values)


def valid_counts(value) -> bool:
    return (
        isinstance(value, (tuple, list))
        and len(value) == 3
        and all(type(v) is int and v >= 0 for v in value)
    )


def required_quarters(name: str, quarters: list[str]) -> list[str]:
    if name not in ITEMS or quarters != get_recent_quarters("20252", 12):
        raise ValueError("2025Q2까지의 고정12분기와 S 항목이 필요합니다.")
    return (
        quarters[-4:]
        if name == "S1"
        else quarters[:4] + quarters[-4:]
        if name == "S4"
        else quarters
    )


def totals(panel: dict, quarters: list[str], sources: tuple[str, ...]) -> tuple:
    if not sources or not quarters:
        raise ValueError("실제 원문이 있는 비교창과 세부 업종이 필요합니다.")
    rows = [panel.get(q, {}).get(s) for q in quarters for s in sources]
    if not all(valid_counts(row) for row in rows):
        raise ValueError("누락 행·결측 건수를 0으로 합산할 수 없습니다.")
    return tuple(sum(row[i] for row in rows) for i in range(3))


def matched_estimate(
    name: str,
    quarters: list[str],
    common: tuple[str, ...],
    sources: tuple[str, ...],
    local: dict,
    city: dict,
) -> dict:
    window = required_quarters(name, quarters)
    local_counts, city_counts = totals(local, window, common), totals(city, window, common)
    entire_city = totals(city, window, sources)[0]
    if local_counts[0] <= 0 or city_counts[0] <= 0 or entire_city <= 0:
        return {"available": False, "reason": "zero_exposure_denominator"}
    if name in ("S1", "S3"):
        index = 2 if name == "S1" else None
        local_events = local_counts[index] if index else local_counts[1] + local_counts[2]
        city_events = city_counts[index] if index else city_counts[1] + city_counts[2]
        if city_events <= 0:
            return {"available": False, "reason": "city_rate_denominator_zero"}
        ratio = (local_events / local_counts[0]) / (city_events / city_counts[0])
        effective = local_counts[0]
    elif name == "S2":
        city_turnover = (city_counts[1] + city_counts[2]) / city_counts[0]
        if city_turnover <= 0:
            return {"available": False, "reason": "city_turnover_zero"}
        ratio = (
            1
            + (
                ((local_counts[1] - local_counts[2]) / local_counts[0])
                - ((city_counts[1] - city_counts[2]) / city_counts[0])
            )
            / city_turnover
        )
        effective = min(
            totals(local, quarters[:4], common)[0],
            totals(local, quarters[-4:], common)[0],
            local_counts[0],
        )
    else:
        old, recent = totals(local, quarters[:4], common), totals(local, quarters[-4:], common)
        old_city, recent_city = (
            totals(city, quarters[:4], common),
            totals(city, quarters[-4:], common),
        )
        if (
            min(old[0], recent[0], old_city[0], recent_city[0], old[2], old_city[2], recent_city[2])
            <= 0
        ):
            return {"available": False, "reason": "undefined_close_rate_trend"}
        ratio = ((recent[2] / recent[0]) / (old[2] / old[0])) / (
            (recent_city[2] / recent_city[0]) / (old_city[2] / old_city[0])
        )
        effective = min(old[0], recent[0])
    return {
        "available": True,
        "ratio": ratio,
        "grade": s_grade(name, ratio, "ratio"),
        "local_counts": local_counts,
        "city_counts": city_counts,
        "city_exposure_share": city_counts[0] / entire_city,
        "effective_exposure": effective,
        "exposure_reliability": min(1, effective / 40) ** 2,
        "source_kind": "matched_complete_subindustry_subset_estimate",
        "rate_rounding": "원문 건수로 직접 계산; 중간 비율 반올림 없음",
    }


def evidence(code: str, quarters: list[str], local: dict, city: dict) -> dict:
    sources = INDUSTRY_TO_SEOUL.get(code, ())
    if not sources:
        return {"supported": False, "items": {}}
    output = {}
    for name in ITEMS:
        window = required_quarters(name, quarters)
        missing = [(q, s) for q in window for s in sources if s not in local.get(q, {})]
        invalid = [
            (q, s)
            for q in window
            for s in sources
            if s in local.get(q, {}) and not valid_counts(local[q][s])
        ]
        expected = len(window) * len(sources)
        common = tuple(
            s for s in sources if all(valid_counts(local.get(q, {}).get(s)) for q in window)
        )
        partial = bool(missing or invalid)
        estimate = (
            matched_estimate(name, quarters, common, sources, local, city)
            if partial and common
            else {"available": False, "reason": "no_complete_subset"}
        )
        output[name] = {
            "partial": partial,
            "window": window,
            "missing_rows": missing,
            "invalid_count_rows": invalid,
            "expected_rows": expected,
            "present_valid_rows": expected - len(missing) - len(invalid),
            "row_coverage": (expected - len(missing) - len(invalid)) / expected,
            "common_sources": common,
            "estimate": estimate,
        }
    return {"supported": True, "items": output}


def replace_contributions(trace: dict, source_evidence: dict, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError("사전에 고정한 원문 누락 비교안만 계산합니다.")
    changes, delta = {}, 0.0
    if mode == "control" or not source_evidence["supported"]:
        return {"weighted_delta": delta, "items": changes}
    for name, item in source_evidence["items"].items():
        if not item["partial"] or trace["status"][name] == "n.a.":
            continue
        old = trace["observed"].get(name)
        old = trace["estimated_S"].get(name, 0.0) if old is None else old
        old *= 20 / 30
        estimate = item["estimate"]
        new = (
            old * item["row_coverage"]
            if mode == "row_fraction"
            else 5
            * estimate["grade"]
            / 4
            * estimate["exposure_reliability"]
            * estimate["city_exposure_share"] ** (2 if mode.endswith("squared") else 1)
            if mode.startswith("matched_") and estimate["available"]
            else 0.0
        )
        delta += new - old
        changes[name] = {
            "source_status": trace["status"][name],
            "experimental_status": "partial_source_estimate",
            "previous_weighted_points": old,
            "new_weighted_points": new,
            "source_item_status_and_points_preserved": True,
            "unknown_applicable_weight_kept": True,
        }
    return {"weighted_delta": delta, "items": changes}

"""완전한 원문에서 S1·S2 계산 기간과 관측량 판단 기간을 맞춥니다."""

import math

from app.industries.catalog import INDUSTRY_TO_SEOUL
from backtest.lifecycle_scores import ratio_for
from backtest.rank_variant import s_grade
from backtest.source_provenance import required_quarters, totals, valid_counts
from backtest.temporal_score import metrics

MODES = ("control", "S1_recent_support", "S2_full_period_support", "both_formula_support")
WINDOW_REASON = "과거·최근 각각 노출량 부족"


def evidence_for(code, quarters, local, city, baseline):
    required_quarters("S2", quarters)
    sources = INDUSTRY_TO_SEOUL.get(code, ())
    if not sources or baseline is None:
        return {"available": False, "reason": "unsupported_industry"}
    if not baseline.get("data_complete") or baseline.get("zero_filled_sources") != 0:
        raise ValueError("누락 보충 없는 같은 업종의 서울 기준선이 필요합니다.")
    for name, panel in (("local", local), ("city", city)):
        if any(not valid_counts(panel.get(q, {}).get(s)) for q in quarters for s in sources):
            return {"available": False, "reason": name + "_required_raw_counts_missing"}
    values = {
        name: metrics([totals(panel, [q], sources) for q in quarters])
        for name, panel in (("local", local), ("city", city))
    }
    for field in ("recent_year_close_rate", "net_change_rate", "turnover_rate"):
        measured, expected = values["city"][field], baseline.get(field)
        if (
            measured is None
            or expected is None
            or not math.isclose(measured, expected, abs_tol=1e-10)
        ):
            raise ValueError("같은 원문의 서울 기준선 비율이 재현되지 않습니다.")
    stats = values["local"]
    fractions = {}
    for name in ("S1", "S2"):
        if name == "S1" and stats["recent_exposure"] <= 0:
            continue
        if name == "S2" and stats["exposure"] <= 0:
            continue
        ratio = ratio_for(name, stats, baseline)
        fractions[name] = {"ratio": ratio, "fraction": s_grade(name, ratio, "ratio") / 4}
    return {
        "available": True,
        "full_exposure": stats["exposure"],
        "old_exposure": stats["old_exposure"],
        "recent_exposure": stats["recent_exposure"],
        "fractions": fractions,
        "local_metrics": stats,
        "all12_local_and_city_raw_rows_complete": True,
        "missing_rows_filled": False,
        "exposure_unit": "store_quarters_not_unique_stores",
    }


def apply_support(original, items, evidence, mode):
    if mode not in MODES:
        raise ValueError("사전에 고정한 계산 기간별 관측량 비교안이 필요합니다.")
    fractions, changes = dict(original), {}
    if mode == "control" or not evidence["available"]:
        return {"fractions": fractions, "changes": changes}
    full, old, recent = (evidence[k] for k in ("full_exposure", "old_exposure", "recent_exposure"))
    if (
        mode in ("S1_recent_support", "both_formula_support")
        and items["S1"]["status"] == "observed"
        and 0 < recent < 40
        and "S1" in evidence["fractions"]
    ):
        measured = evidence["fractions"]["S1"]["fraction"]
        if not math.isclose(original["S1"], measured, abs_tol=1e-10):
            raise ValueError("완전한 최근 원문에서 기존 관측 S1이 재현되지 않습니다.")
        factor = (recent / 40) ** 2
        fractions["S1"] = measured * factor
        changes["S1"] = {
            "original_fraction": original["S1"],
            "fraction": fractions["S1"],
            "reliability": factor,
            "formula_exposure": recent,
            "source_status": "observed",
            "kind": "confidence_discount_for_recent_rate_support",
        }
    if (
        mode in ("S2_full_period_support", "both_formula_support")
        and items["S2"]["status"] == "unknown"
        and items["S2"].get("reason") == WINDOW_REASON
        and full >= 40
        and min(old, recent) < 40
        and "S2" in evidence["fractions"]
    ):
        measured = evidence["fractions"]["S2"]["fraction"]
        expected = measured * (min(old, recent) / 40) ** 2
        if not math.isclose(original["S2"], expected, abs_tol=1e-10):
            raise ValueError("같은 원문의 기존 소량 S2 추정이 재현되지 않습니다.")
        fractions["S2"] = measured
        changes["S2"] = {
            "original_fraction": original["S2"],
            "fraction": measured,
            "formula_exposure": full,
            "source_status": "unknown",
            "kind": "derived_full_period_estimate_not_new_observation",
        }
    return {"fractions": fractions, "changes": changes}

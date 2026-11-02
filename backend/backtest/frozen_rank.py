"""새 위치에서 고정한 C1·S 보완과 D75 후보를 같은 과거 입력으로 계산합니다."""

import math

from app.industries.catalog import INDUSTRIES
from backtest.rank_c1_policy import apply_policy
from backtest.rank_d_smooth import demand_adjustment
from backtest.rank_market import apply_market
from backtest.rank_sparse import apply_sparse, sparse_evidence
from backtest.rank_variant import Variant, score_row
from backtest.weight_selection import features_for, order_scores, weighted_score

METHODS = ("current80", "fixed_C1", "fixed_C1_D75", "popular")
DOMAIN_WEIGHTS = (35, 25, 20)
D_FRACTION = 0.75


def score_saved(saved: dict, calibration: dict) -> dict:
    data = saved["data"]
    if (
        calibration["cutoff"] != "20252"
        or data["floating_population"]["period_code"] != "20252"
        or data["business_lifecycle"]["metadata"] != {"base_quarter": "20252", "quarter_count": 12}
    ):
        raise ValueError("고정한 과거 분기·개폐업 기간과 같은 입력이 필요합니다.")
    if {r["code"] for r in saved["scores"]} != set(INDUSTRIES):
        raise ValueError("원래와 같은 전체51개 업종 점수가 필요합니다.")
    values = {m: {} for m in METHODS if m != "popular"}
    details, ties = {}, {}
    commercial = {r["code"]: r for r in data["commercial_area"]["by_middle"]}
    for original in saved["scores"]:
        code = original["code"]
        row = {**original, "items": {**original["items"], **saved["continuous_S_items"][code]}}
        current = score_row(row, Variant("current"))
        if not math.isclose(
            current["normalized"], saved["continuous_score80"][code]["normalized"], abs_tol=1e-10
        ):
            raise ValueError("새 위치의 기존80점이 재현되지 않았습니다.")
        base = score_row(row, Variant("lq_half_s_ratio", s_curve="ratio"))
        # 비교 반경에 업종 자체가 없어 LQ가 정의되지 않으면 관측된 기존 C1만 유지합니다.
        lq_missing = commercial[code].get("lq") is None
        if not lq_missing:
            base = apply_market(row, base, data, "lq_half_s_ratio")
        evidence = sparse_evidence(row, data, calibration)
        sparse = apply_sparse(base, evidence, power=2, curve="ratio")
        features = features_for({n: v["status"] for n, v in row["items"].items()}, sparse)
        weighted = weighted_score(features, DOMAIN_WEIGHTS)
        policy = apply_policy(weighted, row["items"]["C1"], code, data, 25, "lq_shrink5")
        demand = demand_adjustment(row["items"], "all", 35)
        values["current80"][code] = current["normalized"]
        values["fixed_C1"][code] = policy["normalized"]
        values["fixed_C1_D75"][code] = (
            policy["normalized"]
            + 80 * D_FRACTION * demand["weighted_delta"] / weighted["applicable"]
        )
        details[code] = {
            "status": features["status"],
            "observed": features["observed"],
            "estimated_S": features["estimated"],
            "weighted": weighted,
            "C1_policy": policy["policy_change"],
            "D_adjustment": demand,
            "undefined_LQ_keeps_existing_C1": lq_missing,
        }
        ties[code] = {"coverage": row["coverage"], "adjustment": row["space"]["adjustment"]}
    if any(r["space"]["excluded"] or r["regulation"] == "금지" for r in saved["scores"]):
        raise ValueError("이 검증은 같은51개 후보 범위를 유지해야 합니다.")
    orders = {m: order_scores(v, ties) for m, v in values.items()}
    orders["popular"] = sorted(commercial, key=lambda c: (-commercial[c]["count"], c))
    if orders["current80"] != saved["orders"]["past_continuous_80"]:
        raise ValueError("기존 순위가 재현되지 않았습니다.")
    return {"values": values, "orders": orders, "details": details}

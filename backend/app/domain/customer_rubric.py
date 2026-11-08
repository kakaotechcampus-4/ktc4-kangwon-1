"""손님 평가표 v1: 초안의 손님 수요 주장이 근거로 뒷받침되는지 Top5 후보마다 채점합니다.

땅의 수요를 다시 채점하지 않습니다(D1~D4와 중복). K1~K4는 서버가 점수표·fact·초안 문장을
대조해 비율 × 배점으로 계산하고(60점), K6(손님 눈으로 본 추천·근거 일치)만 모델 점수입니다(40점).
판정과 코드 지적도 코드가 만듭니다. 특정 손님층 페르소나는 두지 않고 일반 손님으로 읽습니다.
L의 수요 지표 중복은 validate_l_records가 이미 거절하므로 문항에서 뺐습니다.
"""

from app.domain.contracts import CustomerCandidateScore, CustomerCheck, CustomerRubric, ReviewIssue
from app.domain.scoring import WEIGHTS

DEMAND = ("D1", "D2", "D3", "D4")
# 본 질문(K6)을 가장 크게 두고, 코드 문항은 확실한 잘못을 잡는 안전장치로 과반을 남깁니다.
K_WEIGHTS = {"K1": 15, "K2": 10, "K3": 15, "K4": 20, "K6": 40}
NAMES = {
    "K1": "수요 근거량",
    "K2": "모집단 일치",
    "K3": "장점 문장 방향",
    "K4": "약점 공개",
    "K6": "추천·근거 일치",
}
# K2 상황별 비율: 대상 자료 · 대신 쓰고 밝힘 · 언급 없음 · 대신 쓴 자료를 장점에 씀.
POPULATION_RATIOS = (1, 2 / 3, 1 / 3, 0)
AGREE, OPPOSE = 0.70, 0.40

# 코드 지적: 문항별 (배점 대비 이 비율 미만이면 지적, id, target, kind, 업종명 뒤 문장, 확인 제안).
# K1·K4는 절반 미만, K2는 밝히지 않았을 때, K3는 하나라도 장점에 썼을 때입니다.
ISSUES = {
    "K1": (
        0.5,
        "demand",
        "score",
        "missing_evidence",
        "의 손님 수요 문항 상당수가 자료 없이 비어 있어 수요 주장이 약합니다.",
        "수요 근거가 부족하다는 점을 위험이나 확인 조건으로 밝히세요.",
    ),
    "K2": (
        0.6,
        "population",
        "fact",
        "scope_mismatch",
        "은 상주·직장 손님 대상인데 연령 근거는 유동 인구입니다.",
        "연령 근거가 지나가는 사람 기준임을 문장에 밝히세요.",
    ),
    "K3": (
        1,
        "reason",
        "claim",
        "factual_error",
        "의 장점 문장이 낮은 등급의 수요 근거를 장점처럼 인용합니다.",
        "해당 근거를 장점에서 빼고 위험으로 옮기세요.",
    ),
    "K4": (
        0.5,
        "risk",
        "condition",
        "missing_evidence",
        "의 약한 수요 근거가 위험이나 확인 조건에 드러나 있지 않습니다.",
        "약한 수요 근거를 위험 문장에 인용하세요.",
    ),
}


def _ratio_points(item, ratio):
    """비율(0~1) × 배점. 소수 첫째 자리까지 남깁니다."""
    return round(K_WEIGHTS[item] * ratio, 1)


def _check(item, points, fact_ids, note, status="observed"):
    return CustomerCheck(
        item=item,
        status=status if points is None else "observed",
        weight=K_WEIGHTS[item],
        points=points,
        fact_ids=sorted(fact_ids)[:12],
        note=note,
    )


def cited_ids(segments):
    return {s.fact_id for s in segments if s.type == "fact"}


def score_candidates(candidates, rows, item_facts, citable):
    scored, issues = [], []
    for rank, candidate in enumerate(candidates, 1):
        code = candidate.industry_code
        items = rows[code]["items"]
        facts = {item: set(item_facts.get((code, item), [])) & citable for item in DEMAND}
        observed = {i for i in DEMAND if items[i]["status"] == "observed"}

        applicable = sum(WEIGHTS[i] for i in DEMAND if items[i]["status"] != "n.a.")
        if applicable == 0:
            k1 = _check(
                "K1", None, [], "손님 수요 문항이 적용되지 않는 업종입니다.", "not_applicable"
            )
        else:
            share = sum(WEIGHTS[i] for i in observed) / applicable
            k1 = _check(
                "K1",
                _ratio_points("K1", share),
                set().union(*(facts[i] for i in observed)),
                "적용되는 손님 수요 문항 중 실제 자료로 채점된 비중입니다.",
            )

        disclosed = cited_ids(candidate.risks_segments) | cited_ids(
            candidate.confirmation_conditions_segments
        )
        reasons = cited_ids(candidate.reasons_segments)

        d3 = items["D3"]
        value = d3.get("value") if isinstance(d3.get("value"), dict) else {}
        if d3["status"] != "observed" or value.get("requested_population") not in ("상주", "직장"):
            k2 = _check("K2", None, [], "상주·직장 대상 연령 문항이 아닙니다.", "not_applicable")
        elif value.get("population") == value.get("requested_population"):
            k2 = _check(
                "K2",
                _ratio_points("K2", POPULATION_RATIOS[0]),
                facts["D3"],
                "대상 모집단 자료로 연령을 채점했습니다.",
            )
        else:
            if facts["D3"] & reasons:
                ratio = POPULATION_RATIOS[3]
            elif facts["D3"] & disclosed:
                ratio = POPULATION_RATIOS[1]
            else:
                ratio = POPULATION_RATIOS[2]
            k2 = _check(
                "K2",
                _ratio_points("K2", ratio),
                facts["D3"],
                "상주·직장 대상인데 유동 연령으로 대신 채점했습니다. 문장에서 밝혔는지 봅니다.",
            )

        weak = set().union(
            *(
                facts[i]
                for i in observed
                if items[i]["grade"] is not None and items[i]["grade"] <= 1
            )
        )
        if not weak:
            k3 = _check("K3", None, [], "약한 수요 근거가 없습니다.", "not_applicable")
            k4 = _check("K4", None, [], "공개할 약한 수요 근거가 없습니다.", "not_applicable")
        else:
            misused = weak & reasons
            k3 = _check(
                "K3",
                _ratio_points("K3", 1 - len(misused) / len(weak)),
                misused,
                "약한 수요 근거 중 장점 문장에 쓰지 않은 비율입니다. 근거는 장점에 쓴 것입니다.",
            )
            shown = weak & disclosed
            k4 = _check(
                "K4",
                _ratio_points("K4", len(shown) / len(weak)),
                weak - shown,
                "약한 수요 근거를 위험·확인 조건에 밝혔는지 봅니다. 근거는 밝히지 않은 것입니다.",
            )

        checks = [k1, k2, k3, k4]
        scored.append((rank, code, checks))
        for check in checks:
            if check.points is None or check.points / check.weight >= ISSUES[check.item][0]:
                continue
            _, slug, target, kind, comment, suggestion = ISSUES[check.item]
            issue = ReviewIssue(
                issue_id=f"customer:{slug}-{code}",
                industry_code=code,
                target=target,
                kind=kind,
                comment=candidate.industry_name + comment,
                fact_ids=check.fact_ids[:5],
                suggested_check=suggestion,
            )
            issues.append((check.points / check.weight, rank, issue))
    issues.sort(key=lambda x: (x[0], x[1]))
    return scored, [issue for _, _, issue in issues][:4]


def finish(scored, code_issues, fit_checks, model_issues, citable):
    """모델 점수(K6)를 합쳐 후보 점수·판정·지적을 확정합니다.

    model_issues가 None이면 모델 제출 실패입니다. 그래도 코드 평가와, 형식이 맞았던
    마지막 제출의 점수 칸(fit_checks)은 남깁니다.
    """
    fit = {}
    for check in fit_checks:
        ids = set(check.fact_ids) & citable
        # 근거 없는 점수는 확인 불가로 바꿉니다(환각 방지).
        fit[check.industry_code] = (check.points if ids else None, ids, check.reason)
    candidates = []
    for rank, code, checks in scored:
        points, ids, reason = fit.get(code, (None, set(), "모델 평가가 없습니다."))
        k6 = _check("K6", points, ids, reason, "unknown")
        all_checks = [*checks, k6]
        applicable = sum(c.weight for c in all_checks if c.status == "observed")
        points = sum(c.points or 0 for c in all_checks)
        candidates.append(
            CustomerCandidateScore(
                industry_code=code,
                rank=rank,
                checks=all_checks,
                points=points,
                applicable_weight=applicable,
                ratio=points / applicable if applicable else None,
            )
        )
    ratios = [c.ratio for c in candidates if c.ratio is not None]
    ratio = sum(ratios) / len(ratios) if ratios else None
    no_demand = [
        c.industry_code
        for c in candidates
        if c.rank <= 3 and c.checks[0].status == "observed" and c.checks[0].points == 0
    ]
    zero = any(k.points == 0 for c in candidates for k in c.checks)
    if not candidates or ratio is None:
        verdict, basis = "conditional", "평가할 후보 점수가 없어 조건부로 둡니다."
    elif no_demand or ratio <= OPPOSE:
        verdict, basis = (
            "oppose",
            (
                "상위 세 후보 중 손님 수요 근거가 전혀 없는 업종이 있습니다."
                if no_demand
                else "후보 평균 득점률이 반대 기준 이하입니다."
            ),
        )
    elif ratio >= AGREE and not zero:
        verdict, basis = "agree", "후보 평균 득점률이 동의 기준 이상이고 0점 항목이 없습니다."
    else:
        verdict, basis = "conditional", "동의 기준에 못 미치거나 0점 항목이 있습니다."
    code_ids = {issue.issue_id for issue in code_issues}
    extra = [issue for issue in model_issues or [] if issue.issue_id not in code_ids]
    rubric = CustomerRubric(
        candidates=candidates,
        ratio=ratio,
        verdict_basis=basis,
        model_status="failed" if model_issues is None else "completed",
    )
    return verdict, (code_issues + extra)[:4], rubric

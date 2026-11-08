"""손님 평가자의 모델 입력을 만듭니다. 채점 규칙은 domain/customer_rubric.py에 있습니다."""

from app.application.ports.storage import open_stores
from app.domain.customer_rubric import NAMES, cited_ids, score_candidates
from app.shared.canonical import canonical_json

PROMPT = """손님 편 평가자입니다. 질문은 하나입니다.
"손님 입장에서 볼 때, 이 업종을 추천한 것과 그 근거가 잘 맞는가?"
업종마다 장점·위험·확인 조건 문장과 거기 인용된 fact를 읽고, 그 근거가 가리키는 손님
(누가·언제·얼마나 지나가는지)이 이 업종을 찾을 손님과 맞는지 판단하세요.
서버가 이미 코드로 채점한 항목(code_checks: 수요 근거량·모집단 일치·장점 문장 방향·약점 공개)은
다시 채점하거나 같은 내용을 지적하지 마세요. 판정(verdict)도 서버가 다시 계산합니다.

[읽는 관점]
- 특정 손님층을 가정하지 말고 일반 손님의 눈으로 읽으세요.
- 학교·주거지·오피스 같은 주변 성격, 상주·직장 인구, 소득·성별을 fact 없이 추정하지 마세요.
- 통행량은 방문자 수가 아닙니다. 지나가는 사람이 많다는 것을 곧 손님이 온다는 뜻으로 쓰지 마세요.
- 공간·면적·층·설비·공사 조건(검토 전 공간 초안 포함)은 임차인 평가자 몫입니다.
  그런 문장은 손님 지적이나 점수 근거로 쓰지 마세요.

[fit_checks: candidates의 업종마다 하나씩, points는 아래 다섯 값 중 하나]
points 40: 추천과 인용된 근거가 손님 입장에서 잘 맞고, 손님 쪽 한계도 밝혔다.
points 30: 대체로 맞지만 작은 비약이 있다.
points 20: 근거가 이 업종 손님과 연결이 약한 일반론이다.
points 10: 근거가 가리키는 손님층·시간대가 이 업종 손님과 어긋나는데 그 차이를 다루지 않았다.
points 0: 근거와 반대로 추천했거나, 근거 없이 손님이 올 것이라 단정했다.
points=null: 장점 문장이 없거나 판단할 근거 fact가 없을 때. 모르면 null로 남기세요.
점수를 매기면 판단에 쓴 fact_ids를 하나 이상 붙이세요. 없으면 points는 null입니다.
reason은 한두 문장, 숫자(연령대·층수 포함) 없이 씁니다.

[issues]
remaining_issue_slots 개까지만 추천과 근거가 손님 입장에서 어긋나는 점을 지적하세요.
남길 것이 없으면 빈 목록입니다. issue_id는 지적마다 서로 달라야 합니다.
위험·확인 조건 문장에 이미 밝힌 손님 쪽 약점은 다시 지적하지 마세요.
단 같은 근거를 장점에도 써서 문장끼리 어긋나면 지적하세요.
지적마다 실제 fact_id를 붙이고, comment·suggested_check에 숫자(연령대·층수 포함)를 쓰지 마세요.

읽기 도구는 꼭 필요할 때만 최대 세 번 쓰고 submit_review로 한 번 제출하세요.
실패한 조회를 동의로 해석하지 마세요."""


def load(scope, draft):
    """점수표 문항·문항별 fact·인용 가능 여부를 한 번에 읽습니다."""
    with open_stores(scope) as st:
        summary = st.scores.score_rows(draft.score_snapshot_id)
        if summary is None:
            raise ValueError("초안의 점수표가 없습니다.")
        item_facts = st.scores.item_fact_ids(draft.score_snapshot_id)
        citable = st.facts.citable_fact_ids(scope.request_id, scope.snapshot_id)
    rows = {row["code"]: row for row in summary}
    return rows, item_facts, citable


def code_checks(scope, draft):
    """Top5 후보마다 K1~K4를 계산하고 코드 지적 후보를 돌려줍니다."""
    rows, item_facts, citable = load(scope, draft)
    scored, issues = score_candidates(draft.top5[:5], rows, item_facts, citable)
    return scored, issues, citable


def packet(scope, draft, scored, issues):
    """모델에는 K6 판단에 필요한 Top5 문장·인용 fact만 넘깁니다."""
    from app.application.report import fact_rows

    candidates = []
    ids = set()
    for candidate in draft.top5[:5]:
        segments = {
            "reasons_segments": candidate.reasons_segments,
            "risks_segments": candidate.risks_segments,
            "confirmation_conditions_segments": candidate.confirmation_conditions_segments,
        }
        for value in segments.values():
            ids |= cited_ids(value)
        candidates.append(
            {"industry_code": candidate.industry_code, "industry_name": candidate.industry_name}
            | {k: [s.model_dump(mode="json") for s in v] for k, v in segments.items()}
        )
    facts = []
    for fid, row in sorted(fact_rows(scope, ids).items()):
        fact = {
            "fact_id": fid,
            "source": row.source,
            "metric": row.metric,
            "unit": row.unit,
            "industry_code": row.industry_code,
            "value": row.value,
        }
        if len(canonical_json(fact["value"])) > 500:
            fact.pop("value")
            fact["read_required"] = True
        facts.append(fact)
    return {
        "draft_id": draft.report_id,
        "candidates": candidates,
        "facts": facts,
        "code_checks": [
            {
                "industry_code": code,
                "checks": [
                    {"item": NAMES[c.item], "points": c.points, "weight": c.weight} for c in checks
                ],
            }
            for _, code, checks in scored
        ],
        "remaining_issue_slots": 4 - len(issues),
    }

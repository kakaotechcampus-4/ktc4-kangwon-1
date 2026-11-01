"""임차인이 받은 초안과 운영 근거를 비교하도록 제한된 크기의 패킷을 만듭니다."""

import json

from app.canonical import canonical_json
from app.db.connection import connect

from .aliases import encode
from .landlord import _facts
from .report import ReportInvalid, fact_rows

PERSONA = (
    "임차인·창업자 편입니다. 후보들의 운영·공사 전제와 초안 문장을 검토하세요. "
    "continuity·competition 근거로 사업계획과 차별화의 실행 조건을 먼저 확인하고, "
    "공간·설비 근거와 확정값을 대조하세요. 자료가 없으면 모른다고 남기고 지적을 만들지 마세요. "
    "확정 층·면적·설비 상태를 다시 묻지 마세요. 설치 가능은 공사 완료가 아니며 "
    "설치 불가는 단순한 현재 부재와 다릅니다. space_rules는 코드가 이미 판단한 결과이므로 "
    "층·필수 및 선호 설비의 제외·순위 보정은 반복 지적하거나 재채점하지 마세요. "
    "면적은 운영 추정입니다. 실제 장비·재고·작업 배치와 반입 조건, 필요한 공사 범위·허용·책임을 "
    "검토하되 비용·매출·개인의 실패 확률을 추정하지 마세요. "
    "기본은 target=condition, kind=action_condition입니다. "
    "candidates로 실제 받은 운영·공사 문장이 관측 근거와 충돌할 때만 "
    "target=claim, kind=factual_error를 쓰고, 어떤 문장이 왜 틀렸는지 짚으세요. "
    "받지 않은 문장의 단정·누락을 주장하지 마세요. "
    "원천·기간·공간 범위·근거 누락 검증과 점수·L 재채점은 심사관 몫입니다. "
    "손님 수요와 임대 지속성은 다른 평가자의 몫입니다. "
    "개폐업·경쟁 수치는 운영 가정을 점검할 신호이지 특정 임차인의 성패가 아닙니다. "
    "이미 충분히 적힌 확인 조건을 반복하지 말고 같은 원인을 묶으세요. "
    "필요한 현장 배치 확인→공사 허용·책임 협의→견적·관할기관 확인만 제시하세요. "
    "facts와 evidence의 관측 근거를 먼저 쓰고 read_required·omitted_fact_ids는 필요할 때 "
    "get_facts로 확인하세요. 일반 조회 limit=32 이하이며 fact_ids와 조건 필터는 섞지 마세요. "
    "제공 근거가 충분하면 읽기 없이 제출해도 됩니다. 확인 과제·근거 부족은 conditional, "
    "중요한 오류·과제가 없으면 agree, 관측 근거로 핵심 운영 전제가 명백히 충돌할 때만 oppose입니다."
)
MAX_PACKET_CHARS = 12000
SEGMENTS = ("reasons_segments", "risks_segments", "confirmation_conditions_segments")
GROUPS = {
    "continuity": (
        ("business_lifecycle", "recent_year_close_rate"),
        ("business_lifecycle", "net_change_rate"),
        ("business_lifecycle", "turnover_rate"),
        ("business_lifecycle", "oldest_year_close_rate"),
    ),
    "competition": (
        ("commercial_area", "store_count"),
        ("commercial_area", "competition_index"),
    ),
    "space": (("industry_profile", "space_fit"),),
}


def review_packet(scope, draft):
    payload = draft.model_dump(mode="json")
    candidates = payload.get("top5", [])[:5]
    codes = [c["industry_code"] for c in candidates]
    # 요청·스냅샷 격리와 현재 공간 비교 선택은 기존 읽기 경로를 재사용합니다.
    rows = _facts(scope, codes)
    with connect(scope.path) as db:
        stored = db.execute(
            "SELECT summary_json FROM score_snapshots WHERE score_snapshot_id=? "
            "AND request_id=? AND snapshot_id=?",
            (payload["score_snapshot_id"], scope.request_id, scope.snapshot_id),
        ).fetchone()
    if stored is None:
        raise ValueError("초안의 점수표가 없습니다.")
    spaces = {r["code"]: r.get("space", {}) for r in json.loads(stored[0])}
    observed = {r["fact_id"]: r for r in rows if r["status"] == "observed" and r["citable"]}
    evidence = {}
    for code in codes:
        evidence[code] = {
            name: {
                "fact_ids": [
                    r["fact_id"]
                    for metric in metrics
                    for r in observed.values()
                    if r["industry_code"] in (None, code) and (r["source"], r["metric"]) == metric
                ]
            }
            for name, metrics in GROUPS.items()
        }
    packet = {
        "draft_id": payload["report_id"],
        "candidates": [
            {
                "industry_code": c["industry_code"],
                "industry_name": c.get("industry_name"),
                **{key: c.get(key, []) for key in SEGMENTS},
                "space_rules": spaces.get(c["industry_code"], {}),
            }
            for c in candidates
        ],
        "evidence": evidence,
        "note": (
            "space_rules는 재채점하지 않을 코드 판정이며 인용 fact가 아닙니다. "
            "evidence의 빈 목록은 확보한 관측 근거가 없다는 뜻이지 수치가 영이라는 뜻이 아닙니다. "
            "read_required 또는 omitted_fact_ids의 원문은 get_facts로 조회하세요."
        ),
        "facts": [],
        "fact_defaults": {"status": "observed", "citable": True},
        "spatial_scopes": {},
    }
    cited = list(
        dict.fromkeys(
            s["fact_id"]
            for c in candidates
            for key in SEGMENTS
            for s in c.get(key, [])
            if s.get("type") == "fact"
        )
    )
    cited_rows = fact_rows(scope, set(cited))
    observed.update(
        {fid: r for fid, r in cited_rows.items() if r["status"] == "observed" and r["citable"]}
    )
    order = [fid for fid, r in observed.items() if r["source"] == "user"]
    # 한 후보의 상세 자료가 다른 후보의 지속성·경쟁 근거를 밀어내지 않게 배치합니다.
    for index in range(
        max(
            (len(g["fact_ids"]) for groups in evidence.values() for g in groups.values()), default=0
        )
    ):
        for name in GROUPS:
            for code in codes:
                ids = evidence[code][name]["fact_ids"]
                if index < len(ids):
                    order.append(ids[index])
    order += [fid for fid in cited if fid in observed]
    scopes = {}
    for fid in dict.fromkeys(order):
        row = observed[fid]
        spatial = row["spatial_scope_json"]
        ref = scopes.setdefault(spatial, f"scope_{len(scopes)}")
        packet["spatial_scopes"][ref] = json.loads(spatial)
        fact = {
            key: row[key]
            for key in ("fact_id", "industry_code", "source", "metric", "period", "unit")
        }
        fact.update(spatial_scope_ref=ref, value=json.loads(row["value_json"]))
        packet["facts"].append(fact)
    packet = encode(scope, packet)
    _trim_packet(packet)
    return packet


def _trim_packet(packet):
    """공간·지속성·경쟁 순으로 보존하고 사용자 확정값은 그 뒤까지 남깁니다."""
    packet["omitted_fact_ids"] = []

    def priority(fact):
        if fact["source"] == "user":
            return 0
        for level, group in enumerate(("space", "continuity", "competition"), 1):
            if (fact["source"], fact["metric"]) in GROUPS[group]:
                return level
        return 4

    # 낮은 우선순위의 메타데이터 때문에 높은 우선순위의 값까지 지우지 않습니다.
    for level in (4, 3, 2, 1, 0):
        cards = [f for f in reversed(packet["facts"]) if priority(f) == level]
        for fact in cards:
            if len(canonical_json(packet)) <= MAX_PACKET_CHARS:
                return
            fact.pop("value", None)
            fact["read_required"] = True
        for fact in cards:
            if len(canonical_json(packet)) <= MAX_PACKET_CHARS:
                return
            packet["omitted_fact_ids"].append(fact["fact_id"])
            packet["facts"].remove(fact)
    if len(canonical_json(packet)) > MAX_PACKET_CHARS:
        raise ValueError("임차인 패킷 상한 안에서 후보 문장·참조를 보존할 수 없습니다.")


def validate_issue(issue, packet):
    if (issue.target, issue.kind) == ("condition", "action_condition"):
        return
    if (issue.target, issue.kind) == ("claim", "factual_error") and any(
        c["industry_code"] == issue.industry_code
        and any(
            s.get("type") == "text" and s.get("text") for key in SEGMENTS for s in c.get(key, [])
        )
        for c in packet["candidates"]
    ):
        return
    raise ReportInvalid("임차인은 받은 운영·공사 문장의 오류 또는 실행 확인 조건만 제출하세요.")

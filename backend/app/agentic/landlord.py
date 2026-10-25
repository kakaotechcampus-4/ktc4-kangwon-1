"""임대인 검토에 필요한 기존 사실을 새 수집 없이 제한된 크기로 제공합니다."""

import json

from app.canonical import canonical_json
from app.db.connection import connect
from app.industries.catalog import INDUSTRIES
from app.local_data.provenance import expand_spatial_scope, validate_snapshot

from .aliases import encode

PERSONA = (
    "임대인 편입니다. 공실 해소와 임대 지속성을 우선 검토하세요. "
    "landlord_context의 업종별 근거로 영업 지속성·임차 수요·임대인 부담을 검토한 뒤 "
    "공간 조건을 확인하세요. 제공 근거가 충분하면 읽기 도구 없이 제출해도 됩니다. "
    "개폐업 추세는 상권 업종의 영업 지속성에 관한 간접 근거이며 특정 임차인의 "
    "임대료 지급 능력·계약 유지 기간을 입증하지 않습니다. 자료의 기간·공간 범위를 "
    "함께 확인하고 미확인을 수요 없음이나 임대 부적합으로 단정하지 마세요. "
    "임대료·공실 기간·공사비가 없으면 임대수익을 추정하지 말고 확인 조건으로 남기세요. "
    "지적과 의미가 맞는 관측 fact만 인용하고, 자료 상태 진단은 관측 수치의 근거가 아닙니다. "
    "공간 요건 경고의 반복보다 후보 판단에 영향을 주는 핵심 확인 사항을 남기세요. "
    "예약·기업 거래 중심 업종에 층·보행 통행 조건을 일괄 적용하지 마세요."
)
MAX_PACKET_CHARS = 12000
GROUPS = {
    "continuity": (
        ("business_lifecycle", "recent_year_close_rate"),
        ("business_lifecycle", "net_change_rate"),
        ("business_lifecycle", "store_exposure"),
    ),
    "demand": (
        ("floating_population", "pattern_fit_index"),
        ("resident_population", "target_age_index"),
        ("worker_population", "target_age_index"),
        ("floating_population", "yoy_change"),
        ("floating_population", "day_fit_index"),
    ),
    "competition": (("commercial_area", "store_count"), ("commercial_area", "competition_index")),
    "space": (("industry_profile", "space_fit"),),
}


def _facts(scope, codes):
    validate_snapshot(scope)
    with connect(scope.path) as db:
        rows = [
            dict(r)
            for r in db.execute(
                "SELECT f.*,EXISTS(SELECT 1 FROM local_fact_lineage l WHERE l.fact_id=f.fact_id) "
                "AS local_lineage FROM facts f WHERE f.request_id=? AND f.snapshot_id=? "
                "AND (f.industry_code IS NULL OR f.industry_code IN ("
                + ",".join("?" for _ in codes)
                + ")) AND (f.metric!='space_fit' OR EXISTS(SELECT 1 FROM space_fit_current c "
                "WHERE c.request_id=f.request_id AND c.snapshot_id=f.snapshot_id "
                "AND c.fact_id=f.fact_id)) ORDER BY f.fact_id",
                [scope.request_id, scope.snapshot_id, *codes],
            )
        ]
    expand_spatial_scope(scope, rows)
    return rows


def review_packet(scope, draft):
    candidates = draft.top5[:5]
    rows = _facts(scope, [c.industry_code for c in candidates])
    groups = {}
    for candidate in candidates:
        code = candidate.industry_code
        groups[code] = {}
        for name, metrics in GROUPS.items():
            matching = [
                r
                for r in rows
                if r["industry_code"] in (None, code) and (r["source"], r["metric"]) in metrics
            ]
            matching.sort(
                key=lambda r: (
                    metrics.index((r["source"], r["metric"])),
                    r["industry_code"] is None,
                    r["fact_id"],
                )
            )
            groups[code][name] = matching
    context = {
        "review_order": ["영업 지속성", "임차 수요", "임대인 부담", "공간 확인"],
        "missing_inputs": ["임대료", "공실 기간", "공사비"],
        "evidence": {
            code: {
                name: {
                    "observed_count": sum(r["status"] == "observed" and r["citable"] for r in rs),
                    "unknown_count": sum(r["status"] == "unknown" for r in rs),
                    "fact_ids": [],
                }
                for name, rs in named.items()
            }
            for code, named in groups.items()
        },
        "availability_note": (
            "건수는 현재 스냅샷의 자료 상태이며 인용용 fact가 아닙니다. "
            "관측 건수가 없으면 근거를 확보하지 못한 상태이지 수요·점포가 없다는 뜻이 아닙니다. "
            "관측 건수보다 제공 fact가 적으면 공간 상한으로 생략된 자료는 get_facts로 확인하세요."
        ),
    }
    packet = {
        "draft_id": draft.report_id,
        "top5": [
            {
                "industry_name": INDUSTRIES[c.industry_code],
                **{
                    key: getattr(c, key)
                    for key in ("industry_code", "badge", "coverage", "demand_coverage", "L_status")
                },
            }
            for c in candidates
        ],
        "landlord_context": context,
        "limitations_segments": [
            item.model_dump(mode="json") for item in getattr(draft, "limitations_segments", ())
        ],
        "spatial_scopes": {},
        "facts": [],
    }
    supplied = set()
    scopes = {}

    def add(row, group_ids=None):
        fid = row["fact_id"]
        if fid in supplied:
            if group_ids is not None:
                group_ids.append(fid)
            return
        if row["status"] != "observed" or not row["citable"]:
            return
        spatial = row["spatial_scope_json"]
        new_scope = spatial not in scopes
        ref = scopes.setdefault(spatial, f"scope_{len(scopes)}")
        packet["spatial_scopes"][ref] = json.loads(spatial)
        fact = {
            key: row[key]
            for key in ("fact_id", "source", "metric", "industry_code", "unit", "period", "status")
        }
        fact.update(value=json.loads(row["value_json"]), citable=True, spatial_scope_ref=ref)
        packet["facts"].append(fact)
        if group_ids is not None:
            group_ids.append(fid)
        if len(canonical_json(encode(scope, packet))) <= MAX_PACKET_CHARS:
            supplied.add(fid)
            return
        packet["facts"].pop()
        if group_ids is not None:
            group_ids.pop()
        if new_scope:
            packet["spatial_scopes"].pop(ref)
            scopes.pop(spatial)

    for row in rows:
        if row["source"] == "user":
            add(row)
    # 한 후보가 지면을 독점하지 않도록 같은 우선순위의 자료를 후보별로 교차 배치합니다.
    for name, index in (
        ("continuity", 0),
        ("demand", 0),
        ("competition", 0),
        ("continuity", 1),
        ("space", 0),
        ("continuity", 2),
        ("demand", 1),
        ("demand", 2),
    ):
        for code, named in groups.items():
            observed = [r for r in named[name] if r["status"] == "observed" and r["citable"]]
            if index < len(observed):
                add(observed[index], context["evidence"][code][name]["fact_ids"])
    encoded = encode(scope, packet)
    if len(canonical_json(encoded)) > MAX_PACKET_CHARS:
        raise ValueError("임대인 평가 패킷 상한을 초과했습니다.")
    return encoded

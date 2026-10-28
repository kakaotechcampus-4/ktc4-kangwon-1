"""심사관이 초안 문장과 근거를 대조하도록 문장·문항 근거·근거 카드를 제한된 크기로 제공합니다."""

import json
import re

from app.canonical import canonical_json
from app.db.connection import connect

from .aliases import encode
from .report import fact_rows

PERSONA = (
    "심사관입니다. 점수·순위는 바꾸지 않고 보고서 문장과 근거가 맞는지 검토합니다. "
    "candidates의 상위 후보마다 reasons·risks·confirmation_conditions 문장을 하나씩 보고 "
    "근거·출처·기간 범위·중복의 네 칸을 확인하세요. "
    "checks를 먼저 보세요. checks.uncited는 fact 슬롯이 없는 문장의 후보·칸·순번이고 "
    "순번은 칸 안 문장을 영부터 센 값입니다. 그 후보 score_items에서 문장을 뒷받침할 "
    "fact_id를 골라 missing_evidence로 지적하세요. checks.shared_sources는 같은 원천 "
    "지표를 쓰는 점수 문항 묶음이니 중복 칸 판단에 참고하세요. "
    "checks를 본 뒤에도 위험 문장마다 인용 fact의 출처·기간 범위 칸을 확인하세요. "
    "근거 칸: 문장에 fact 슬롯이 없으면 그 후보 score_items에서 문장을 뒷받침할 fact_id를 골라 "
    "target=claim, kind=missing_evidence로 지적하세요. "
    "출처 칸: 인용 fact의 source·metric이 문장 내용과 다르면 scope_mismatch입니다. "
    "기간 범위 칸: fact의 period·spatial_scopes가 문장이 말하는 시점·범위와 "
    "실제로 다를 때만 scope_mismatch입니다. 문장이 기간·범위를 근거보다 "
    "덜 자세히 썼을 뿐 어긋나지 않으면 kind=action_condition으로 남기세요. "
    "중복 칸: 같은 원천 지표가 두 문항에서 함께 점수가 되어 같은 현상을 두 번 세면 "
    "target=score, kind=duplicate_score입니다. "
    "확인하지 못한 칸은 kind=action_condition으로 남기세요. "
    "공간·운영 적합성은 창업자, 손님 수요는 손님, 임대 지속성은 임대인 평가자의 몫이므로 "
    "공간 요건 경고를 되풀이하지 마세요. unknown 이유와 L 중복 채점은 서버가 검사합니다. "
    "facts와 score_items의 관측 fact만 인용하고 "
    "제공 근거가 충분하면 읽기 도구 없이 제출해도 됩니다. "
    "get_facts는 꼭 필요한 근거만 골라 한 번에 서른두 개 이하로 요청하고, "
    "거절되면 같은 요청을 반복하지 말고 나눠서 다시 요청하세요. "
    "comment와 suggested_check에 숫자 문자가 하나라도 있으면 서버가 거절합니다. "
    "연도·분기, 값, 업종 코드, 문항 이름, fact_id 별칭에도 숫자가 섞여 있으니 "
    "문장에 옮겨 쓰지 마세요. 후보는 industry_code 칸, 근거는 fact_ids 칸이 가리키므로 "
    "문장에서는 '이 후보', '인용 근거'로 쓰고 "
    "기간은 '최근 한 해', '가장 이른 해', '관측 기간 전체'처럼 말로 쓰세요. "
    "제출 전에 지적마다 fact_ids가 있는지 확인하세요. "
    "지적이 없으면 agree, 지적이나 확인 조건이 있으면 conditional, "
    "인용 근거가 문장과 반대 방향이면 oppose입니다."
)
MAX_PACKET_CHARS = 12000
SENTENCE_END = re.compile(r"(?<=[.!?])")
MAX_VALUE_CHARS = 500
ITEMS = ("D1", "D2", "D3", "D4", "C1", "C4", "S1", "S2", "S3", "S4", "L")
SEGMENTS = ("reasons_segments", "risks_segments", "confirmation_conditions_segments")
SUMMARY = ("code_points", "B", "H", "coverage", "badge", "L_status")
SCORE_COLUMNS = ("item", "status", "grade", "points", "fact_ids")
FACT_COLUMNS = (
    "fact_id",
    "industry_code",
    "source",
    "metric",
    "period",
    "unit",
    "spatial_scope_ref",
    "value",
)
NOTE = (
    "score_items와 facts는 score_columns·fact_columns 순서의 행입니다. "
    "facts의 value가 null이거나 omitted_fact_ids에 있으면 get_facts로 원문을 확인하세요."
)


def _table(rows, columns):
    return [[row.get(column) for column in columns] for row in rows]


def _score_items(scope, score_snapshot_id, codes):
    with connect(scope.path) as db:
        rows = db.execute(
            "SELECT industry_code,item,status,grade,points,fact_ids_json FROM scores "
            "WHERE score_snapshot_id=? AND industry_code IN (" + ",".join("?" for _ in codes) + ")",
            [score_snapshot_id, *codes],
        ).fetchall()
    found = {code: {} for code in codes}
    for code, item, status, grade, points, fact_ids in rows:
        found[code][item] = {
            "item": item,
            "status": status,
            "grade": grade,
            "points": points,
            "fact_ids": json.loads(fact_ids),
        }
    return {code: [items[i] for i in ITEMS if i in items] for code, items in found.items()}


def _cited(segments):
    return [s["fact_id"] for s in segments if s.get("type") == "fact"]


def _sentences(segments):
    found, text, cited = [], "", False
    for segment in segments:
        if segment.get("type") == "fact":
            cited = True
            continue
        parts = SENTENCE_END.split(segment.get("text", ""))
        for part in parts[:-1]:
            text += part
            found.append((text.strip(), cited))
            text, cited = "", False
        text += parts[-1]
    if text.strip():
        found.append((text.strip(), cited))
    return found


def _uncited(candidates):
    groups = [(c["industry_code"], key, c.get(key, [])) for c in candidates for key in SEGMENTS]
    return [
        {"industry_code": code, "field": key, "sentence": index}
        for code, key, segments in groups
        for index, (_, cited) in enumerate(_sentences(segments))
        if not cited
    ]


def _shared_sources(codes, items, rows, allowed):
    found = []
    for code in codes:
        groups = {}
        for entry in items[code]:
            keys = {
                (rows[f]["source"], rows[f]["metric"]) for f in entry["fact_ids"] if f in allowed
            }
            for key in sorted(keys):
                groups.setdefault(key, []).append(entry["item"])
        found += [
            {"industry_code": code, "source": source, "metric": metric, "items": names}
            for (source, metric), names in sorted(groups.items())
            if len(names) >= 2
        ]
    return found


def review_packet(scope, draft):
    payload = draft.model_dump(mode="json")
    top5 = payload.get("top5", [])[:5]
    codes = [c["industry_code"] for c in top5]
    items = _score_items(scope, payload["score_snapshot_id"], codes) if codes else {}
    order = []
    for candidate in top5:
        for key in SEGMENTS:
            order += _cited(candidate.get(key, []))
        order += candidate.get("fact_ids", [])
    for key in ("summary_segments", "limitations_segments"):
        order += _cited(payload.get(key, []))
    for item in ITEMS:
        for code in codes:
            order += next((e["fact_ids"] for e in items[code] if e["item"] == item), [])
    order = list(dict.fromkeys(order))
    rows = fact_rows(scope, set(order))
    usable = [f for f in order if rows[f]["status"] == "observed" and rows[f]["citable"]]
    allowed = set(usable)
    scopes = {}
    facts = []
    for fid in usable:
        row = rows[fid]
        fact = {key: row[key] for key in FACT_COLUMNS[:6]}
        fact["spatial_scope_ref"] = scopes.setdefault(
            row["spatial_scope_json"], f"scope_{len(scopes)}"
        )
        if len(row["value_json"]) <= MAX_VALUE_CHARS:
            fact["value"] = json.loads(row["value_json"])
        facts.append(fact)
    packet = {
        "draft_id": draft.report_id,
        "note": NOTE,
        "score_columns": list(SCORE_COLUMNS),
        "fact_columns": list(FACT_COLUMNS),
        "candidates": [
            {
                "industry_code": c["industry_code"],
                "industry_name": c.get("industry_name"),
                **{key: c.get(key) for key in SUMMARY},
                **{key: c.get(key, []) for key in SEGMENTS},
                "fact_ids": [f for f in c.get("fact_ids", []) if f in allowed],
                "score_items": [
                    dict(e, fact_ids=[f for f in e["fact_ids"] if f in allowed])
                    for e in items[c["industry_code"]]
                ],
            }
            for c in top5
        ],
        "summary_segments": payload.get("summary_segments", []),
        "limitations_segments": payload.get("limitations_segments", []),
        "spatial_scopes": {ref: json.loads(raw) for raw, ref in scopes.items()},
        "facts": facts,
        "omitted_fact_ids": [],
        "checks": {
            "uncited": _uncited(top5),
            "shared_sources": _shared_sources(codes, items, rows, allowed),
        },
    }
    packet = encode(scope, packet)
    for candidate in packet["candidates"]:
        candidate["score_items"] = _table(candidate["score_items"], SCORE_COLUMNS)
    packet["facts"] = _table(packet["facts"], FACT_COLUMNS)
    value = FACT_COLUMNS.index("value")

    def oversized():
        return len(canonical_json(packet)) > MAX_PACKET_CHARS

    for fact in reversed(packet["facts"]):
        if not oversized():
            break
        fact[value] = None
    while oversized() and packet["facts"]:
        packet["omitted_fact_ids"].append(packet["facts"].pop()[0])
    if oversized():
        raise ValueError("심사관 평가 패킷 상한 안에서 초안 문장을 보존할 수 없습니다.")
    return packet

"""모델 경계에서만 짧은 요청별 별칭을 사용하고 저장 식별자는 보존합니다."""

import json
from hashlib import sha256

from app.db.connection import connect

SINGLES = {"fact_id", "distance_fact_id"}
LISTS = {"fact_ids", "reason_fact_ids", "selection_fact_ids"}


def _walk(value, translate, key=None):
    if key in SINGLES and isinstance(value, str):
        return translate(value)
    if key in LISTS and isinstance(value, list):
        return [translate(item) for item in value]
    if key in LISTS and isinstance(value, dict):
        return {name: translate(item) for name, item in value.items()}
    if isinstance(value, dict):
        return {name: _walk(item, translate, name) for name, item in value.items()}
    if isinstance(value, list):
        return [_walk(item, translate) for item in value]
    return value


def encode(scope, value):
    with connect(scope.path) as db:

        def alias(fid):
            existing = db.execute(
                "SELECT alias FROM fact_aliases WHERE request_id=? AND alias=?",
                (scope.request_id, fid),
            ).fetchone()
            if existing:
                return existing[0]
            row = db.execute(
                "SELECT alias FROM fact_aliases WHERE request_id=? AND fact_id=?",
                (scope.request_id, fid),
            ).fetchone()
            if row:
                return row[0]
            if not db.execute(
                "SELECT 1 FROM facts WHERE request_id=? AND snapshot_id=? AND fact_id=?",
                (scope.request_id, scope.snapshot_id, fid),
            ).fetchone():
                raise ValueError("요청에 없는 fact를 별칭으로 내보낼 수 없습니다.")
            counter = 0
            while True:
                short = sha256(f"{fid}:{counter}".encode()).hexdigest()[:8]
                added = db.execute(
                    "INSERT OR IGNORE INTO fact_aliases VALUES(?,?,?)",
                    (scope.request_id, short, fid),
                )
                if added.rowcount:
                    return short
                counter += 1

        return _walk(value, alias)


def encode_messages(scope, messages):
    output = []
    for message in messages:
        item = dict(message)
        if isinstance(item.get("content"), str):
            try:
                body = json.loads(item["content"])
            except ValueError:
                pass
            else:
                item["content"] = json.dumps(encode(scope, body), ensure_ascii=False)
        output.append(item)
    return output


def decode(scope, value):
    with connect(scope.path) as db:

        def original(reference):
            if not isinstance(reference, str):
                raise ValueError("fact 별칭은 문자열이어야 합니다.")
            row = db.execute(
                "SELECT f.fact_id FROM facts f LEFT JOIN fact_aliases a "
                "ON a.fact_id=f.fact_id AND a.request_id=f.request_id "
                "WHERE f.request_id=? AND f.snapshot_id=? AND (f.fact_id=? OR a.alias=?)",
                (scope.request_id, scope.snapshot_id, reference, reference),
            ).fetchone()
            if not row:
                visible = (
                    reference if len(reference) == 8 and reference.isalnum() else "미등록 식별자"
                )
                raise ValueError("존재하지 않는 fact: " + visible)
            return row[0]

        return _walk(value, original)


def decode_report(scope, arguments):
    """미존재 인용은 해당 문장/참조만 제거하고 나머지 보고서를 검증합니다."""
    warnings = []
    report = arguments.get("report", {})
    if not isinstance(report, dict):
        return arguments, warnings

    def clean(container):
        result = {}
        for key, value in container.items():
            if key.endswith("_segments") and isinstance(value, list):
                segments = []
                for segment in value:
                    try:
                        segments.append(decode(scope, segment))
                    except ValueError as exc:
                        warnings.append(str(exc) + "; 해당 문장을 제외했습니다.")
                result[key] = segments
            elif key == "fact_ids" and isinstance(value, list):
                result[key] = []
                for fid in value:
                    try:
                        result[key].extend(decode(scope, {key: [fid]})[key])
                    except ValueError as exc:
                        warnings.append(str(exc))
            elif key in {"candidates", "excluded_candidates"} and isinstance(value, list):
                result[key] = [
                    clean(candidate) if isinstance(candidate, dict) else candidate
                    for candidate in value
                ]
            else:
                result[key] = value
        return result

    cleaned = clean(report)
    if warnings:
        segments = cleaned.setdefault("limitations_segments", [])
        if isinstance(segments, list):
            segments.append({"type": "text", "text": "미등록 근거를 인용한 문장을 제외했습니다."})
    return decode(scope, arguments | {"report": cleaned}), warnings

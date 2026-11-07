"""모델 경계에서만 짧은 요청별 별칭을 사용하고 저장 식별자는 보존합니다."""

import json
import re

from app.application.ports.storage import open_stores

SINGLES = {"fact_id", "distance_fact_id"}
LISTS = {"fact_ids", "reason_fact_ids", "selection_fact_ids"}
QUARTER_RANGE = re.compile(r"\d{4}[1-4](~\d{4}[1-4])?")
PERIOD_LABEL_ROLES = frozenset({"examiner"})


def period_label(period):
    if not QUARTER_RANGE.fullmatch(period):
        return period
    start, _, end = period.partition("~")
    label = f"{start[:4]}년 {start[4]}분기"
    if not end:
        return label
    if end[:4] == start[:4]:
        return f"{label}~{end[4]}분기"
    return f"{label}~{end[:4]}년 {end[4]}분기"


def labels_periods(role):
    return role in PERIOD_LABEL_ROLES


def label_periods(value, key=None):
    if key == "period" and isinstance(value, str):
        return period_label(value)
    if isinstance(value, dict):
        return {name: label_periods(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [label_periods(item) for item in value]
    return value


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
    references = set()
    _walk(value, lambda fid: references.add(fid) or fid)
    with open_stores(scope.path) as st:
        resolved = st.facts.aliases_for(scope.request_id, scope.snapshot_id, sorted(references))
    return _walk(value, resolved.__getitem__)


def encode_messages(scope, messages, label=False):
    output = []
    for message in messages:
        item = dict(message)
        if isinstance(item.get("content"), str):
            try:
                body = json.loads(item["content"])
            except ValueError:
                pass
            else:
                body = encode(scope, body)
                item["content"] = json.dumps(
                    label_periods(body) if label else body, ensure_ascii=False
                )
        output.append(item)
    return output


def decode(scope, value):
    with open_stores(scope.path) as st:

        def original(reference):
            if not isinstance(reference, str):
                raise ValueError("fact 별칭은 문자열이어야 합니다.")
            row = st.facts.fact_id_by_reference(scope.request_id, scope.snapshot_id, reference)
            if not row:
                visible = (
                    reference if len(reference) == 8 and reference.isalnum() else "미등록 식별자"
                )
                raise ValueError("존재하지 않는 fact: " + visible)
            return row

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

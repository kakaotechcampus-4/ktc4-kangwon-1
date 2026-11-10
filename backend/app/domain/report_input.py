"""확정 공간값과 정확히 같은 표기만 근거 참조로 바꿉니다. 수치 추정은 하지 않습니다."""

import re
from copy import deepcopy

from app.domain.text import has_digit

SPACE_LITERAL = re.compile(
    r"(?<![0-9A-Za-z.,+\-−])(?:(?:지하|지상|지|B)\s*)?(?:[+\-−]\s*)?\d+(?:\.\d+)?\s*"
    r"(?:㎡|m²|m2|평|층|F)(?![0-9A-Za-z])",
    re.IGNORECASE,
)


def report_containers(report):
    yield "", report
    for group in ("candidates", "excluded_candidates"):
        values = report.get(group)
        if isinstance(values, list):
            for index, value in enumerate(values):
                if isinstance(value, dict):
                    yield f"{group}.{index}.", value


def text_references(segment, literals):
    if set(segment) != {"type", "text"} or not isinstance(segment.get("text"), str):
        return [segment]
    text, output, start = segment["text"], [], 0
    for match in SPACE_LITERAL.finditer(text):
        fid = literals.get(re.sub(r"\s+", "", match.group()))
        if fid is None:
            continue
        if match.start() > start:
            output.append({"type": "text", "text": text[start : match.start()]})
        output.append({"type": "fact", "fact_id": fid, "format": "text"})
        start = match.end()
    if not output:
        return [segment]
    if start < len(text):
        output.append({"type": "text", "text": text[start:]})
    return output


def normalize_report_input(arguments, literals):
    normalized = deepcopy(arguments)
    report = normalized.get("report")
    if not isinstance(report, dict):
        return normalized, []
    converted, defaulted = False, False
    for _, container in report_containers(report):
        for field, value in container.items():
            if not field.endswith("_segments") or not isinstance(value, list):
                continue
            segments = []
            for segment in value:
                if isinstance(segment, dict) and segment.get("type") == "fact":
                    if "format" not in segment:
                        segment = segment | {"format": "text"}
                        defaulted = True
                expanded = (
                    text_references(segment, literals)
                    if isinstance(segment, dict) and segment.get("type") == "text"
                    else [segment]
                )
                converted = converted or expanded != [segment]
                segments.extend(expanded)
            container[field] = segments
    warnings = []
    if converted:
        warnings.append("확정된 층·면적 표기를 저장된 근거 참조로 변환했습니다.")
    if defaulted:
        warnings.append("누락된 근거 표시 형식을 원문 표시로 보완했습니다.")
    return normalized, warnings


def numeric_text_paths(report):
    paths = []
    for prefix, container in report_containers(report):
        for field, value in container.items():
            if not field.endswith("_segments") or not isinstance(value, list):
                continue
            for index, segment in enumerate(value):
                if (
                    isinstance(segment, dict)
                    and segment.get("type") == "text"
                    and isinstance(segment.get("text"), str)
                    and has_digit(segment["text"])
                ):
                    paths.append(f"report.{prefix}{field}.{index}")
    return paths[:3]

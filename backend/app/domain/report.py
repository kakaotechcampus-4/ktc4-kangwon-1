from decimal import ROUND_HALF_UP, Decimal

from app.domain.contracts import (
    ConditionExcludedCandidate,
    LRecord,
    LSelection,
    RankedIndustry,
    RegulationExcludedIndustry,
)
from app.domain.industries.catalog import INDUSTRIES
from app.domain.scoring import rank_candidates, rank_key
from app.domain.space_rules import FACILITY_NAMES, FACILITY_STATE_TEXT, load_requirements
from app.domain.text import has_digit

RULE_FACILITY_LEVELS = frozenset({"required", "preferred"})
RULE_SPACE_MESSAGE = "층과 필수·선호 공간 조건은 규칙이 채점합니다. L 근거로 쓸 수 없습니다."


class ReportInvalid(ValueError):
    """모델 제출 오류는 수정 가능한 도구 오류로 반환합니다."""


def l_grade(factors):
    favorable = sum(f["direction"] == "favorable" for f in factors)
    adverse = sum(f["direction"] == "adverse" for f in factors)
    if adverse >= 2 or any(f.get("major_constraint") for f in factors):
        return 0
    if favorable and adverse or not favorable and not adverse:
        return 2
    if adverse:
        return 1
    return 4 if favorable >= 2 else 3


def rule_scored_space(fact, component, industry_code):
    metric = fact.metric
    if metric == "space_fit":
        if component == "floor":
            return True
        level = load_requirements().get(industry_code, {}).get(f"{component}_needed")
        return component in FACILITY_NAMES and level in RULE_FACILITY_LEVELS
    if fact.source != "user":
        return False
    if metric == "floor":
        return True
    return metric == "existing_facilities" and isinstance(fact.value, dict)


def industry_ranking(rows, excluded_codes):
    return [
        RankedIndustry(
            industry_code=r["code"],
            industry_name=r["name"],
            rank=rank,
            ai_excluded=r["code"] in excluded_codes,
        )
        for rank, r in enumerate(rank_candidates(rows, limit=len(rows)), 1)
    ]


def regulation_excluded(rows):
    return [
        RegulationExcludedIndustry(industry_code=r["code"], industry_name=r["name"])
        for r in sorted(rows, key=rank_key)
        if r["regulation"] == "금지"
    ]


def condition_excluded(rows):
    ranked = sorted((r for r in rows if r["regulation"] != "금지"), key=rank_key)
    return [
        ConditionExcludedCandidate(
            industry_code=r["code"],
            industry_name=r["name"],
            reasons=r["space"]["exclusion_reasons"],
            score_rank=rank,
        )
        for rank, r in enumerate(ranked, 1)
        if r.get("space", {}).get("excluded", False)
    ]


def segments(proposal):
    fields = list(proposal.summary_segments) + list(proposal.limitations_segments)
    for candidate in proposal.candidates + proposal.excluded_candidates:
        fields += (
            candidate.reasons_segments
            + candidate.risks_segments
            + candidate.confirmation_conditions_segments
        )
    return fields


def digit_text_paths(proposal):
    paths = []

    def scan(prefix, items):
        paths.extend(
            f"{prefix}.{index}"
            for index, segment in enumerate(items)
            if segment.type == "text" and has_digit(segment.text)
        )

    scan("summary_segments", proposal.summary_segments)
    scan("limitations_segments", proposal.limitations_segments)
    for group in ("candidates", "excluded_candidates"):
        for index, candidate in enumerate(getattr(proposal, group)):
            for field in (
                "reasons_segments",
                "risks_segments",
                "confirmation_conditions_segments",
            ):
                scan(f"{group}.{index}.{field}", getattr(candidate, field))
    return paths


def numeric_text_message(prefix, paths):
    shown = ", ".join(paths[:6]) + (f" 외 {len(paths) - 6}곳" if len(paths) > 6 else "")
    return f"{prefix} 숫자가 든 text 위치: {shown}. 숫자를 빼거나 fact 슬롯으로 바꾸세요."


def code90_uses_metric(row, metric):
    basis = row.get("items", {}).get("C1", {}).get("scoring", {}).get("basis", "")
    return metric == "lq" and "LQ" in basis


def complete_l_records(records, base_id, base_rows, advisor_unavailable=False):
    indexed = {r.industry_code: r for r in records}
    if len(indexed) != len(records):
        raise ReportInvalid("L 업종이 중복됩니다.")
    if {row["code"] for row in base_rows} != set(INDUSTRIES):
        raise ReportInvalid("전체 업종의 초기 코드 점수가 필요합니다.")
    completed = []
    for rank, original in enumerate(base_rows, 1):
        record = indexed.get(original["code"])
        if record is None:
            record = LRecord(
                industry_code=original["code"],
                selection=LSelection(
                    basis="all_industries",
                    code_score_snapshot_id=base_id,
                    code_lower_rank=rank,
                    reason="전체 업종 검토",
                ),
                review_state="unreviewed",
                status="unknown",
                grade=None,
                limitations=["L 판단 미제출: 확인된 새 근거를 제출하지 않았습니다."],
            )
        record.advisor_unavailable = record.advisor_unavailable or advisor_unavailable
        completed.append(record)
    return completed


SPACE_FIT_NAMES = {"floor": "층", "area": "면적", **FACILITY_NAMES}


CONFIDENCE_TEXT = {"low": "낮음", "medium": "보통", "high": "높음"}


def space_fit_text(value):
    parts = [
        f"{name} {value[key]}"
        for key, name in SPACE_FIT_NAMES.items()
        if isinstance(value.get(key), str) and value[key] != "해당 없음"
    ]
    text = " · ".join(parts) if parts else "비교할 공간 조건 없음"
    confidence = CONFIDENCE_TEXT.get(value.get("confidence"))
    return f"{text} (비교 신뢰도 {confidence})" if confidence else text


def text_value(value):
    if isinstance(value, bool):
        return "예" if value else "아니요"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 1e21:
            return str(int(value))
        return fixed(value, 2) if abs(value) < 1e21 else repr(value)
    return None


def fixed(value, digits):
    exponent = Decimal(1).scaleb(-digits)
    return format(Decimal(value).quantize(exponent, rounding=ROUND_HALF_UP), "f")


def grouped(value):
    return format(Decimal(value).quantize(Decimal(1), rounding=ROUND_HALF_UP), ",f")


def render_segment(segment, facts):
    if segment.type == "text":
        return segment.text
    fact = facts[segment.fact_id]
    value = fact.value
    if segment.format == "text":
        if fact.metric == "existing_facilities" and isinstance(value, dict):
            return " · ".join(
                f"{name} {FACILITY_STATE_TEXT[value[key]]}"
                for key, name in FACILITY_NAMES.items()
                if value.get(key) in FACILITY_STATE_TEXT
            )
        if isinstance(value, dict):
            if fact.metric == "space_fit":
                return space_fit_text(value)
            if fact.metric == "space_requirements" and isinstance(value.get("area_band"), str):
                return f"권장 면적 {value['area_band']}"
            return "확인 불가"
        if isinstance(value, list):
            items = [text_value(item) for item in value]
            return ", ".join(items) if items and None not in items else "확인 불가"
        text = text_value(value)
        return "확인 불가" if text is None else text
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ReportInvalid("숫자 형식에 맞지 않는 fact입니다.")
    if segment.format == "percent":
        if fact.unit not in {"%", "비율"}:
            raise ReportInvalid("백분율 단위가 아닙니다.")
        return fixed(value * 100 if fact.unit == "비율" else value, 1) + "%"
    if segment.format == "count":
        return grouped(value)
    if segment.format == "distance":
        return grouped(value) + "m"
    return fixed(value, 2)


def join_segments(segments, facts):
    joined = ""
    previous = None
    for segment in segments:
        piece = render_segment(segment, facts)
        kind = segment.type
        if kind == "fact" and facts[segment.fact_id].metric == "space_fit":
            kind = "space_fit"
        touching = joined[-1:].strip() and piece[:1].strip() and piece[0] not in ".,!?;:)]…"
        gap = (
            joined[-1:] in (".", "!", "?")
            or previous == "space_fit"
            or (previous == "text" and joined[-1:] not in "([{'\"“‘~-/·")
            or (previous not in (None, "text") and kind != "text")
        )
        if touching and gap:
            joined += " "
        joined += piece
        if piece:
            previous = kind
    return joined


def limitation_segments(model_segments, texts):
    from app.domain.contracts import TextSegment

    added = [
        TextSegment(type="text", text=t if t.endswith((".", "!", "?")) else t + ".") for t in texts
    ]
    return [*model_segments, *added]

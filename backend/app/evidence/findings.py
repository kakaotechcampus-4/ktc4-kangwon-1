"""전문가 문장의 경로·수치·단위를 검증합니다."""

import re
from decimal import Decimal

from app.industries import lookup
from app.schemas import Finding, MapData, SpecialistId

from .index import SourceIndex, can_cite
from .map import MAP_AGENT_ID
from .pointer import resolve_pointer

FINDING_WARNING_PREFIX = "전문가 근거 제외"


def validate_findings(
    findings: list[Finding],
    *,
    agent_id: SpecialistId,
    data: dict | MapData,
    radii: set[int] | None = None,
    index: SourceIndex | None = None,
) -> tuple[list[Finding], list[str]]:
    """문장 의미를 보증하지 않으며 경로·소유 업종·직접 표기 수치만 검증합니다."""
    if agent_id == MAP_AGENT_ID and not isinstance(data, MapData):
        data = MapData.model_validate(data or {"queries": {}})
    if isinstance(data, dict) and index is None:
        index = SourceIndex.build(data)
    indexed = index.owners if index is not None else None
    context_radii = (index.radii if index is not None else frozenset()) | {
        Decimal(r) for r in radii or ()
    }
    valid, warnings = [], []
    for i, finding in enumerate(findings):
        paths = [ref.path for ref in finding.evidence]
        reasons = [can_cite(data, path, finding.industry_code, indexed=indexed) for path in paths]
        allowed = not any(reasons)
        if not allowed:
            reason = _path_reason(agent_id, finding, paths, reasons, indexed)
            warnings.append(f"{FINDING_WARNING_PREFIX}: {i + 1}번 경로·업종 불일치{reason}")
            continue
        values = [resolve_pointer(data, p) for p in paths]
        claim = _claim_without_context(finding.claim, paths, context_radii)
        rejected, mismatched = _mismatched_numbers(claim, values, paths, agent_id, data)
        if rejected:
            warnings.append(_number_warning(i + 1, mismatched))
            continue
        valid.append(finding)
    return valid, warnings


def _mismatched_numbers(claim, values, paths, agent_id, data):
    numbers = re.findall(r"(?<![A-Za-z0-9_.])[-+]?\d[\d,]*(?:\.\d+)?", claim)
    numeric = [Decimal(str(v)) for v in values if type(v) in {int, float}]
    mismatched = [
        n
        for n in numbers
        if not any(
            abs(value - Decimal(n.replace(",", "")))
            <= (Decimal(0) if "." not in n else Decimal(5).scaleb(-len(n.split(".")[1]) - 1))
            for value in numeric
        )
    ]
    # 같은 숫자라도 점포 수를 인원·금액으로 바꾸면 인용할 수 없습니다.
    for number, unit in re.findall(
        r"([-+]?\d[\d,]*(?:\.\d+)?)\s*(명/일|개소|명|개|원|점|배|미터|m|%)", claim
    ):
        if not any(
            type(value) in {int, float}
            and abs(Decimal(str(value)) - Decimal(number.replace(",", "")))
            <= (
                Decimal(0)
                if "." not in number
                else Decimal(5).scaleb(-len(number.split(".")[1]) - 1)
            )
            and (
                unit in _allowed_units(agent_id, path, data)
                # "일평균 …명"은 명/일 값을 풀어 쓴 표현입니다.
                or unit == "명"
                and "명/일" in _allowed_units(agent_id, path, data)
                and ("일평균" in claim or "일 평균" in claim or "하루" in claim)
            )
            for path, value in zip(paths, values, strict=True)
        ):
            mismatched.append(number)
    matched = not mismatched
    if "%" in claim:
        population = data.get("population") if isinstance(data, dict) else None
        unit = rate_basis(data) or (
            population.get("share_unit") if isinstance(population, dict) else None
        )
        percent_allowed = any(
            any(token in p for token in ("rate", "share", "percentile", "ratio"))
            and "%" in str(unit)
            for p in paths
        )
        matched = matched and percent_allowed
        if not percent_allowed:
            mismatched.extend(re.findall(r"([-+]?\d[\d,]*(?:\.\d+)?)\s*%", claim))
    scaled = re.findall(r"([-+]?\d[\d,]*(?:\.\d+)?)\s*[만억천]\s*(?:명|개|원)", claim)
    mismatched.extend(scaled)
    return not matched or bool(scaled), mismatched


def _number_warning(position, mismatched):
    numbers_only = list(dict.fromkeys(n.replace(",", "") for n in mismatched))[:3]
    detail = f" (맞지 않는 수: {', '.join(numbers_only)})" if numbers_only else ""
    return f"{FINDING_WARNING_PREFIX}: {position}번 수치·단위 불일치{detail}"


def _path_reason(agent_id, finding, paths, reasons, indexed):
    reason = ""
    if agent_id == MAP_AGENT_ID:
        causes = dict.fromkeys(filter(None, reasons))
        reason = "(지도: " + "·".join(causes) + ")"
    else:
        details = []
        for path, cause in zip(paths, reasons, strict=True):
            if cause == "evidence_industry_mismatch":
                claimed = lookup.find(finding.industry_code) if finding.industry_code else None
                owner_code = indexed.get(path) if indexed is not None else None
                owner = lookup.find(owner_code) if owner_code else None
                details.append(
                    f"업종: 인용 {claimed.code if claimed else '없음'}"
                    f" · 경로 {owner.code if owner else '없음'}"
                )
            elif cause:
                details.append("형식" if cause == "evidence_path_invalid" else "없음")
        reason = "(" + "·".join(dict.fromkeys(details)) + ")"
    return reason


def _claim_without_context(claim, paths, context_radii):
    # 날짜·코드는 지표 숫자가 아닙니다. 숫자 단위 축약·환산은 지원하지 않습니다.
    claim = re.sub(r"\b[A-Z]\d{3}\b|\b\d{4}-\d{2}-\d{2}\b", "", claim)
    # 기간 표현과 원자료에 있는 반경은 지표가 아닌 문맥이라 인용 경로 없이 허용합니다.
    claim = re.sub(
        r"\d{4}\s*년\s*\d\s*분기|\d+\s*개?\s*분기|\d+\s*년|(?<!\d)20\d{2}[1-4](?!\d)"
        # 연령대·시간대·면적 단위도 구간 이름입니다.
        r"|\d{1,2}\s*[~-]\s*\d{1,2}\s*시|\d{1,2}\s*시|1\s*(?:km²|km2|㎢)",
        "",
        claim,
    )
    claim = re.sub(
        r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*m(?![A-Za-z])",
        lambda m: (
            "" if Decimal(str(m.group(1)).replace(",", "")) in context_radii else str(m.group(0))
        ),
        claim,
    )
    if any(
        part == "by_age" or part.startswith("age_") for path in paths for part in path.split("/")
    ):
        claim = re.sub(r"(?<!\d)(?:10|20|30|40|50|60|70|80|90)\s*대(?![\d가-힣])", "", claim)
    return claim


def _allowed_units(agent_id, path, data) -> set[str]:
    """원자료 단위 또는 지표의 고정 단위만 허용합니다. 환산하지 않습니다."""
    leaf = path.rsplit("/", 1)[-1]
    if leaf == "score":
        return {"점"}
    if leaf in {"lq", "lq_district", "times_vs_surroundings"} or "index" in path:
        return {"배"}
    if leaf.endswith("_m"):
        return {"m", "미터"}
    if any(k in path for k in ("rate", "share", "percentile", "ratio")):
        unit = rate_basis(data) or ""
        for prefix in ("population", "resident", "worker"):
            block = data.get(prefix)
            if path.startswith(f"/{prefix}/") and isinstance(block, dict):
                unit = block.get("share_unit", unit)
        return {"%"} if "%" in str(unit) else set()
    if agent_id == "floating_population":
        return (
            {"명/일"}
            if leaf in {"daily_avg", "mean_daily_per_trade_area"}
            else {"명"}
            if path.startswith(("/resident/", "/worker/")) and leaf == "count"
            else set()
        )
    # 순증감(period_net_change·recent_year_net_change)도 점포 수 차이라 개수 단위를 씁니다.
    if "count" in leaf or leaf == "store_total" or leaf.endswith("net_change"):
        return {"개", "개소"}
    return set()


def rate_basis(data: dict | MapData):
    if isinstance(data, MapData):
        return None
    method = data.get("scoring_method")
    return data.get("rate_basis") or (
        method.get("rate_basis") if isinstance(method, dict) else None
    )

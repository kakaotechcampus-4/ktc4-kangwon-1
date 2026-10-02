"""전문가 문장의 경로·수치·단위를 검증합니다."""

import re
from decimal import Decimal

from app.schemas import Finding, MapData, SpecialistId

from .index import can_cite, index_paths
from .map import MAP_AGENT_ID
from .pointer import resolve_pointer

FINDING_WARNING_PREFIX = "전문가 근거 제외"


def validate_findings(
    findings: list[Finding],
    *,
    agent_id: SpecialistId,
    data: dict | MapData,
    radii: set[int] | None = None,
) -> tuple[list[Finding], list[str]]:
    """문장 의미를 보증하지 않으며 경로·소유 업종·직접 표기 수치만 검증합니다."""
    if agent_id == MAP_AGENT_ID and not isinstance(data, MapData):
        data = MapData.model_validate(data or {"queries": {}})
    indexed = index_paths(data) if isinstance(data, dict) else None
    context_radii = _radii(data) | {Decimal(r) for r in radii or ()}
    valid, warnings = [], []
    for i, finding in enumerate(findings):
        paths = [ref.path for ref in finding.evidence]
        reasons = [can_cite(data, path, finding.industry_code, indexed=indexed) for path in paths]
        allowed = not any(reasons)
        if not allowed:
            reason = ""
            if agent_id == MAP_AGENT_ID:
                causes = dict.fromkeys(filter(None, reasons))
                reason = "(지도: " + "·".join(causes) + ")"
            warnings.append(f"{FINDING_WARNING_PREFIX}: {i + 1}번 경로·업종 불일치{reason}")
            continue
        values = [resolve_pointer(data, p) for p in paths]
        # 날짜·코드는 지표 숫자가 아닙니다. 숫자 단위 축약·환산은 지원하지 않습니다.
        claim = re.sub(r"\b[A-Z]\d{3}\b|\b\d{4}-\d{2}-\d{2}\b", "", finding.claim)
        # 기간 표현과 원자료에 있는 반경은 지표가 아닌 문맥이라 인용 경로 없이 허용합니다.
        claim = re.sub(
            r"\d{4}\s*년\s*\d\s*분기|\d+\s*개?\s*분기|\d+\s*년|(?<!\d)20\d{2}[1-4](?!\d)"
            # 연령대·시간대·면적 단위도 구간 이름입니다.
            r"|\d+\s*대(?![\d가-힣])|\d{1,2}\s*[~-]\s*\d{1,2}\s*시|\d{1,2}\s*시|1\s*(?:km²|km2|㎢)",
            "",
            claim,
        )
        claim = re.sub(
            r"(?<![\d.])(\d[\d,]*(?:\.\d+)?)\s*m(?![A-Za-z])",
            lambda m: (
                ""
                if Decimal(str(m.group(1)).replace(",", "")) in context_radii
                else str(m.group(0))
            ),
            claim,
        )
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
        if not matched or scaled:
            mismatched.extend(scaled)
            numbers_only = list(dict.fromkeys(n.replace(",", "") for n in mismatched))[:3]
            detail = f" (맞지 않는 수: {', '.join(numbers_only)})" if numbers_only else ""
            warnings.append(f"{FINDING_WARNING_PREFIX}: {i + 1}번 수치·단위 불일치{detail}")
            continue
        valid.append(finding)
    return valid, warnings


def _radii(node) -> set[Decimal]:
    """원자료의 *radius_m 값입니다. 문장의 "반경 500m" 같은 문맥 숫자 확인에만 씁니다."""
    found: set[Decimal] = set()
    items = (
        node.items()
        if isinstance(node, dict)
        else enumerate(node)
        if isinstance(node, list)
        else ()
    )
    for key, value in items:
        if isinstance(key, str) and key.endswith("radius_m") and type(value) in {int, float}:
            found.add(Decimal(str(value)))
        elif isinstance(value, (dict, list)):
            found |= _radii(value)
    return found


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

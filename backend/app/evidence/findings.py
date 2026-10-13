"""전문가 문장의 경로·수치·단위를 검증합니다."""

import re

from app.industries import lookup
from app.schemas import Finding, MapData, SpecialistId

from .index import SourceIndex, can_cite
from .map import MAP_AGENT_ID

FINDING_WARNING_PREFIX = "전문가 근거 제외"


def validate_findings(
    findings: list[Finding],
    *,
    agent_id: SpecialistId,
    data: dict | MapData,
    radii: set[int] | None = None,
    index: SourceIndex | None = None,
    render: bool = True,
) -> tuple[list[Finding], list[str]]:
    """문장 의미를 보증하지 않으며 경로·소유 업종·직접 표기 수치만 검증합니다."""
    if agent_id == MAP_AGENT_ID and not isinstance(data, MapData):
        data = MapData.model_validate(data or {"queries": {}})
    if isinstance(data, dict) and index is None:
        index = SourceIndex.build(data, agent_id)
    indexed = index.owners if index is not None else None
    valid, warnings = [], []
    for i, finding in enumerate(findings):
        paths = [ref.path for ref in finding.evidence]
        reasons = [can_cite(data, path, finding.industry_code, indexed=indexed) for path in paths]
        allowed = not any(reasons)
        if not allowed:
            reason = _path_reason(agent_id, finding, paths, reasons, indexed)
            warnings.append(f"{FINDING_WARNING_PREFIX}: {i + 1}번 경로·업종 불일치{reason}")
            continue
        if not render:
            valid.append(finding)
            continue
        from .citations import CitationError, render_cited

        source = data.model_dump(mode="json") if isinstance(data, MapData) else data
        try:
            claim = render_cited(
                finding.claim,
                [(agent_id, p) for p in paths],
                {agent_id: source},
                map_radii=radii if agent_id == MAP_AGENT_ID else None,
            )
        except CitationError:
            numbers = re.findall(
                r"(?<![A-Za-z0-9_.])[-+]?\d[\d,]*(?:\.\d+)?",
                re.sub(r"\{\d+\}", "", finding.claim),
            )
            warnings.append(_number_warning(i + 1, numbers))
            continue
        if len(claim) > 200:
            warnings.append(f"{FINDING_WARNING_PREFIX}: {i + 1}번 문장 길이 초과")
            continue
        valid.append(finding.model_copy(update={"claim": claim}))
    return valid, warnings


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
            if (path.startswith(("/resident/", "/worker/")) and leaf == "count")
            or path.startswith(
                ("/population/by_age/", "/population/by_time/", "/population/by_day/")
            )
            or (path.startswith("/radius_profile/") and leaf == "total")
            else {"개"}
            if leaf == "trade_area_count"
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

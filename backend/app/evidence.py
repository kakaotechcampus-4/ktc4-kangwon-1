"""공통 원자료의 업종 식별자와 실제 근거 경로를 연결합니다."""

import re
from decimal import Decimal
from typing import Any

from app.industries import lookup
from app.schemas import Finding, SpecialistId


def _industry(row: dict, path: str) -> str | None:
    """식별 불가·코드와 명칭 충돌은 빈 코드로 표시해 인용을 막습니다."""
    scoped_row = path.split("/")[-2:-1] in (["industries"], ["by_middle"], ["industry_results"])
    code = row.get("industry_id", row.get("industry_code"))
    name = row.get("industry_name", row.get("industry"))
    generic_code, generic_name = row.get("code"), row.get("name")
    if scoped_row and name is None:
        name = row.get("middle")
    if scoped_row or (
        isinstance(generic_code, str)
        and lookup.find(generic_code) is not None
        or isinstance(generic_name, str)
        and lookup.find_by_name(generic_name) is not None
    ):
        code = code if code is not None else generic_code
        name = name if name is not None else generic_name
    if code is None and name is None:
        return "" if scoped_row else None
    found = lookup.find(code) if isinstance(code, str) else None
    named = lookup.find_by_name(name) if isinstance(name, str) else None
    if code is not None:
        return found.code if found and (name is None or named and named.code == found.code) else ""
    return named.code if named else ""


def index_paths(data: dict[str, Any]) -> dict[str, str | None]:
    """인용 경로와 소유 업종을 반환합니다. citable은 전체·필드별 차단을 지원합니다."""
    paths: dict[str, str | None] = {}

    def visit(
        value: Any, path: str, owner: str | None = None, blocked: bool = False
    ) -> tuple[bool, bool]:
        scoped = owner is not None
        policy = value.get("citable") if isinstance(value, dict) else None
        if isinstance(value, dict):
            identified = _industry(value, path)
            if identified is not None:
                blocked = blocked or owner is not None and owner != identified
                owner, scoped = identified, True
            blocked = (
                blocked
                or policy is False
                or value.get("data_available") is False
                or value.get("confidence") == "none"
            )
        blocked = blocked or owner == ""
        children = (
            value.items()
            if isinstance(value, dict)
            else enumerate(value)
            if isinstance(value, list)
            else ()
        )
        descendant_scoped = False
        descendant_blocked = False
        for key, child in children:
            if key == "citable":
                continue
            child_owner = owner
            if path.endswith("/industry_counts"):
                industry = lookup.find_by_name(str(key))
                child_owner = industry.code if industry else ""
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            unavailable_score = (
                isinstance(value, dict) and key == "score" and value.get("score_available") is False
            )
            field_blocked = isinstance(policy, dict) and policy.get(key) is False
            child_scoped, child_blocked = visit(
                child,
                f"{path}/{escaped}",
                child_owner,
                blocked or unavailable_score or field_blocked,
            )
            descendant_scoped |= child_scoped
            descendant_blocked |= child_blocked
        present = (
            value is not None
            and not (isinstance(value, str) and not value.strip())
            and value != []
            and value != {}
        )
        # 금지된 하위 자료·다른 업종을 상위 객체 인용으로 우회하지 못합니다.
        if (
            path
            and present
            and not blocked
            and not descendant_blocked
            and not (owner is None and descendant_scoped)
        ):
            paths[path] = owner
        return scoped or descendant_scoped, blocked or descendant_blocked

    visit(data, "")
    return paths


def industry_catalog(sources: dict[str, dict]) -> list[dict]:
    """원본 값을 복제하지 않고 업종별 인용 경로를 묶어 제공합니다."""
    entries = []
    for agent_id, data in sources.items():
        groups: dict[str, list[str]] = {}
        for path, code in index_paths(data).items():
            if code:
                groups.setdefault(code, []).append(path)
        for code, paths in groups.items():
            entries.append(
                {
                    "agent_id": agent_id,
                    "industry_code": code,
                    "industry_name": lookup.get(code).name,
                    "paths": paths,
                }
            )
    return entries


def resolve_pointer(data: Any, path: str) -> Any:
    """배열 위치를 추정하지 않고 표준 포인터만 해석합니다."""
    if not path.startswith("/") or re.search(r"~(?![01])", path):
        raise ValueError("잘못된 근거 경로입니다.")
    for encoded in path[1:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(data, dict):
            data = data[key]
        elif isinstance(data, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            data = data[int(key)]
        else:
            raise KeyError(key)
    return data


def valid_map_path(path: str, code: str | None, data: dict) -> bool:
    """지도 표본·시설·정상 0건만 인용하며 검색 총수를 업종 수로 바꾸지 않습니다."""
    parts = path.split("/")
    if len(parts) != 4 or parts[0] or re.search(r"~(?![01])", path):
        return False
    _, section, key, field = [p.replace("~1", "/").replace("~0", "~") for p in parts]
    if section == "industries":
        return code == key and key in data.get("industries", {}) and field == "sampled_count"
    if section == "queries":
        query = data.get("queries", {}).get(key, {})
        target = query.get("request", {})
        return bool(
            query.get("status") == "ok"
            and field == "total_count"
            and (
                target.get("kind") == "infrastructure"
                or code is not None
                and target.get("industry_code") == code
                and query.get("total_count") == 0
            )
        )
    if section == "places":
        place = data.get("places", {}).get(key, {})
        if field not in {"name", "distance_m"} or place.get(field) is None:
            return False
        return bool(
            code is not None
            and place.get("mapping_status") == "mapped"
            and place.get("industry_code") == code
            or place.get("mapping_status") == "not_applicable"
            and any(
                q.get("status") == "ok"
                and q.get("request", {}).get("kind") == "infrastructure"
                and key in q.get("place_ids", [])
                for q in data.get("queries", {}).values()
            )
        )
    return False


def scalar_records(data: dict) -> list[dict]:
    """숫자·문자열 값만 원본 경로와 묶습니다. 객체 전체를 요약에 복제하지 않습니다."""
    return [
        {"path": path, "value": value, "industry_code": owner}
        for path, owner in index_paths(data).items()
        if isinstance(value := resolve_pointer(data, path), (str, int, float))
        and not isinstance(value, bool)
    ]


def validate_findings(
    findings: list[Finding], *, agent_id: SpecialistId, data: dict
) -> tuple[list[Finding], list[str]]:
    """문장 의미를 보증하지 않으며 경로·소유 업종·직접 표기 수치만 검증합니다."""
    indexed = index_paths(data)
    radii = _radii(data)
    valid, warnings = [], []
    for i, finding in enumerate(findings):
        paths = [ref.path for ref in finding.evidence]
        allowed = all(
            valid_map_path(p, finding.industry_code, data)
            if agent_id == "map_analysis"
            else p in indexed and (indexed[p] is None or indexed[p] == finding.industry_code)
            for p in paths
        )
        if not allowed:
            warnings.append(f"전문가 근거 제외: {i + 1}번 경로·업종 불일치")
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
            lambda m: "" if Decimal(str(m.group(1)).replace(",", "")) in radii else str(m.group(0)),
            claim,
        )
        numbers = re.findall(r"(?<![A-Za-z0-9_.])[-+]?\d[\d,]*(?:\.\d+)?", claim)
        numeric = [Decimal(str(v)) for v in values if type(v) in {int, float}]
        matched = all(
            any(
                abs(value - Decimal(n.replace(",", "")))
                <= (Decimal(0) if "." not in n else Decimal(5).scaleb(-len(n.split(".")[1]) - 1))
                for value in numeric
            )
            for n in numbers
        )
        # 같은 숫자라도 점포 수를 인원·금액으로 바꾸면 인용할 수 없습니다.
        for number, unit in re.findall(
            r"([-+]?\d[\d,]*(?:\.\d+)?)\s*(명/일|개소|명|개|원|점|배|미터|m|%)", claim
        ):
            matched = matched and any(
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
            )
        if "%" in claim:
            population = data.get("population")
            unit = rate_basis(data) or (
                population.get("share_unit") if isinstance(population, dict) else None
            )
            matched = matched and any(
                any(token in p for token in ("rate", "share", "percentile", "ratio"))
                and "%" in str(unit)
                for p in paths
            )
        if not matched or re.search(r"\d\s*[만억천]\s*(명|개|원)", claim):
            warnings.append(f"전문가 근거 제외: {i + 1}번 수치·단위 불일치")
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
    if "count" in leaf or leaf in {
        "store_total",
        "period_open_count",
        "period_close_count",
        "recent_year_net_change",
    }:
        return {"개", "개소"}
    return set()


def rate_basis(data: dict):
    method = data.get("scoring_method")
    return data.get("rate_basis") or (
        method.get("rate_basis") if isinstance(method, dict) else None
    )

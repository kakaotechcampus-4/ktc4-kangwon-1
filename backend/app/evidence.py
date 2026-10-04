"""공통 원자료의 업종 식별자와 실제 근거 경로를 연결합니다."""

import re
from collections.abc import Mapping
from typing import Any

from app.agents.data_models import industry_owners
from app.industries import lookup
from app.schemas import Finding, SpecialistId


def index_paths(data: dict[str, Any], agent_id: str) -> dict[str, str | None]:
    """인용 경로와 소유 업종을 반환합니다. citable은 전체·필드별 차단을 지원합니다."""
    owners = industry_owners(agent_id, data)
    paths: dict[str, str | None] = {}

    def visit(
        value: Any, path: str, owner: str | None = None, blocked: bool = False
    ) -> tuple[bool, bool]:
        scoped = owner is not None
        policy = value.get("citable") if isinstance(value, dict) else None
        if path in owners:
            identified = owners[path]
            blocked = blocked or owner is not None and owner != identified
            owner, scoped = identified, True
        if isinstance(value, dict):
            blocked = (
                blocked
                or policy is False
                or value.get("data_available") is False
                or value.get("confidence") == "none"
            )
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
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            unavailable_score = (
                isinstance(value, dict) and key == "score" and value.get("score_available") is False
            )
            field_blocked = isinstance(policy, dict) and policy.get(key) is False
            child_scoped, child_blocked = visit(
                child,
                f"{path}/{escaped}",
                owner,
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
        for path, code in index_paths(data, agent_id).items():
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


def pointer_segments(path: str) -> list[str]:
    if not path.startswith("/") or re.search(r"~(?![01])", path):
        raise ValueError("잘못된 근거 경로입니다.")
    return [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]


def resolve_pointer(data: Any, path: str) -> Any:
    """배열 위치를 추정하지 않고 표준 포인터만 해석합니다."""
    for key in pointer_segments(path):
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


def scalar_records(data: dict, agent_id: str) -> list[dict]:
    """숫자·문자열 값만 원본 경로와 묶습니다. 객체 전체를 요약에 복제하지 않습니다."""
    return [
        {"path": path, "value": value, "industry_code": owner}
        for path, owner in index_paths(data, agent_id).items()
        if isinstance(value := resolve_pointer(data, path), (str, int, float))
        and not isinstance(value, bool)
    ]


def validate_findings(
    findings: list[Finding], *, agent_id: SpecialistId, data: dict, render: bool = True
) -> tuple[list[Finding], list[str]]:
    """문장 의미를 보증하지 않으며 경로·소유 업종·직접 표기 수치만 검증합니다."""
    indexed = index_paths(data, agent_id)
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
        if not render:
            valid.append(finding)
            continue
        try:
            claim = render_cited(finding.claim, [(agent_id, p) for p in paths], {agent_id: data})
        except CitationError:
            warnings.append(f"전문가 근거 제외: {i + 1}번 수치·단위 불일치")
            continue
        if len(claim) > 200:
            warnings.append(f"전문가 근거 제외: {i + 1}번 문장 길이 초과")
            continue
        valid.append(finding.model_copy(update={"claim": claim}))
    return valid, warnings


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
            if path.startswith(("/resident/", "/worker/"))
            and leaf == "count"
            or path.startswith(
                ("/population/by_age/", "/population/by_time/", "/population/by_day/")
            )
            or path.startswith("/radius_profile/")
            and leaf == "total"
            else {"개"}
            if leaf == "trade_area_count"
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


_PLACEHOLDER = re.compile(r"\{(\d+)\}")
_UNIT = re.compile(r"\s*(명/일|개소|명|개|원|점|배|미터|m|%)")
_SCALE = re.compile(r"\s*[만억천]")
_DIGITS = re.compile(r"\d+")


class CitationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _dict_keys(data: Any, path: str) -> list[str]:
    keys = []
    for key in pointer_segments(path):
        if isinstance(data, dict) and key in data:
            keys.append(key)
            data = data[key]
        elif isinstance(data, list) and key.isdigit() and int(key) < len(data):
            data = data[int(key)]
        else:
            break
    return keys


def render_cited(text: str, refs: list[tuple[str, str]], sources: Mapping[str, Any]) -> str:
    labels = {
        digits
        for agent_id, path in refs
        for key in _dict_keys(sources.get(agent_id, {}), path)
        for digits in _DIGITS.findall(key)
    }
    if any(digits not in labels for digits in _DIGITS.findall(_PLACEHOLDER.sub("", text))):
        raise CitationError("number_uncited")
    pieces: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER.finditer(text):
        index = int(match.group(1))
        if index >= len(refs):
            raise CitationError("placeholder_out_of_range")
        agent_id, path = refs[index]
        data = sources.get(agent_id, {})
        try:
            value = resolve_pointer(data, path)
        except (KeyError, IndexError, ValueError, TypeError):
            raise CitationError("placeholder_value_invalid") from None
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise CitationError("placeholder_value_invalid")
        if _SCALE.match(text, match.end()):
            raise CitationError("unit_mismatch")
        unit = _UNIT.match(text, match.end())
        allowed = _allowed_units(agent_id, path, data)
        if unit and unit.group(1) not in allowed | ({"명"} if "명/일" in allowed else set()):
            raise CitationError("unit_mismatch")
        pieces.extend(
            [text[cursor : match.start()], value if isinstance(value, str) else f"{value:,}"]
        )
        cursor = match.end()
    return "".join([*pieces, text[cursor:]])

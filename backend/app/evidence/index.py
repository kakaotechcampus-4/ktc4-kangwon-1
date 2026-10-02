"""원자료의 인용 가능 경로·업종과 값을 연결합니다."""

from typing import Any

from app.industries import lookup
from app.schemas import AgentAnalysis, MapData

from .map import map_path_reason
from .pointer import escape_pointer, parse_pointer, resolve_pointer

INDUSTRY_SECTIONS = frozenset({"industries", "by_middle", "industry_results"})
INDUSTRY_COUNTS = "industry_counts"


def usable_analyses(analyses: list[AgentAnalysis]) -> list[AgentAnalysis]:
    return [item for item in analyses if item.status in {"ok", "partial"}]


def _industry(row: dict, path: str) -> str | None:
    """식별 불가·코드와 명칭 충돌은 빈 코드로 표시해 인용을 막습니다."""
    parts = parse_pointer(path) if path else []
    scoped_row = len(parts) >= 2 and parts[-2] in INDUSTRY_SECTIONS
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
            if path.endswith("/" + INDUSTRY_COUNTS):
                industry = lookup.find_by_name(str(key))
                child_owner = industry.code if industry else ""
            escaped = escape_pointer(str(key))
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


def scalar_records(data: dict) -> list[dict]:
    """숫자·문자열 값만 원본 경로와 묶습니다. 객체 전체를 요약에 복제하지 않습니다."""
    return [
        {"path": path, "value": value, "industry_code": owner}
        for path, owner in index_paths(data).items()
        if isinstance(value := resolve_pointer(data, path), (str, int, float))
        and not isinstance(value, bool)
    ]


def can_cite(
    source: dict | MapData,
    path: str,
    industry_code: str | None,
    *,
    indexed: dict[str, str | None] | None = None,
) -> str | None:
    """인용할 수 없으면 원문을 포함하지 않는 기존 진단 사유를 돌려줍니다."""
    if isinstance(source, MapData):
        return map_path_reason(path, industry_code, source)
    try:
        parse_pointer(path)
    except ValueError:
        return "evidence_path_invalid"
    try:
        value = resolve_pointer(source, path)
    except (KeyError, IndexError, ValueError):
        return "evidence_not_found"
    if (
        value is None
        or isinstance(value, str)
        and not value.strip()
        or isinstance(value, (list, dict))
        and not value
    ):
        return "evidence_empty"
    if indexed is None:
        indexed = index_paths(source)
    if path not in indexed:
        return "evidence_unavailable"
    if indexed[path] is not None and indexed[path] != industry_code:
        return "evidence_industry_mismatch"
    return None

"""이번 입력의 업종 식별자와 실제 근거 경로를 연결합니다."""

from typing import Any

from app.industries import lookup


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
    """값이 있는 경로와 소유 업종을 반환합니다. None은 공통 자료입니다."""
    paths: dict[str, str | None] = {}

    def visit(value: Any, path: str, owner: str | None = None, blocked: bool = False) -> bool:
        scoped = owner is not None
        if isinstance(value, dict):
            identified = _industry(value, path)
            if identified is not None:
                blocked = blocked or owner is not None and owner != identified
                owner, scoped = identified, True
            blocked = (
                blocked or value.get("data_available") is False or value.get("confidence") == "none"
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
        for key, child in children:
            child_owner = owner
            if path.endswith("/industry_counts"):
                industry = lookup.find_by_name(str(key))
                child_owner = industry.code if industry else ""
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            unavailable_score = (
                isinstance(value, dict) and key == "score" and value.get("score_available") is False
            )
            descendant_scoped |= visit(
                child, f"{path}/{escaped}", child_owner, blocked or unavailable_score
            )
        present = (
            value is not None
            and not (isinstance(value, str) and not value.strip())
            and value != []
            and value != {}
        )
        # 여러 업종을 감싼 상위 목록·객체로 개별 업종 검사를 우회하지 못합니다.
        if path and present and not blocked and not (owner is None and descendant_scoped):
            paths[path] = owner
        return scoped or descendant_scoped

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

import csv
from pathlib import Path

from app.industries.catalog import INDUSTRIES

DOTS = ("ㆍ", "‧", "・", "∙")


def _normal(name: str) -> str:
    text = "".join(name.split())
    for dot in DOTS:
        text = text.replace(dot, "·")
    return text


NAME_TO_CODE = {_normal(name): code for code, name in INDUSTRIES.items()}


def develop_code(name: str) -> str:
    code = NAME_TO_CODE.get(_normal(name))
    if code is None:
        raise KeyError(f"develop 업종에 없는 이름입니다: {name}")
    return code


def row_key(row: dict) -> str:
    return f"{row['업종코드']}-{row['순번']}"


def read_sample(path: Path, picks: set[str] | None = None) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if picks is None or row_key(row) in picks]


def invalid_rows(rows: list[dict]) -> list[str]:
    problems = []
    seen: set[str] = set()
    for row in rows:
        key = row_key(row)
        if key in seen:
            problems.append(f"{key}: 같은 업종코드·순번이 두 번 있습니다.")
        seen.add(key)
        if _normal(row.get("업종", "")) not in NAME_TO_CODE:
            problems.append(
                f"{key}: 업종 이름 {row.get('업종')}을 develop 업종에서 찾지 못했습니다."
            )
        if not row.get("주소", "").strip():
            problems.append(f"{key}: 주소가 비었습니다.")
    return problems

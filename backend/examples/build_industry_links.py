"""연결표 CSV를 만든다. 한 번 만들고 나면 사람이 CSV를 고치므로, 재실행은 덮어쓰기다.

    seoul_to_industry.csv     서울시 생활밀접업종 99종 → 중분류   (탐색 산출물에서 옮겨 적음)
    legacy70_to_industry.csv  개폐업 70업종 → 중분류              (서울시 경로로 합성)
    industries.csv            has_seoul · note 채움

`--force` 없이는 이미 있는 파일을 덮지 않는다. 사람이 손으로 고친 판정을 날리지 않기 위해서다.

사용:
    python examples/build_industry_links.py
    python examples/build_industry_links.py --force
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.industries import (  # noqa: E402
    LEGACY70_LINK_PATH,
    MASTER_PATH,
    SEOUL_LINK_PATH,
)

MATCH_SOURCE = Path(__file__).resolve().parent / "schema_compare" / "업종매칭_소분류근거.csv"
EXCLUDED_SEOUL = {"CS300043": "전자상거래업"}

MASTER_COLUMNS = ["middle_code", "middle_name", "major_code", "major_name", "has_seoul", "note"]
SEOUL_COLUMNS = [
    "seoul_code",
    "seoul_name",
    "middle_code",
    "match_method",
    "evidence_small",
    "note",
]
LEGACY_COLUMNS = ["legacy_id", "legacy_name", "middle_code", "split_count", "route", "note"]


def read_csv(path: Path) -> list[dict[str, str]]:
    """엑셀로 한 번 열었다 저장하면 cp949가 된다. 둘 다 받아준다."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f"{path.name}: 인코딩을 못 읽었습니다.")
    return [
        row
        for row in csv.DictReader(io.StringIO(text))
        if any((v or "").strip() for v in row.values())
    ]


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def guard(path: Path, force: bool) -> bool:
    if path.exists() and not force:
        print(f"  건너뜀 — {path.name} 이 이미 있습니다. 덮어쓰려면 --force")
        return False
    return True


def build_seoul_links(master: dict[str, dict[str, str]]) -> list[dict]:
    rows = []
    for row in read_csv(MATCH_SOURCE):
        code = row["(서울시)코드명"].strip()
        if code in EXCLUDED_SEOUL:
            continue
        middle = row["top1 (공공데이터포털)코드명"].strip()
        if middle not in master:
            raise SystemExit(f"{code}: 중분류 {middle!r} 가 마스터에 없습니다.")
        rows.append(
            {
                "seoul_code": code,
                "seoul_name": row["(서울시)업종명"].strip(),
                "middle_code": middle,
                "match_method": row["판정방식"].strip(),
                "evidence_small": row["근거 소분류"].strip(),
                "note": "",
            }
        )
    return sorted(rows, key=lambda r: r["seoul_code"])


def build_legacy_links(seoul_rows: list[dict], master: dict[str, dict[str, str]]) -> list[dict]:
    """개폐업 70업종 → 중분류. business_lifecycle 은 읽기만 한다."""
    from app.agents.business_lifecycle import mapping as legacy

    seoul_to_middle = {r["seoul_code"]: r["middle_code"] for r in seoul_rows}
    by_legacy: dict[int, dict[str, str]] = {}
    for seoul_code, legacy_id in legacy.SEOUL_TO_SERVICE.items():
        middle = seoul_to_middle.get(seoul_code)
        if middle:
            by_legacy.setdefault(legacy_id, {})[middle] = "seoul"

    # 서울시 경로가 없는 7종. 이름으로 우리 어휘에 직접 잇는다.
    direct = {
        5: ["I206"],
        26: ["G212"],
        43: ["Q101", "Q104"],
        54: ["S208"],
        59: ["S210", "S211"],
        66: ["M105", "M106", "M107"],
        67: ["M109"],
    }
    for legacy_id, codes in direct.items():
        for code in codes:
            if code not in master:
                raise SystemExit(f"legacy {legacy_id}: 중분류 {code!r} 가 마스터에 없습니다.")
            by_legacy.setdefault(legacy_id, {})[code] = "direct"

    rows = []
    for legacy_id in sorted(legacy.SERVICE_INDUSTRIES):
        found = by_legacy.get(legacy_id, {})
        if not found:
            raise SystemExit(f"legacy {legacy_id} 에 연결된 중분류가 없습니다.")
        for middle, route in sorted(found.items()):
            rows.append(
                {
                    "legacy_id": legacy_id,
                    "legacy_name": legacy.SERVICE_INDUSTRIES[legacy_id],
                    "middle_code": middle,
                    "split_count": len(found),
                    "route": route,
                    "note": "서울시 경로 없음" if route == "direct" else "",
                }
            )
    return rows


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="이미 있는 CSV를 덮어씁니다")
    args = parser.parse_args()

    master = {row["middle_code"]: row for row in read_csv(MASTER_PATH)}
    print(f"마스터 {len(master)}종")

    seoul_rows = build_seoul_links(master)
    if guard(SEOUL_LINK_PATH, args.force):
        write_csv(SEOUL_LINK_PATH, SEOUL_COLUMNS, seoul_rows)
        print(f"  서울시 {len(seoul_rows)}종 → {SEOUL_LINK_PATH.name}")

    legacy_rows = build_legacy_links(seoul_rows, master)
    if guard(LEGACY70_LINK_PATH, args.force):
        write_csv(LEGACY70_LINK_PATH, LEGACY_COLUMNS, legacy_rows)
        print(
            f"  개폐업 {len({r['legacy_id'] for r in legacy_rows})}업종 "
            f"{len(legacy_rows)}행 → {LEGACY70_LINK_PATH.name}"
        )

    linked = {r["middle_code"] for r in seoul_rows}
    updated = []
    for code, row in sorted(master.items()):
        updated.append(
            {
                **row,
                "has_seoul": "Y" if code in linked else "N",
                "note": row.get("note") or ("" if code in linked else "서울시 100대에 없음"),
            }
        )
    write_csv(MASTER_PATH, MASTER_COLUMNS, updated)
    print(f"  마스터 갱신 — 서울시 연결 {len(linked)}종 · 단독 {len(master) - len(linked)}종")

    by_method: dict[str, int] = {}
    for row in seoul_rows:
        by_method[row["match_method"]] = by_method.get(row["match_method"], 0) + 1
    print(f"  판정방식 {by_method}  ← '모델'은 사람 검수가 필요합니다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

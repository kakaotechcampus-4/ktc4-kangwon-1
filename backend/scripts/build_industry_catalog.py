"""`app/industries/data/*.csv` 를 검증하고 `catalog.py` 를 생성한다.

CSV 가 깨져도 런타임까지 번지지 않게 하는 게 목적이다. 엑셀로 열었다 저장하면 인코딩이 cp949 로
바뀌고 행이 날아가는 일이 실제로 있었다. 그래서 생성 단계에서 막는다.

    python scripts/build_industry_catalog.py            검증 후 생성물 둘을 다시 만든다
    python scripts/build_industry_catalog.py --check    검증만. CI 용

`--check` 는 디스크의 생성물이 지금 CSV 와 같은지도 본다. CSV 만 고치고 재생성을 잊는 사고를
여기서 잡는다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.industries import (  # noqa: E402
    LEGACY70_LINK_PATH,
    MASTER_JSON_PATH,
    MASTER_PATH,
    PACKAGE_DIR,
    SEOUL_LINK_PATH,
)

CATALOG_PATH = PACKAGE_DIR / "catalog.py"

EXPECTED_COUNT = 75
SOURCE_PERIOD = "2026년 1분기"
EXCLUDED_SEOUL = {"CS300043": "전자상거래업"}
MATCH_METHODS = {"정확", "모델", "부분", "수동"}
LEGACY_RANGE = range(1, 71)

MASTER_COLUMNS = {"middle_code", "middle_name", "major_code", "major_name", "has_seoul", "note"}
SEOUL_COLUMNS = {
    "seoul_code",
    "seoul_name",
    "middle_code",
    "match_method",
    "evidence_small",
    "note",
}
LEGACY_COLUMNS = {"legacy_id", "legacy_name", "middle_code", "split_count", "route", "note"}

SEOUL_CODE = re.compile(r"^CS\d{6}$")
TAIL = re.compile(r"(소매업|판매업|운영업|서비스업|전문점|판매|소매|업소|업|점)$")
NOISE = re.compile(r"[\s\-,·ㆍ/()]|및")


class Failure(Exception):
    pass


def normalize_name(name: str) -> str:
    text = NOISE.sub("", name or "")
    for _ in range(2):
        text = TAIL.sub("", text)
    return text


def read_strict(path: Path, columns: set[str]) -> list[dict[str, str]]:
    """BOM 있는 UTF-8만 받는다. 엑셀 왕복으로 cp949가 된 파일을 여기서 막는다."""
    if not path.exists():
        raise Failure(f"{path.name} 이 없습니다.")
    raw = path.read_bytes()
    if not raw.startswith(b"\xef\xbb\xbf"):
        raise Failure(
            f"{path.name} 이 BOM 있는 UTF-8이 아닙니다.\n"
            "    엑셀에서 열었다 저장하셨나요? '유니코드 텍스트(UTF-8)'로 다시 저장하세요."
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Failure(f"{path.name}: UTF-8로 못 읽습니다 — {exc}") from exc

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or columns - set(reader.fieldnames):
        missing = sorted(columns - set(reader.fieldnames or []))
        raise Failure(f"{path.name}: 컬럼이 빠졌습니다 — {missing}")
    rows = [
        {k: (v or "").strip() for k, v in row.items() if k}
        for row in reader
        if any((v or "").strip() for v in row.values())
    ]
    return rows


def check_master(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    if len(rows) != EXPECTED_COUNT:
        raise Failure(f"마스터가 {len(rows)}행입니다. {EXPECTED_COUNT}행이어야 합니다.")

    master: dict[str, dict[str, str]] = {}
    normalized: dict[str, str] = {}
    majors: dict[str, str] = {}
    for row in rows:
        code = row["middle_code"]
        if not code or not row["middle_name"]:
            raise Failure(f"필수 값이 비었습니다 — {row}")
        if code in master:
            raise Failure(f"중분류 코드가 중복입니다 — {code}")
        master[code] = row

        key = normalize_name(row["middle_name"])
        if key in normalized:
            raise Failure(
                f"정규화하면 같아지는 업종명이 둘입니다 — {normalized[key]} / {row['middle_name']}"
            )
        normalized[key] = row["middle_name"]

        known = majors.setdefault(row["major_code"], row["major_name"])
        if known != row["major_name"]:
            raise Failure(
                f"대분류 {row['major_code']} 이름이 둘입니다 — {known} / {row['major_name']}"
            )
        if row["has_seoul"] not in {"Y", "N"}:
            raise Failure(f"{code}: has_seoul 이 Y/N 이 아닙니다 — {row['has_seoul']!r}")
    return master


def check_seoul(rows: list[dict[str, str]], master: dict[str, dict[str, str]]) -> None:
    seen: set[str] = set()
    for row in rows:
        code = row["seoul_code"]
        if not SEOUL_CODE.match(code):
            raise Failure(f"서울시 코드 형식이 아닙니다 — {code!r}")
        if code in EXCLUDED_SEOUL:
            raise Failure(f"{code} 는 제외하기로 한 업종인데 연결표에 있습니다.")
        if code in seen:
            raise Failure(f"서울시 코드가 중복입니다 — {code}")
        seen.add(code)
        if row["middle_code"] not in master:
            raise Failure(f"{code}: 중분류 {row['middle_code']!r} 가 마스터에 없습니다.")
        if row["match_method"] not in MATCH_METHODS:
            raise Failure(f"{code}: 판정방식이 허용값이 아닙니다 — {row['match_method']!r}")

    linked = {row["middle_code"] for row in rows}
    for code, row in master.items():
        expected = "Y" if code in linked else "N"
        if row["has_seoul"] != expected:
            raise Failure(
                f"{code}: has_seoul 이 {row['has_seoul']} 인데 실제 연결은 {expected} 입니다."
            )


def check_legacy(rows: list[dict[str, str]], master: dict[str, dict[str, str]]) -> None:
    by_id: dict[int, set[str]] = {}
    for row in rows:
        try:
            legacy_id = int(row["legacy_id"])
        except ValueError as exc:
            raise Failure(f"legacy_id 가 정수가 아닙니다 — {row['legacy_id']!r}") from exc
        if legacy_id not in LEGACY_RANGE:
            raise Failure(f"legacy_id 가 1~70 밖입니다 — {legacy_id}")
        if row["middle_code"] not in master:
            raise Failure(
                f"legacy {legacy_id}: 중분류 {row['middle_code']!r} 가 마스터에 없습니다."
            )
        if row["route"] not in {"seoul", "direct"}:
            raise Failure(f"legacy {legacy_id}: route 가 허용값이 아닙니다 — {row['route']!r}")
        by_id.setdefault(legacy_id, set()).add(row["middle_code"])

    missing = sorted(set(LEGACY_RANGE) - set(by_id))
    if missing:
        raise Failure(f"개폐업 업종이 연결표에 없습니다 — {missing}")
    for row in rows:
        legacy_id = int(row["legacy_id"])
        if int(row["split_count"]) != len(by_id[legacy_id]):
            raise Failure(f"legacy {legacy_id}: split_count 가 실제 개수와 다릅니다.")


def fingerprint(*groups: list[dict[str, str]]) -> str:
    """원본 CSV 내용에서 나오는 지문.

    생성 날짜를 쓰면 내용이 같아도 날짜만 달라져 `--check` 가 매일 실패한다. 실제로 겪었다.
    """
    digest = hashlib.sha256()
    for rows in groups:
        for row in rows:
            digest.update(repr(sorted(row.items())).encode("utf-8"))
    return digest.hexdigest()[:12]


def render(
    master: dict[str, dict[str, str]],
    seoul: list[dict[str, str]],
    legacy: list[dict[str, str]],
) -> str:
    def dict_block(name: str, annotation: str, items: list[tuple[str, str]], comment: str) -> str:
        lines = [f"# {comment}", f"{name}: {annotation} = {{"]
        lines += [f"    {k}: {v}," for k, v in items]
        lines += ["}", ""]
        return "\n".join(lines)

    industries = [(repr(c), repr(r["middle_name"])) for c, r in sorted(master.items())]
    majors = [
        (repr(c), f"({r['major_code']!r}, {r['major_name']!r})") for c, r in sorted(master.items())
    ]
    seoul_to = [
        (repr(r["seoul_code"]), repr(r["middle_code"]))
        for r in sorted(seoul, key=lambda r: r["seoul_code"])
    ]

    industry_to_seoul: dict[str, list[str]] = {}
    for row in sorted(seoul, key=lambda r: r["seoul_code"]):
        industry_to_seoul.setdefault(row["middle_code"], []).append(row["seoul_code"])
    to_seoul = [(repr(c), repr(tuple(v))) for c, v in sorted(industry_to_seoul.items())]

    without = [
        (repr(c), repr(r["middle_name"]))
        for c, r in sorted(master.items())
        if r["has_seoul"] == "N"
    ]

    legacy_to: dict[int, list[str]] = {}
    for row in sorted(legacy, key=lambda r: (int(r["legacy_id"]), r["middle_code"])):
        legacy_to.setdefault(int(row["legacy_id"]), []).append(row["middle_code"])
    legacy_block = [(str(k), repr(tuple(v))) for k, v in sorted(legacy_to.items())]

    industry_to_legacy: dict[str, list[int]] = {}
    for legacy_id, codes in sorted(legacy_to.items()):
        for code in codes:
            industry_to_legacy.setdefault(code, []).append(legacy_id)
    to_legacy = [(repr(c), repr(tuple(v))) for c, v in sorted(industry_to_legacy.items())]

    excluded = [(repr(k), repr(v)) for k, v in sorted(EXCLUDED_SEOUL.items())]

    head = f'''"""팀 공통 업종 어휘 — 자동 생성 파일입니다. 고치지 마세요.

원본은 `app/industries/data/*.csv` 이고, 이 파일은
`python scripts/build_industry_catalog.py` 로 다시 만듭니다.

개폐업 `mapping.py` 와 같은 모양으로 씁니다 — `INDUSTRIES` 가 `SERVICE_INDUSTRIES` 자리,
`SEOUL_TO_INDUSTRY` 가 `SEOUL_TO_SERVICE` 자리입니다.
"""

from __future__ import annotations

from typing import Final

CATALOG_VERSION: Final = "{fingerprint(list(master.values()), seoul, legacy)}"
SOURCE_PERIOD: Final = "{SOURCE_PERIOD}"
EXPECTED_INDUSTRY_COUNT: Final = {EXPECTED_COUNT}

'''

    blocks = [
        dict_block(
            "INDUSTRIES",
            "Final[dict[str, str]]",
            industries,
            "중분류 코드 → 업종명. 이 어휘가 기준이다.",
        ),
        dict_block(
            "INDUSTRY_MAJORS",
            "Final[dict[str, tuple[str, str]]]",
            majors,
            "중분류 코드 → (대분류 코드, 대분류명)",
        ),
        dict_block(
            "SEOUL_TO_INDUSTRY",
            "Final[dict[str, str]]",
            seoul_to,
            "서울시 생활밀접업종 코드 → 중분류 코드",
        ),
        dict_block(
            "INDUSTRY_TO_SEOUL",
            "Final[dict[str, tuple[str, ...]]]",
            to_seoul,
            "중분류 코드 → 거기로 접히는 서울시 코드들",
        ),
        dict_block(
            "EXCLUDED_SEOUL_INDUSTRIES",
            "Final[dict[str, str]]",
            excluded,
            "서울시에 있으나 쓰지 않는 업종. 무점포라 상가 자료에 안 잡힌다.",
        ),
        dict_block(
            "INDUSTRIES_WITHOUT_SEOUL",
            "Final[dict[str, str]]",
            without,
            "서울시 100대 생활밀접업종만으로는 만들 수 없는 업종.",
        ),
        dict_block(
            "LEGACY70_TO_INDUSTRY",
            "Final[dict[int, tuple[str, ...]]]",
            legacy_block,
            "개폐업 70업종 ID → 중분류. 마이그레이션용이며 개폐업이 옮겨오면 지운다.",
        ),
        dict_block(
            "INDUSTRY_TO_LEGACY70",
            "Final[dict[str, tuple[int, ...]]]",
            to_legacy,
            "위의 역방향. 값이 여럿이면 점수를 그대로 합치면 안 된다.",
        ),
    ]
    return head + "\n".join(blocks)


def render_json(
    master: dict[str, dict[str, str]],
    seoul: list[dict[str, str]],
    legacy: list[dict[str, str]],
) -> str:
    """공통 75개 중분류의 배포용 업종 목록.

    운영 개폐업 분석의 `industry_id`는 `code`에 담긴 문자열 중분류 코드다.
    이 JSON의 정수 `industry_id`는 코드 오름차순의 보조 일련번호이며 운영 ID가 아니다.
    과거 legacy70 정수 ID는 별도 연결표에 보관하며 이 일련번호와 구분한다.
    """
    industries = [
        {
            "industry_id": index,
            "code": code,
            "major": row["major_name"],
            "name": row["middle_name"],
        }
        for index, (code, row) in enumerate(sorted(master.items()), 1)
    ]
    payload = {
        "version": "1.0",
        # catalog.py 의 CATALOG_VERSION 과 같은 값이다. 둘이 같은 CSV 에서 나왔는지 대조할 수 있다.
        "catalog_version": fingerprint(list(master.values()), seoul, legacy),
        "industry_count": len(industries),
        "industries": industries,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def ruff_format(text: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "-", "--stdin-filename", "catalog.py"],
        input=text,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise Failure(f"ruff format 실패 — {result.stderr.strip()}")
    return result.stdout


def _current(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="검증만 하고 쓰지 않습니다")
    args = parser.parse_args()

    try:
        master_rows = read_strict(MASTER_PATH, MASTER_COLUMNS)
        seoul_rows = read_strict(SEOUL_LINK_PATH, SEOUL_COLUMNS)
        legacy_rows = read_strict(LEGACY70_LINK_PATH, LEGACY_COLUMNS)

        master = check_master(master_rows)
        check_seoul(seoul_rows, master)
        check_legacy(legacy_rows, master)
        rendered = ruff_format(render(master, seoul_rows, legacy_rows))
        rendered_json = render_json(master, seoul_rows, legacy_rows)
    except Failure as exc:
        print(f"검증 실패: {exc}")
        return 1

    linked = sum(1 for r in master.values() if r["has_seoul"] == "Y")
    by_method: dict[str, int] = {}
    for row in seoul_rows:
        by_method[row["match_method"]] = by_method.get(row["match_method"], 0) + 1

    print(f"업종 {len(master)}종 — 서울시 연결 {linked} · 단독 {len(master) - linked}")
    print(f"서울시 연결 {len(seoul_rows)}행 · 판정방식 {by_method}")
    print(f"  '모델' {by_method.get('모델', 0)}건은 사람 검수가 필요합니다")
    print(f"개폐업 연결 {len(legacy_rows)}행 / {len({r['legacy_id'] for r in legacy_rows})}업종")

    outputs = ((CATALOG_PATH, rendered), (MASTER_JSON_PATH, rendered_json))

    stale = [path.name for path, text in outputs if _current(path) != text]
    print()

    if args.check:
        if stale:
            print(f"{' · '.join(stale)} 가 CSV와 다릅니다. --check 없이 다시 돌려 생성하세요.")
            return 1
        print("catalog.py 와 industry_master.json 이 CSV와 같습니다.")
        return 0

    for path, text in outputs:
        if _current(path) == text:
            print(f"{path.name} 변경 없음")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"{path.name} 생성 완료 ({len(text.splitlines())}줄)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

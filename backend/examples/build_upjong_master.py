"""상권업종분류 중분류 마스터 파일을 만듭니다."""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

from app.agents.commercial_area.client import StoreClient
from app.agents.commercial_area.config import Settings, load_dotenv_if_present
from app.agents.commercial_area.schemas import MiddleCode
from app.agents.commercial_area.upjong import master_from_stores, write_master

OFFICIAL_COLUMN_CANDIDATES = {
    "middle_code": ("중분류코드", "indsMclsCd", "상권업종중분류코드"),
    "middle_name": ("중분류명", "indsMclsNm", "상권업종중분류명"),
    "major_code": ("대분류코드", "indsLclsCd", "상권업종대분류코드"),
    "major_name": ("대분류명", "indsLclsNm", "상권업종대분류명"),
}

SAMPLE_POINTS = (
    (37.5006, 127.0364),
    (37.5665, 126.9780),
    (37.4784, 126.9516),
    (35.1587, 129.1604),
    (35.8714, 128.6014),
)


def read_csv_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"인코딩을 알 수 없습니다: {path}")


def from_official_csv(path: Path) -> list[MiddleCode]:
    with io.StringIO(read_csv_text(path)) as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        resolved = {}
        for target, candidates in OFFICIAL_COLUMN_CANDIDATES.items():
            match = next((c for c in candidates if c in fields), None)
            if not match:
                raise SystemExit(f"필요한 컬럼을 찾지 못했습니다: {target} (후보 {candidates})")
            resolved[target] = match

        unique: dict[str, MiddleCode] = {}
        for row in reader:
            code = (row[resolved["middle_code"]] or "").strip()
            if not code:
                continue
            unique.setdefault(
                code,
                MiddleCode(
                    code=code,
                    name=(row[resolved["middle_name"]] or "").strip(),
                    major_code=(row[resolved["major_code"]] or "").strip(),
                    major_name=(row[resolved["major_name"]] or "").strip(),
                ),
            )
    return sorted(unique.values(), key=lambda r: r.code)


def from_api(settings: Settings, radius: int) -> list[MiddleCode]:
    client = StoreClient(settings)
    collected: dict[str, MiddleCode] = {}
    try:
        for lat, lon in SAMPLE_POINTS:
            stores, meta = client.stores_in_radius(lat, lon, radius)
            for row in master_from_stores(stores):
                collected.setdefault(row.code, row)
            print(f"  ({lat}, {lon}) 점포 {len(stores)}건 → 누적 중분류 {len(collected)}개")
    finally:
        client.close()
    return sorted(collected.values(), key=lambda r: r.code)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-csv", type=Path)
    parser.add_argument("--radius", type=int, default=1000)
    args = parser.parse_args()

    load_dotenv_if_present()
    settings = Settings.from_env()

    if args.official_csv:
        rows = from_official_csv(args.official_csv)
        source = f"공식 CSV {args.official_csv.name}"
    else:
        if not settings.sbiz_service_key:
            print("SBIZ_SERVICE_KEY가 없습니다. --official-csv 로 공식 업종코드 파일을 넘기거나 키를 설정하세요.")
            return 1
        print("API 응답에서 업종 코드를 수집합니다. 공식 파일보다 누락 가능성이 있습니다.")
        rows = from_api(settings, args.radius)
        source = "API 응답 수집"

    write_master(settings.upjong_master_path, rows)
    print(f"\n{source} → {settings.upjong_master_path}")
    print(f"중분류 {len(rows)}개 저장 (공식 체계는 75개)")
    if len(rows) < 75:
        print("75개보다 적습니다. 공식 업종코드 CSV로 다시 만드는 것을 권장합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

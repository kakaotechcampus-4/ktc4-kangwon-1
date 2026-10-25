import argparse
import json
import sys
from pathlib import Path

from app.local_data.database import LocalDataDB, default_path

POPULATION_SOURCES = ("stores", "lifecycle", "floating", "resident", "worker")
REQUIRED_SOURCES = (*POPULATION_SOURCES, "areas")
QUARTER_COUNTS = {"lifecycle": 12, "floating": 5}


class HistoryDataError(ValueError):
    pass


def check_history_db(path: Path, quarter: str) -> dict:
    resolved = Path(path).resolve()
    if resolved == default_path().resolve():
        raise HistoryDataError("서비스 자료 DB는 백테스트에 쓸 수 없습니다.")
    if not resolved.exists():
        raise HistoryDataError(f"자료 DB가 없습니다: {resolved}")
    db = LocalDataDB(resolved)
    found = [v for v in (db.version(vid) for vid in db.active_versions()) if v is not None]
    by_source: dict[str, list[dict]] = {}
    for version in found:
        by_source.setdefault(version["source"], []).append(version)
    missing = [source for source in REQUIRED_SOURCES if source not in by_source]
    if missing:
        raise HistoryDataError(f"활성 원천이 빠졌습니다: {missing}")
    for source, count in QUARTER_COUNTS.items():
        if len(by_source[source]) != count:
            raise HistoryDataError(f"{source} 원천은 {count}분기가 필요합니다.")
    latest = {source: max(v["quarter"] for v in by_source[source]) for source in POPULATION_SOURCES}
    wrong = {source: value for source, value in latest.items() if value != quarter}
    if wrong:
        raise HistoryDataError(f"최신 분기가 {quarter}가 아닌 원천: {wrong}")
    empty = sorted({v["source"] for v in found if not v["row_count"]})
    if empty:
        raise HistoryDataError(f"행이 없는 원천: {empty}")
    return {
        "path": str(resolved),
        "release_count": db.release_count(),
        "versions": [
            {key: v[key] for key in ("version_id", "source", "quarter", "row_count", "file_hash")}
            for v in sorted(found, key=lambda v: (v["source"], v["quarter"]))
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="과거 시점 자료 DB를 점검합니다.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--quarter", default="20234")
    args = parser.parse_args(argv)
    try:
        info = check_history_db(args.data, args.quarter)
    except HistoryDataError as error:
        print(f"점검 실패: {error}", file=sys.stderr)
        return 1
    rows: dict[str, int] = {}
    for version in info["versions"]:
        rows[version["source"]] = rows.get(version["source"], 0) + version["row_count"]
    report = {
        "release_count": info["release_count"],
        "versions": len(info["versions"]),
        "rows": rows,
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

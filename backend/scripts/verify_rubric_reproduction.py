"""커밋 제외 표본과 기준 결과를 읽기만 하며 408개 업종 결과를 비교합니다."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agentic.scoring import evaluate  # noqa: E402


def verify(folder: Path) -> dict:
    expected = json.loads((folder / "dryrun-results.json").read_text(encoding="utf-8"))["reports"]
    paths = sorted(folder.glob("sample-*.json"))
    if len(paths) != 8 or len(expected) != 8:
        raise ValueError("기준 결과와 8개 주소 표본이 필요합니다.")
    by_address = {r["address"]: r for r in expected}
    matched, differences, badges = 0, [], Counter()
    for path in paths:
        report = evaluate(json.loads(path.read_text(encoding="utf-8")))
        old = by_address[report["address"]]
        rows = {r["code"]: r for r in old["rows"]}
        for row in report["rows"]:
            changed = [
                key
                for key in ("items", "lower", "upper", "applicable_weight", "badge", "coverage")
                if row[key] != rows[row["code"]][key]
            ]
            if changed:
                differences.append({"sample": path.name, "code": row["code"], "fields": changed})
            else:
                matched += 1
            badges[row["badge"]] += 1
        if [r["code"] for r in report["top5"]] != [r["code"] for r in old["top5"]]:
            differences.append({"sample": path.name, "fields": ["top5"]})
    return {
        "matched": matched,
        "total": sum(badges.values()),
        "badges": dict(badges),
        "differences": differences,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=Path, default=Path(__file__).resolve().parents[1] / "cache/rubric_samples"
    )
    args = parser.parse_args()
    result = verify(args.samples)
    print(json.dumps(result, ensure_ascii=False))
    return (
        0
        if result["matched"] == 408
        and result["badges"] == {"추천": 9, "조건부": 1, "보류": 377, "비추천": 21}
        and not result["differences"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

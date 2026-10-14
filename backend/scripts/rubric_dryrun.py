"""v0.8 시험 채점. 운영 채점 엔진을 재사용해 LLM 없이 저장된 표본만 읽는다."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agentic.scoring import (  # noqa: E402,F401
    AMBIGUITIES,
    WEIGHTS,
    evaluate,
    population_baseline,
    profiles,
    regulation,
    result,
    score_item,
    seoul_age_share,
    summarize,
    valid,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=Path, default=Path(__file__).resolve().parents[1] / "cache/rubric_samples"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    args.samples = args.samples.resolve()
    if args.samples.is_relative_to(root) and not args.samples.is_relative_to(
        root / "backend/cache"
    ):
        parser.error("실데이터 출력은 저장소 밖 또는 backend/cache만 허용합니다.")
    samples = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(args.samples.glob("sample-*.json"))
    ]
    if not samples:
        raise SystemExit("표본 없음: 먼저 승인된 자료를 수집하세요.")
    reports = [evaluate(s) for s in samples]
    sensitivities = {}
    for parameter, base in [
        ("coverage_min", 0.75),
        ("lower_min", 0.65),
        ("upper_max", 0.45),
        ("domain_min", 0.5),
        ("exposure_min", 40),
    ]:
        sensitivities[parameter] = {
            str(round(base * factor, 3)): [
                evaluate(s, **{parameter: base * factor})["badges"] for s in samples
            ]
            for factor in [0.8, 0.9, 1, 1.1, 1.2]
        }
    unknown = {
        item: sum(
            r["items"][item]["status"] == "unknown" for report in reports for r in report["rows"]
        )
        / (len(reports) * 51)
        for item in WEIGHTS
    }
    out = {
        "reports": reports,
        "unknown_rates": unknown,
        "sensitivity": sensitivities,
        "unimplemented_rules": AMBIGUITIES,
        "lower_threshold_comparison": {
            str(threshold): [evaluate(s, lower_min=threshold)["badges"] for s in samples]
            for threshold in [0.60, 0.65, 0.70]
        },
    }
    (args.samples / "dryrun-results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "top5": [
                    {
                        "address": r["address"],
                        "candidates": [
                            (v["code"], v["badge"], v["lower"], v["upper"]) for v in r["top5"]
                        ],
                    }
                    for r in reports
                ],
                "badges": [r["badges"] for r in reports],
                "unknown_rates": unknown,
                "unimplemented_rules": AMBIGUITIES,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

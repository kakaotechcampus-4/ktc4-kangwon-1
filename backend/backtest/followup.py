"""원본 A/B를 보존하고 시설 조회를 생략한 영향만 오프라인에서 분리합니다."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from app.agentic.scoring import WEIGHTS, profiles
from app.industries import DATA_DIR
from app.industries.catalog import INDUSTRIES
from backtest.ab_metrics import paired_cluster_interval, summarize
from backtest.comparison import CODE_ITEMS, code_summary
from backtest.offline import block_network, write_json

C_ITEMS = tuple(name for name in CODE_ITEMS if name != "C4")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def common_score(row: dict) -> dict:
    # 원본 상태를 바꾸지 않고, 모든 업종에 같은 평가 항목 집합을 적용합니다.
    code_summary(row)
    items = row["items"]
    weight = sum(WEIGHTS[name] for name in C_ITEMS)
    applicable = sum(WEIGHTS[name] for name in C_ITEMS if items[name]["status"] != "n.a.")
    points = sum(items[name]["points"] for name in C_ITEMS if items[name]["status"] == "observed")
    return {
        "weight": weight,
        "applicable": applicable,
        "points": points,
        "normalized": weight * points / applicable if applicable else None,
    }


def profile_exclusions(profile: dict) -> dict:
    rules = {
        "D1": (profile.get("pattern") == "무관", "rationale"),
        "D2": (profile.get("day_pattern") == "무관", "day_pattern_rationale"),
        "D3": (profile.get("target_population") in (None, "", "—"), "target_population_rationale"),
        "C4": (not profile.get("required_facilities"), "required_facilities_rationale"),
    }
    return {name: profile.get(reason, "") for name, (excluded, reason) in rules.items() if excluded}


def extend_case(case: dict, saved: dict) -> dict:
    rows = saved["scores"]
    if len(rows) != 51 or {row["code"] for row in rows} != set(INDUSTRIES):
        raise ValueError("51업종 전체 점수가 필요합니다.")
    summaries = {row["code"]: common_score(row) for row in rows}
    allowed = [
        row
        for row in rows
        if row["regulation"] != "금지"
        and not row.get("space", {}).get("excluded", False)
        and summaries[row["code"]]["normalized"] is not None
    ]
    ordered = sorted(
        allowed,
        key=lambda row: (
            -(summaries[row["code"]]["normalized"] + row.get("space", {}).get("adjustment", 0)),
            -(row["coverage"] or 0),
            row["code"],
        ),
    )
    return {
        **case,
        "orders": {**case["orders"], "C": [row["code"] for row in ordered]},
        "C_target_score": summaries[case["target"]],
    }


def run(baseline: Path, scores: Path, out: Path) -> dict:
    if out.exists():
        raise ValueError("결과 폴더가 이미 있습니다.")
    with block_network():
        source = baseline / "results.json"
        previous = json.loads(source.read_text(encoding="utf-8"))
        manifest_path = scores / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if digest(manifest_path) != previous["provenance"]["scores_manifest_sha256"]:
            raise ValueError("원본 채점 manifest가 달라졌습니다.")
        profile_path = DATA_DIR / "industry_profile.csv"
        original_profile_hash = next(
            value
            for name, value in manifest["source_hashes"].items()
            if name.replace("\\", "/") == "app/industries/data/industry_profile.csv"
        )
        if digest(profile_path) != original_profile_hash:
            raise ValueError("원본 채점과 업종 프로필이 다릅니다.")
        profile_rows = profiles()
        cases, changed, hashes = [], [], {}
        na_mismatches, fixed_c1, facility = [], Counter(), Counter()
        lifecycle_unknown = Counter()
        quality = {method: Counter() for method in ("A", "B", "C")}
        for original in previous["cases"]:
            path = scores / f"{original['id']}.json"
            if digest(path) != previous["provenance"]["case_sha256"][path.name]:
                raise ValueError("원본 사례 점수가 달라졌습니다.")
            hashes[path.name] = digest(path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved["id"] != original["id"] or saved["site"] != original["site"]:
                raise ValueError("사례 ID·좌표가 원본과 다릅니다.")
            case = extend_case(original, saved)
            lookup = {row["code"]: row for row in saved["scores"]}
            for code, row in lookup.items():
                expected = profile_exclusions(profile_rows[code])
                actual = {name for name, item in row["items"].items() if item["status"] == "n.a."}
                if set(expected) != actual:
                    na_mismatches.append(
                        {
                            "id": case["id"],
                            "code": code,
                            "expected": sorted(expected),
                            "actual": sorted(actual),
                        }
                    )
                c1 = row["items"]["C1"]
                if c1["status"] == "observed" and c1.get("value") is None:
                    fixed_c1[code] += 1
                facility[row["items"]["C4"]["status"]] += 1
                if all(row["items"][f"S{i}"]["status"] == "unknown" for i in range(1, 5)):
                    lifecycle_unknown[code] += 1
            for method in quality:
                for code in case["orders"][method][:5]:
                    statuses = [lookup[code]["items"][name]["status"] for name in ("D1", "D3")]
                    quality[method]["top5_n"] += 1
                    quality[method]["demand_both_na"] += statuses == ["n.a.", "n.a."]
                    quality[method]["demand_missing"] += (
                        "observed" not in statuses and "unknown" in statuses
                    )
            target = case["target"]
            hit_a, hit_b = [target in case["orders"][method][:5] for method in ("A", "B")]
            if hit_a != hit_b:
                row = lookup[target]
                changed.append(
                    {
                        "id": case["id"],
                        "target": target,
                        "name": row["name"],
                        "change": "gained" if hit_b else "lost",
                        "ranks": {
                            m: case["orders"][m].index(target) + 1
                            if target in case["orders"][m]
                            else None
                            for m in ("A", "B", "C")
                        },
                        "groups": {
                            prefix: sum(
                                item["points"] or 0
                                for name, item in row["items"].items()
                                if name.startswith(prefix)
                            )
                            for prefix in ("D", "C", "S")
                        },
                        "profile_exclusions": profile_exclusions(profile_rows[target]),
                        "items": row["items"],
                        "baseline_score": case["target_score"],
                        "C_score": case["C_target_score"],
                    }
                )
            cases.append(case)
        if not cases or facility["observed"]:
            raise ValueError("이 실험은 시설을 관측하지 않은 원본 표본에서만 실행합니다.")
        if na_mismatches:
            raise ValueError("원본 미적용 상태가 승인 프로필과 다릅니다.")
        methods = ("A", "B", "C", "stores")
        metrics = {method: summarize(cases, method) for method in methods}
        for method in ("A", "B", "stores"):
            if metrics[method] != previous["metrics"][method]:
                raise ValueError("기존 A/B 지표가 재현되지 않았습니다.")
        result = {
            "kind": "offline-common-items-development-diagnostic",
            "settings": {
                "C_items": list(C_ITEMS),
                "C_weight": sum(WEIGHTS[k] for k in C_ITEMS),
                "weights": WEIGHTS,
                "excluded_for_all": ["C4"],
                "llm_calls": 0,
                "tie_break": "기존 서비스 coverage, 업종 코드",
                "interpretation": "시설 미조회 영향을 분리한 개선용 진단; 독립 검증 아님",
            },
            "metrics": metrics,
            "paired_hit5_difference": {
                "C_minus_A": paired_cluster_interval(cases, "A", "C"),
                "C_minus_B": paired_cluster_interval(cases, "B", "C"),
            },
            "audit": {
                "case_n": len(cases),
                "industry_score_n": 51 * len(cases),
                "na_profile_mismatch_n": len(na_mismatches),
                "facility_statuses": dict(facility),
                "fixed_c1_rows": dict(fixed_c1),
                "lifecycle_all_unknown_by_industry": dict(lifecycle_unknown),
                "changed_label_cases": changed,
                "quality": quality,
            },
            "cases": cases,
            "provenance": {
                "baseline_sha256": digest(source),
                "manifest_sha256": digest(manifest_path),
                "profile_sha256": digest(profile_path),
                "code_sha256": digest(Path(__file__)),
                "metrics_sha256": digest(Path(__file__).with_name("ab_metrics.py")),
                "case_sha256": hashes,
            },
        }
        out.mkdir(parents=True)
        write_json(out / "results.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="시설 항목 제외의 단일 후속 실험을 집계합니다.")
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run(args.baseline, args.scores, args.out)
    print(
        json.dumps(
            {
                "hit5": {m: v["hit5"] for m, v in result["metrics"].items()},
                "differences": result["paired_hit5_difference"],
                "na_mismatch_n": result["audit"]["na_profile_mismatch_n"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

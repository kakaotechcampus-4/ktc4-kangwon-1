"""기존 위치에서 시점을 맞춘 80점과 이전 결과를 같은 방식으로 비교합니다."""

import argparse
import copy
import csv
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from statistics import mean

from app.agentic import scoring
from app.industries.catalog import INDUSTRIES
from app.schemas import AnalysisTask, Site
from backtest.ab_metrics import paired_cluster_interval, rank_of, summarize
from backtest.cohort import build as build_cohort
from backtest.followup import C_ITEMS, common_score
from backtest.forward import CachedAdapter
from backtest.licensing import sha256
from backtest.lifecycle_scores import grade_for
from backtest.offline import block_network, load_sites, write_json
from backtest.past_baselines import build as build_baselines
from backtest.past_baselines import calibrated

METHODS = ("before_80", "past_80", "past_continuous_80")
_adapter = None
_baselines = None


def label_density_baseline(rows: list[dict], quarter: str) -> int:
    """운영 설명의 고정 연도를 검증에 실제 사용한 분기로 정정합니다. 점수는 보존합니다."""
    old = "현재 API/2026Q2 밀도 기준선 시점 차이 있음"
    new = f"검증용 점포·서울 500m 밀도 기준선 분기 {quarter} 일치(현행 지도 기준)"
    count = 0
    for row in rows:
        item = row["items"]["C1"]
        if old in item["reason"]:
            item["reason"] = item["reason"].replace(old, new)
            count += 1
    return count


def continuous_rows(rows: list[dict]) -> list[dict]:
    changed = copy.deepcopy(rows)
    for row in changed:
        for name in ("S1", "S2", "S3", "S4"):
            item = row["items"][name]
            if item["status"] != "observed":
                continue
            item["grade"] = grade_for(name, item["value"], continuous=True)
            item["points"] = scoring.WEIGHTS[name] * item["grade"] / 4
            item["reason"] += " · 실험용 고정 연속 등급"
    return changed


def order80(rows: list[dict]) -> list[str]:
    summaries = {r["code"]: common_score(r) for r in rows}
    allowed = [
        r
        for r in rows
        if r["regulation"] != "금지" and not r.get("space", {}).get("excluded", False)
    ]
    # 이전 C 실험과 환산·동점 기준을 같게 유지합니다. 미확인 배점은 분모에 남습니다.
    return [
        r["code"]
        for r in sorted(
            allowed,
            key=lambda r: (
                -(summaries[r["code"]]["normalized"] + r.get("space", {}).get("adjustment", 0)),
                -(r["coverage"] or 0),
                r["code"],
            ),
        )
    ]


def init_worker(data: str, baselines: dict):
    global _adapter, _baselines
    with block_network():
        _adapter = CachedAdapter(Path(data), None)
    _baselines = baselines


def score_site(case: dict) -> dict:
    with block_network(), calibrated(_baselines):
        task = AnalysisTask(
            request_id="past80-" + case["id"], site=Site.model_validate(case["site"]), radius_m=500
        )
        data = _adapter.analyze(task)
        data["education_zones"] = {"status": "not_queried", "zones": []}
        data["facilities"] = {"data": {"queries": {}, "places": {}}}
        rows = scoring.evaluate(data)["rows"]
        label_density_baseline(rows, _baselines["cutoff"])
        if {r["code"] for r in rows} != set(INDUSTRIES):
            raise ValueError("51업종 전체 점수가 필요합니다.")
        smooth = continuous_rows(rows)
        return {
            "id": case["id"],
            "site": case["site"],
            "target": case["target_industry_code"],
            "data": data,
            "scores": rows,
            "continuous_S_items": {
                r["code"]: {k: r["items"][k] for k in ("S1", "S2", "S3", "S4")} for r in smooth
            },
            "orders": {"past_80": order80(rows), "past_continuous_80": order80(smooth)},
            "score80": {r["code"]: common_score(r) for r in rows},
            "continuous_score80": {r["code"]: common_score(r) for r in smooth},
        }


def csv_file(path: Path, rows: list[dict]):
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def item_kind(name: str, item: dict) -> str:
    return (
        "profile_fixed"
        if name == "C1" and item["status"] == "observed" and item.get("value") is None
        else item["status"]
    )


def export_scores(out: Path, paired: list[dict], before: dict, after: dict) -> None:
    details, industry, items = [], [], []
    grouped = defaultdict(list)
    for case in paired:
        key = case["id"]
        a, b = (
            {r["code"]: r for r in before[key]["scores"]},
            {r["code"]: r for r in after[key]["scores"]},
        )
        ranks = {m: {c: i + 1 for i, c in enumerate(case["orders"][m])} for m in METHODS}
        for code, name in INDUSTRIES.items():
            old, new = common_score(a[code]), after[key]["score80"][code]
            cont = after[key]["continuous_score80"][code]
            row = {
                "사례ID": key,
                "주소": case["site"]["input_address"],
                "실제업종코드": case["target"],
                "업종코드": code,
                "업종": name,
                "이전80환산점수": old["normalized"],
                "과거정렬80환산점수": new["normalized"],
                "S연속안80환산점수": cont["normalized"],
                "이전순위": ranks["before_80"].get(code),
                "과거정렬순위": ranks["past_80"].get(code),
                "S연속안순위": ranks["past_continuous_80"].get(code),
                "과거확인점수합": new["points"],
                "과거적용배점": new["applicable"],
                "과거80자료충족도": sum(
                    scoring.WEIGHTS[k]
                    for k in C_ITEMS
                    if b[code]["items"][k]["status"] == "observed"
                )
                / new["applicable"],
            }
            for prefix, keys in (
                ("D", ("D1", "D2", "D3", "D4")),
                ("C1", ("C1",)),
                ("S", ("S1", "S2", "S3", "S4")),
            ):
                for label, source_rows in (("이전", a), ("과거", b)):
                    row[f"{label}{prefix}확인점수합"] = sum(
                        source_rows[code]["items"][k]["points"] or 0 for k in keys
                    )
            details.append(row)
            grouped[code].append((a[code], b[code], row))
    for code, name in INDUSTRIES.items():
        values = grouped[code]
        summary = {"업종코드": code, "업종": name, "위치수": len(values)}
        for field in (
            "이전80환산점수",
            "과거정렬80환산점수",
            "S연속안80환산점수",
            "이전순위",
            "과거정렬순위",
            "S연속안순위",
            "이전D확인점수합",
            "과거D확인점수합",
            "이전C1확인점수합",
            "과거C1확인점수합",
            "이전S확인점수합",
            "과거S확인점수합",
            "과거80자료충족도",
        ):
            summary[field + "평균"] = mean(r[field] for _, _, r in values)
        for label, field in (
            ("이전", "이전순위"),
            ("과거", "과거정렬순위"),
            ("연속안", "S연속안순위"),
        ):
            summary[label + "TOP5횟수"] = sum(r[field] <= 5 for _, _, r in values)
        industry.append(summary)
        for item in C_ITEMS:
            record = {"업종코드": code, "업종": name, "문항": item, "배점": scoring.WEIGHTS[item]}
            for label, position in (("이전", 0), ("과거", 1)):
                observed = [
                    v[position]["items"][item]
                    for v in values
                    if v[position]["items"][item]["status"] == "observed"
                ]
                states = Counter(item_kind(item, v[position]["items"][item]) for v in values)
                record[label + "관측수"] = states["observed"]
                record[label + "프로필고정수"] = states["profile_fixed"]
                record[label + "미확인수"] = states["unknown"]
                record[label + "미적용수"] = states["n.a."]
                record[label + "관측또는고정점수평균"] = (
                    mean(v["points"] for v in observed) if observed else None
                )
            items.append(record)
    csv_file(out / "위치별_51업종_점수.csv", details)
    csv_file(out / "51업종_점수요약.csv", industry)
    csv_file(out / "51업종_문항별_관측상태.csv", items)


def run(
    prepared: Path,
    current: Path,
    source: Path,
    competition: Path,
    old: Path,
    out: Path,
    *,
    workers=3,
    limit=None,
) -> dict:
    if out.exists():
        raise ValueError("기존 위치 80점 비교 폴더가 이미 있습니다.")
    current_hash = sha256(current)
    prepared_meta = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    if prepared_meta["original_db_sha256"] != current_hash:
        raise ValueError("과거 자료 준비 후 원본 DB가 달라졌습니다.")
    cohort = json.loads((old / "cohort/cohort.json").read_text(encoding="utf-8"))
    original_source = Path(cohort["metadata"]["source"])
    if sha256(original_source) != cohort["metadata"]["source_sha256"]:
        raise ValueError("기존 주소·실제 업종 원본이 달라졌습니다.")
    sites = load_sites(old / "cohort/sites.json")
    previous = json.loads((old / "followup-common-items/results.json").read_text(encoding="utf-8"))
    expected = {c["id"]: c for c in previous["cases"]}
    if {c["id"] for c in sites} != set(expected):
        raise ValueError("이전 80점과 같은 위치 집합이 아닙니다.")
    before = {}
    for site in sites:
        key = site["id"]
        p = old / "scores" / f"{key}.json"
        if sha256(p) != previous["provenance"]["case_sha256"][p.name]:
            raise ValueError("고정된 이전 점수가 달라졌습니다.")
        before[key] = json.loads(p.read_text(encoding="utf-8"))
        if order80(before[key]["scores"]) != expected[key]["orders"]["C"]:
            raise ValueError("이전 80점 환산·동점 순위가 재현되지 않았습니다.")
    out.mkdir(parents=True)
    (out / "scores").mkdir()
    with block_network():
        calibration = build_baselines(prepared / "past.sqlite3", current, source, competition)
        write_json(out / "baselines.json", calibration)
        historical_cohort = out / "historical-address-match"
        historical_meta = build_cohort(
            original_source, prepared / "past.sqlite3", historical_cohort
        )
        history_sites = load_sites(historical_cohort / "sites.json")
    extras = [s for s in history_sites if s["id"] not in expected]
    active_sites = sites + extras
    if limit:
        active_sites = sites[:limit]
    if workers < 1:
        raise ValueError("작업 프로세스 수는 1 이상이어야 합니다.")
    if workers == 1:
        init_worker(str(prepared / "past.sqlite3"), calibration)
    executor = (
        nullcontext(None)
        if workers == 1
        else ProcessPoolExecutor(
            max_workers=workers,
            initializer=init_worker,
            initargs=(str(prepared / "past.sqlite3"), calibration),
        )
    )
    with executor as pool:
        after = {}
        completed = (
            map(score_site, active_sites)
            if pool is None
            else pool.map(score_site, active_sites, chunksize=1)
        )
        for n, saved in enumerate(completed, 1):
            after[saved["id"]] = saved
            write_json(out / "scores" / f"{saved['id']}.json", saved)
            if n % 10 == 0 or n == len(active_sites):
                print(
                    json.dumps(
                        {"stage": "positions_scored", "completed": n, "total": len(active_sites)}
                    ),
                    flush=True,
                )
    paired = []
    for site in sites:
        key = site["id"]
        if key not in after:
            continue
        paired.append(
            {
                "id": key,
                "target": site["target_industry_code"],
                "site": site["site"],
                "cluster": expected[key]["cluster"],
                "orders": {"before_80": expected[key]["orders"]["C"], **after[key]["orders"]},
            }
        )
    metrics = {m: summarize(paired, m) for m in METHODS}
    for m in METHODS:
        metrics[m]["mean_target_rank"] = mean(rank_of(c["orders"][m], c["target"]) for c in paired)
    export_scores(out, paired, before, after)
    with original_source.open(encoding="utf-8-sig", newline="") as f:
        original_rows = list(csv.DictReader(f))
    paired_by_id = {c["id"]: c for c in paired}
    exclusions = {
        v["id"]: v["reason"]
        for v in json.loads((historical_cohort / "cohort.json").read_text(encoding="utf-8"))[
            "exclusions"
        ]
    }
    locations = []
    for row in original_rows:
        key = row["행"]
        c = paired_by_id.get(key)
        record = {
            "사례ID": key,
            "상호": row["상호"],
            "주소": row["주소"],
            "실제업종": row["실제 업종"],
            "구분": "같은좌표비교" if c else "과거추가대조" if key in after else "좌표미확정",
            "제외이유": "" if key in after else exclusions.get(key, "이번 실행 범위 밖"),
        }
        for m in METHODS:
            order = c["orders"][m] if c else after[key]["orders"].get(m) if key in after else None
            target = c["target"] if c else after[key]["target"] if key in after else None
            record[m + "_실제업종순위"] = rank_of(order, target) if order else None
            record[m + "_TOP5"] = "; ".join(INDUSTRIES[code] for code in order[:5]) if order else ""
        locations.append(record)
    csv_file(out / "245곳_위치별_변화.csv", locations)
    result = {
        "kind": "same-location-past-aligned-common80-development-comparison",
        "input_address_n": len(original_rows),
        "paired_n": len(paired),
        "historically_matched_n": historical_meta["matched_n"],
        "historical_extra_n": len(after) - len(paired),
        "all_scored_n": len(after),
        "unresolved_n": len(original_rows) - len(after),
        "settings": {
            "cutoff": "20252",
            "past_lifecycle_quarters": calibration["source_city_quarters"],
            "items": C_ITEMS,
            "weight": 80,
            "score_variants": METHODS,
            "normalization": "80 * 확인 점수 합 / 적용 배점. 미확인 배점은 분모에 유지",
            "tie_break": "이전 C 실험과 같은 서비스 coverage·업종 코드",
            "operating_score_changed": False,
            "smoke_test": bool(limit),
        },
        "metrics": metrics,
        "paired_hit5_difference": {
            "past_minus_before": paired_cluster_interval(paired, "before_80", "past_80"),
            "continuous_minus_step_same_input": paired_cluster_interval(
                paired, "past_80", "past_continuous_80"
            ),
        },
        "cases": paired,
        "limits": [
            "기존 개선용 표본 재실행. 독립 성능 검증·개별 생존 확률 아님",
            "현재 보관된 과거 분기와 현행 지도 사용; 당시 공개 버전 미검증",
            "같은 좌표 비교에는 기존 2026년 건물 좌표를 유지. 과거 지오코딩 확정 아님",
            "이전→과거 점수 차이는 자료 시점과 기준선 일치 효과를 함께 포함",
            "순수 점수식 비교는 같은 과거 입력의 구간안·연속안끼리 해석",
            "시설·규제·공간 조건·LLM을 새로 조회하지 않은 공통80점 검증",
        ],
        "provenance": {
            "original_db_sha256": current_hash,
            "original_db_unchanged": sha256(current) == current_hash,
            "prepared_manifest_sha256": sha256(prepared / "manifest.json"),
            "previous_results_sha256": sha256(old / "followup-common-items/results.json"),
            "original_cohort_sha256": sha256(old / "cohort/sites.json"),
            "case_sha256": {key: sha256(out / "scores" / f"{key}.json") for key in after},
            "code_sha256": {
                name: sha256(Path(__file__).with_name(name))
                for name in ("past80.py", "past_baselines.py", "past_data.py")
            },
            "analysis_api_calls": 0,
            "llm_calls": 0,
        },
    }
    if not result["provenance"]["original_db_unchanged"]:
        raise ValueError("읽기 전용 원본 DB가 달라졌습니다.")
    write_json(out / "results.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="기존 위치의 과거80점을 비교합니다.")
    for name in ("prepared", "current", "source", "competition", "old", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--limit", type=int)
    a = parser.parse_args(argv)
    r = run(
        a.prepared,
        a.current,
        a.source,
        a.competition,
        a.old,
        a.out,
        workers=a.workers,
        limit=a.limit,
    )
    print(
        json.dumps(
            {
                "paired_n": r["paired_n"],
                "historical_extra_n": r["historical_extra_n"],
                "metrics": {
                    k: {x: v[x] for x in ("hit5_n", "hit5", "mean_target_rank")}
                    for k, v in r["metrics"].items()
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

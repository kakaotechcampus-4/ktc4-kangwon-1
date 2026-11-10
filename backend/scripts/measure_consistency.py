"""같은 주소를 같은 입력으로 여러 번 분석해 결과가 얼마나 같은지 잽니다.

실제 모델을 부르면 비용이 듭니다. `--real`과 전체 호출 상한 `--max-calls`가 있어야 돌고,
`--mock`은 대역 모델로 배선만 확인합니다. 결과에는 실제 주소와 모델 문장이 들어가므로
`--out`은 Git이 제외하는 `cache/` 아래를 씁니다.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections import Counter
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.application.analysis import execute_agentic_analysis, mock_run_options  # noqa: E402
from app.application.answers import confirmed_space_values  # noqa: E402
from app.infrastructure.config import load_environment  # noqa: E402


def summarize_run(status, result, budget, seconds):
    calls = (budget or {}).get("calls") or []
    result = result or {}
    reviews = result.get("evaluator_reviews") or []
    top5 = result.get("top5") or []
    return {
        "status": status,
        "seconds": round(seconds, 1),
        "calls": len(calls),
        "calls_by_role": dict(Counter(c.get("role", "decision") for c in calls)),
        "input_tokens": sum(
            c["input_tokens"] if c.get("input_tokens") is not None else c.get("estimated_input", 0)
            for c in calls
        ),
        "output_tokens": sum(c.get("output_tokens") or 0 for c in calls),
        "top5": [c["industry_code"] for c in top5],
        "badges": {c["industry_code"]: c.get("badge") for c in top5},
        "L": {
            r["industry_code"]: r.get("grade") if r.get("status") == "observed" else None
            for r in result.get("L_records") or []
        },
        "evaluators_completed": sum(r.get("status") == "completed" for r in reviews),
        "verdicts": {r.get("actor"): r.get("verdict") for r in reviews},
        "issues": sum(len(r.get("issues") or []) for r in reviews),
        "resolutions": dict(
            Counter(r.get("disposition") for r in result.get("review_resolutions") or [])
        ),
        "review_completeness": result.get("review_completeness"),
    }


def _jaccard(a, b):
    union = set(a) | set(b)
    return len(set(a) & set(b)) / len(union) if union else 1.0


def _spread(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"min": min(values), "max": max(values), "mean": round(sum(values) / len(values), 1)}


def compare_runs(runs):
    done = [r for r in runs if r["status"] == "completed"]
    report = {"total_runs": len(runs), "completed_runs": len(done)}
    if not done:
        return report
    tops = [r["top5"] for r in done]
    pairs = list(combinations(tops, 2))
    codes = sorted({code for r in done for code in r["L"]})
    observed = {
        code: [r["L"][code] for r in done if r["L"].get(code) is not None] for code in codes
    }
    compared = {code: grades for code, grades in observed.items() if len(grades) >= 2}
    diffs = [max(g) - min(g) for g in compared.values()]
    report.update(
        {
            "top5_identical": all(t == tops[0] for t in tops),
            "top5_same_set": all(set(t) == set(tops[0]) for t in tops),
            "top1_same": all(t[:1] == tops[0][:1] for t in tops),
            "top5_jaccard_mean": (
                sum(_jaccard(a, b) for a, b in pairs) / len(pairs) if pairs else 1.0
            ),
            "L_status_agree_share": (
                sum(len({r["L"].get(code) is None for r in done}) == 1 for code in codes)
                / len(codes)
                if codes
                else None
            ),
            "L_observed_per_run": [sum(v is not None for v in r["L"].values()) for r in done],
            "L_max_grade_diff": max(diffs) if diffs else None,
            "L_grade_diff_le1_share": (sum(d <= 1 for d in diffs) / len(diffs) if diffs else None),
            "evaluators_completed": [r["evaluators_completed"] for r in done],
            "calls": _spread([r["calls"] for r in done]),
            "seconds": _spread([r["seconds"] for r in done]),
            "input_tokens": _spread([r["input_tokens"] for r in done]),
            "output_tokens": _spread([r["output_tokens"] for r in done]),
        }
    )
    return report


async def _analyse(site, request_id, db_path, mock):
    space = confirmed_space_values(
        site.get("floor"), site.get("exclusive_area_m2"), site.get("facilities")
    )
    return await execute_agentic_analysis(
        site["address"],
        request_id=request_id,
        db_path=db_path,
        allow_questions=False,
        confirmed_space=space,
        **(mock_run_options(ask=False) if mock else {}),
    )


def _run_once(site, db_path, mock):
    request_id = uuid.uuid4().hex
    started = time.monotonic()
    try:
        outcome = asyncio.run(_analyse(site, request_id, db_path, mock))
    except Exception as exc:
        summary = summarize_run("error", None, None, time.monotonic() - started)
        summary["error"] = type(exc).__name__
        return request_id, summary, None
    model = outcome.result
    result = model.model_dump(mode="json") if model is not None else None
    summary = summarize_run(outcome.status, result, outcome.budget, time.monotonic() - started)
    return request_id, summary, result


def _table(sites):
    lines = [
        "| 주소 | 완료 | Top5 같음 | Top1 같음 | Top5 겹침 | L 상태 일치 "
        "| L 등급 최대 차 | 평가자 완료 | 호출 | 초 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for site in sites:
        c = site["comparison"]
        if not c.get("completed_runs"):
            lines.append(f"| {site['label']} | 0/{c['total_runs']} | | | | | | | | |")
            continue
        lines.append(
            f"| {site['label']} | {c['completed_runs']}/{c['total_runs']} "
            f"| {c['top5_identical']} | {c['top1_same']} | {c['top5_jaccard_mean']:.2f} "
            f"| {c['L_status_agree_share']} | {c['L_max_grade_diff']} "
            f"| {c['evaluators_completed']} | {c['calls']} | {c['seconds']} |"
        )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--max-calls", type=int)
    args = parser.parse_args(argv)
    if args.mock == args.real:
        parser.error("--mock(대역)이나 --real(유료 실행) 중 하나를 고르세요.")
    if args.real and (args.max_calls is None or args.max_calls < 1):
        parser.error("--real에는 1 이상의 --max-calls가 필요합니다.")
    if args.real:
        load_environment()
    sites = json.loads(args.sites.read_text(encoding="utf-8"))
    runs_dir = args.out / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.out / "requests.sqlite3"
    used_calls = 0
    stopped = None
    report = []
    for site in sites:
        summaries = []
        for index in range(1, args.runs + 1):
            if args.real and used_calls >= args.max_calls:
                stopped = f"전체 호출 상한 {args.max_calls}회에 닿아 멈췄습니다."
                break
            request_id, summary, result = _run_once(site, db_path, args.mock)
            used_calls += summary["calls"]
            summaries.append(summary)
            (runs_dir / f"{site['label']}-{index}.json").write_text(
                json.dumps(
                    {"request_id": request_id, "summary": summary, "result": result},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(
                f"{site['label']} {index}/{args.runs}: {summary['status']} "
                f"{summary['seconds']}초 {summary['calls']}회 top5={summary['top5']}",
                flush=True,
            )
        report.append(
            {"label": site["label"], "runs": summaries, "comparison": compare_runs(summaries)}
        )
        if stopped:
            break
    summary = {"mode": "real" if args.real else "mock", "total_calls": used_calls, "sites": report}
    if stopped:
        summary["stopped"] = stopped
        print(stopped, flush=True)
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

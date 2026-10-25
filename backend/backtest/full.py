import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import load_environment
from app.services.analysis import execute_agentic_analysis
from backtest.baselines import swapped
from backtest.catalog import develop_code, invalid_rows, read_sample, row_key
from backtest.history import HistoryDataError, check_history_db
from backtest.measure import load_baselines
from backtest.ranking import rank_rows
from backtest.run import atomic_text, check_resume_inputs, file_sha256, git_commit

MAX_ROWS = 10
RESULT = "전체실행.json"
META = "run_meta.json"
REASSESSED = "전체실행_재집계.json"
MARKER = "미제출 L 판단은 unknown으로 남기고 이미 확인한 판단은 보존했습니다"
UNSUBMITTED = "L 판단 미제출"
BAD_STATUS = {"오류", "무효"}
CONSECUTIVE_BAD = 2

Analyzer = Callable[..., Awaitable[Any]]


def snapshot_rows(db_path: Path, request_id: str, *, reviewed: bool) -> list[dict] | None:
    condition = "L_review_state='reviewed'" if reviewed else "L_review_state!='reviewed'"
    order = "DESC" if reviewed else "ASC"
    with closing(sqlite3.connect(db_path)) as db:
        row = db.execute(
            f"SELECT summary_json FROM score_snapshots WHERE request_id=? AND {condition} "
            f"ORDER BY created_at {order} LIMIT 1",
            (request_id,),
        ).fetchone()
    return None if row is None else json.loads(row[0])


def compare(
    key: str, target: str, code_rows: list[dict], final_rows: list[dict], calls: int
) -> dict[str, Any]:
    code_ranked = rank_rows(code_rows)
    final_ranked = rank_rows(final_rows)

    def rank_of(ranked: list[dict]) -> int:
        return next(r["rank"] for r in ranked if r["code"] == target)

    def top(ranked: list[dict]) -> list[str]:
        return [r["code"] for r in ranked if r["rank"] <= 5]

    target_row = next(r for r in final_ranked if r["code"] == target)
    return {
        "행": key,
        "대상": target,
        "코드 순위": rank_of(code_ranked),
        "최종 순위": rank_of(final_ranked),
        "코드 상위5": top(code_ranked),
        "최종 상위5": top(final_ranked),
        "상위5 겹침": len(set(top(code_ranked)) & set(top(final_ranked))),
        "대상 L": target_row["items"]["L"],
        "호출 수": calls,
    }


def _calls(recording: Path) -> int:
    if not recording.exists():
        return 0
    entries = json.loads(recording.read_text(encoding="utf-8"))
    return len(entries) if isinstance(entries, list) else 0


def _entries(recording: Path) -> list[dict]:
    if not recording.exists():
        return []
    entries = json.loads(recording.read_text(encoding="utf-8"))
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def run_health(db_path: Path, request_id: str, recording: Path) -> dict:
    state: dict[str, Any] = {}
    row = None
    if Path(db_path).exists():
        with closing(sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)) as db:
            try:
                row = db.execute(
                    "SELECT state_json FROM agentic_runs WHERE request_id=?", (request_id,)
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
    if row is not None:
        state = json.loads(row[0])
    limits = state.get("limitations", [])
    reasons: list[str] = []
    for index, text in enumerate(limits):
        if text == MARKER and index and limits[index - 1] not in reasons:
            reasons.append(limits[index - 1])
    records = state.get("L_records", {}).values()
    missing = sum(
        any(str(text).startswith(UNSUBMITTED) for text in record.get("limitations", []))
        for record in records
    )
    errors = Counter(
        e.get("role", "") for e in _entries(recording) if e.get("error") or e.get("error_code")
    )
    return {
        "fallback": bool(reasons),
        "fallback_reasons": reasons,
        "advisor_unavailable": bool(state.get("advisor_unavailable")),
        "l_submitted": len(state.get("L_records", {})) - missing,
        "model_errors": dict(errors),
    }


def assess(status: str, health: dict, calls: int) -> str:
    if status != "완료":
        return status
    errors = sum(health["model_errors"].values())
    if errors * 2 > calls:
        return "무효"
    if health["fallback"] or errors:
        return "대체 마무리"
    return status


def health_fields(health: dict) -> dict[str, Any]:
    return {
        "대체 마무리": health["fallback"],
        "대체 마무리 사유": health["fallback_reasons"],
        "자문 실패": health["advisor_unavailable"],
        "L 제출 업종 수": health["l_submitted"],
        "모델 오류 수": health["model_errors"],
    }


def _bad(result: dict) -> bool:
    return result["상태"] in BAD_STATUS or bool(sum(result.get("모델 오류 수", {}).values()))


async def run_full(
    rows: list[dict],
    *,
    out: Path,
    data_path: Path,
    requests_db: Path,
    analyze: Analyzer = execute_agentic_analysis,
    done: list[dict] | None = None,
    max_calls: int | None = None,
) -> tuple[list[dict], str | None]:
    results = [r for r in (done or []) if r.get("상태") == "완료"]
    finished = {r["행"] for r in results}
    (out / "calls").mkdir(parents=True, exist_ok=True)
    stopped = None
    streak = 0
    processed = 0
    used = 0
    for row in rows:
        key = row_key(row)
        if key in finished:
            continue
        if max_calls is not None and used >= max_calls:
            stopped = "max_calls"
            break
        target = develop_code(row["업종"])
        request_id = f"btf-{key}-{uuid.uuid4().hex[:8]}"
        recording = out / "calls" / f"{key}.json"
        try:
            outcome = await analyze(
                row["주소"],
                db_path=requests_db,
                local_data_path=data_path,
                request_id=request_id,
                recording_path=recording,
                allow_questions=False,
            )
            code_rows = snapshot_rows(requests_db, request_id, reviewed=False)
            final_rows = snapshot_rows(requests_db, request_id, reviewed=True)
            if code_rows is None or final_rows is None:
                result = {
                    "행": key,
                    "상태": "점수 없음",
                    "결과 상태": outcome.status,
                    "호출 수": _calls(recording),
                }
            else:
                result = {
                    **compare(key, target, code_rows, final_rows, _calls(recording)),
                    "상태": "완료",
                    "결과 상태": outcome.status,
                    "요청 ID": request_id,
                }
        except Exception as error:
            message = f"{type(error).__name__}: {str(error)[:200]}"
            result = {"행": key, "상태": "오류", "오류": message, "호출 수": _calls(recording)}
        health = run_health(requests_db, request_id, recording)
        result = {**result, **health_fields(health)}
        result["상태"] = assess(result["상태"], health, result["호출 수"])
        results.append(result)
        processed += 1
        used += result["호출 수"]
        atomic_text(out / RESULT, json.dumps(results, ensure_ascii=False, indent=1, default=str))
        line = {k: result.get(k) for k in ("행", "상태", "코드 순위", "최종 순위", "호출 수")}
        print(json.dumps(line, ensure_ascii=False), flush=True)
        streak = streak + 1 if _bad(result) else 0
        if processed == 1 and sum(result["모델 오류 수"].values()):
            stopped = "first_row_model_error"
            break
        if streak >= CONSECUTIVE_BAD:
            stopped = "consecutive_errors"
            break
    return results, stopped


def reassess(out: Path, requests_db: Path) -> int:
    target = out / REASSESSED
    if target.exists():
        print(f"이미 있습니다: {target}", file=sys.stderr)
        return 1
    original = json.loads((out / RESULT).read_text(encoding="utf-8"))
    rows = []
    for old in original:
        recording = out / "calls" / f"{old['행']}.json"
        calls = _calls(recording)
        health = run_health(requests_db, old.get("요청 ID", ""), recording)
        row = {**old, **health_fields(health), "호출 수": calls}
        row["상태"] = assess(old["상태"], health, calls)
        rows.append(row)
        line = {k: row.get(k) for k in ("행", "상태", "코드 순위", "최종 순위", "호출 수")}
        print(json.dumps(line, ensure_ascii=False), flush=True)
    done = [r for r in rows if r["상태"] == "완료"]
    summary = {
        "상태": dict(Counter(r["상태"] for r in rows)),
        "호출 수": sum(r["호출 수"] for r in rows),
        "완료 중 코드 순위 = 최종 순위": sum(r["코드 순위"] == r["최종 순위"] for r in done),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    atomic_text(
        target, json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=1)
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="AI 포함 서비스 전체를 과거 시점으로 돌립니다(유료)."
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--baselines", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rows")
    parser.add_argument("--requests", type=Path)
    parser.add_argument("--quarter", default="20234")
    parser.add_argument("--max-rows", type=int, default=MAX_ROWS)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--reassess", action="store_true")
    args = parser.parse_args(argv)
    if args.reassess:
        if not args.requests:
            parser.error("--reassess에는 --requests가 필요합니다.")
        if not (args.out / RESULT).exists():
            parser.error("재집계할 결과 폴더가 아닙니다.")
        return reassess(args.out, args.requests)
    for name in ("input", "data", "baselines", "rows"):
        if getattr(args, name) is None:
            parser.error(f"--{name}이 필요합니다.")
    if not args.real:
        parser.error("유료 실행입니다. --real을 붙여야 합니다.")
    if args.max_calls is None or args.max_calls < 1:
        parser.error("--real에는 1 이상의 --max-calls가 필요합니다.")
    picks = args.rows.split(",")
    if len(picks) > args.max_rows:
        parser.error(f"한 번에 {args.max_rows}곳까지만 돌립니다.")
    if args.resume and not (args.out / RESULT).exists():
        parser.error("이어 돌릴 결과 폴더가 아닙니다.")
    if not args.resume and args.out.exists():
        parser.error("결과 폴더가 이미 있습니다.")
    rows = read_sample(args.input, set(picks))
    problems = invalid_rows(rows)
    if len(rows) != len(picks) or problems:
        print("\n".join(problems) or "없는 행 키가 있습니다.", file=sys.stderr)
        return 2
    load_environment()
    if not os.getenv("ELICE_API_KEY"):
        print("모델 키(ELICE_API_KEY)가 비어 있습니다.", file=sys.stderr)
        return 1
    try:
        data_info = check_history_db(args.data, args.quarter)
    except HistoryDataError as error:
        print(f"자료 DB 점검 실패: {error}", file=sys.stderr)
        return 1
    values = load_baselines(args.baselines)
    if values["quarter"] != args.quarter:
        print(f"기준선 분기 {values['quarter']}가 {args.quarter}와 다릅니다.", file=sys.stderr)
        return 1
    requests_db = (
        args.requests
        or Path.home() / ".chaeum" / "backtest_runs" / args.out.name / "requests.sqlite3"
    )
    if not args.resume and requests_db.exists():
        print(f"요청 DB가 이미 있습니다: {requests_db}", file=sys.stderr)
        return 1
    if args.resume:
        refusal = check_resume_inputs(args.out, args.baselines, data_info)
        if refusal:
            print(refusal, file=sys.stderr)
            return 1
    args.out.mkdir(parents=True, exist_ok=args.resume)
    requests_db.parent.mkdir(parents=True, exist_ok=True)
    if not (args.out / "baseline.json").exists():
        shutil.copy2(args.baselines, args.out / "baseline.json")
    done = json.loads((args.out / RESULT).read_text(encoding="utf-8")) if args.resume else None
    started = datetime.now().isoformat(timespec="seconds")
    ordered = sorted(rows, key=lambda r: picks.index(row_key(r)))
    with swapped(values):
        results, stopped = asyncio.run(
            run_full(
                ordered,
                out=args.out,
                data_path=args.data,
                requests_db=requests_db,
                done=done,
                max_calls=args.max_calls,
            )
        )
    runs = (
        json.loads((args.out / META).read_text(encoding="utf-8"))["runs"]
        if (args.out / META).exists()
        else []
    )
    runs.append(
        {
            "command": sys.argv,
            "commit": git_commit(),
            "data": data_info,
            "baselines": {"path": str(args.baselines), "sha256": file_sha256(args.baselines)},
            "requests_db": str(requests_db),
            "started": started,
            "finished": datetime.now().isoformat(timespec="seconds"),
            "stopped": stopped,
            "calls": sum(r.get("호출 수", 0) for r in results),
            "status": {
                s: sum(r["상태"] == s for r in results) for s in {r["상태"] for r in results}
            },
        }
    )
    atomic_text(args.out / META, json.dumps({"runs": runs}, ensure_ascii=False, indent=1))
    return 0 if stopped in (None, "max_calls") else 1


if __name__ == "__main__":
    raise SystemExit(main())

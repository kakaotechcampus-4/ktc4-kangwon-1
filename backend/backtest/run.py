import argparse
import asyncio
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from app.address import GeocodeError
from app.config import load_environment
from backtest.baselines import swapped
from backtest.catalog import develop_code, invalid_rows, read_sample, row_key
from backtest.history import HistoryDataError, check_history_db
from backtest.measure import load_baselines
from backtest.metrics import summarize
from backtest.ranking import ITEMS, rank_rows, score_rows, target_summary
from backtest.score import score_address

SUMMARY = "요약.csv"
SCORES = "업종별점수.csv"
RECORDS = "records.json"
STATE = "state.json"
META = "run_meta.json"
METRICS = "지표.json"
REPEATED_ERRORS = 3
BAD_ADDRESS = {
    "NOT_FOUND",
    "EMPTY_ADDRESS",
    "ADDRESS_AMBIGUOUS",
    "ADDRESS_MISMATCH",
    "ADDRESS_TOO_LONG",
}
SUMMARY_FIELDS = [
    "행",
    "그룹",
    "상호",
    "주소",
    "업종",
    "업종 코드",
    "상태",
    "오류",
    "순위",
    "업종 수",
    "상위5 업종 수",
    "하한",
    "coverage",
    "배지",
    "규제",
    "주소 평균 하한",
    "평균 대비",
    "점포 수",
    "점포 수 순위",
    "D 차이",
    "C 차이",
    "S 차이",
    "서울 자료 없음",
    "현재 시점 C4",
    "현재 시점 G",
    "상권 선택",
    "요청 ID",
]
SCORE_FIELDS = [
    "행",
    "업종 코드",
    "업종",
    "순위",
    "하한",
    "상한",
    "coverage",
    "배지",
    "규제",
    *ITEMS,
]

Scorer = Callable[..., Awaitable[tuple[Any, dict[str, Any], dict[str, Any]]]]


def atomic_text(path: Path, text: str) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _atomic_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_resume_inputs(out: Path, baselines: Path, data_info: dict) -> str | None:
    meta = out / META
    runs = json.loads(meta.read_text(encoding="utf-8")).get("runs", []) if meta.exists() else []
    kept = out / "baseline.json"
    if kept.exists():
        before = file_sha256(kept)
    elif runs:
        before = runs[0]["baselines"]["sha256"]
    else:
        before = None
    if before is not None and before != file_sha256(baselines):
        return "기준선 파일이 처음 실행 때와 다릅니다. 이어 돌릴 수 없습니다."
    if runs:
        first = [(v["version_id"], v["file_hash"]) for v in runs[0]["data"]["versions"]]
        now = [(v["version_id"], v["file_hash"]) for v in data_info["versions"]]
        if first != now:
            return "자료 DB 버전이 처음 실행 때와 다릅니다. 이어 돌릴 수 없습니다."
    return None


def git_commit() -> str:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )
    except (OSError, subprocess.CalledProcessError):
        return "알 수 없음"
    return done.stdout.strip()


def write_outputs(out: Path, state: dict[str, list[dict]]) -> None:
    _atomic_csv(out / SUMMARY, SUMMARY_FIELDS, state["summaries"])
    _atomic_csv(out / SCORES, SCORE_FIELDS, state["scores"])
    atomic_text(
        out / RECORDS, json.dumps(state["records"], ensure_ascii=False, indent=1, default=str)
    )
    atomic_text(out / STATE, json.dumps(state, ensure_ascii=False, default=str))


def base_summary(row: dict) -> dict[str, Any]:
    return {
        "행": row_key(row),
        "그룹": row["그룹"],
        "상호": row["상호"],
        "주소": row["주소"],
        "업종": row["업종"],
        "업종 코드": develop_code(row["업종"]),
    }


async def score_row(
    row: dict, *, data_path: Path, requests_db: Path, score: Scorer
) -> tuple[dict[str, Any], list[dict], dict[str, Any]]:
    base = base_summary(row)
    key = base["행"]
    request_id = f"bt-{key}-{uuid.uuid4().hex[:8]}"
    try:
        site, data, report = await score(
            row["주소"], local_data_path=data_path, db_path=requests_db, request_id=request_id
        )
    except GeocodeError as error:
        status = "주소 변환 실패" if error.code in BAD_ADDRESS else "오류"
        summary = {**base, "상태": status, "오류": error.code, "요청 ID": request_id}
        return summary, [], {"행": key, "상태": status, "오류": error.code}
    ranked = rank_rows(report["rows"])
    by_middle = data.get("commercial_area", {}).get("by_middle", [])
    counts = {item["code"]: item["count"] for item in by_middle}
    selection = data.get("area_selection", {})
    status = "상권 밖" if selection.get("method") == "미선택" else "완료"
    summary = {
        **base,
        **target_summary(ranked, base["업종 코드"], counts),
        "상태": status,
        "상권 선택": selection.get("method"),
        "요청 ID": request_id,
    }
    target = next(r for r in ranked if r["code"] == base["업종 코드"])
    keep = ("code", "name", "rank", "lower", "upper", "coverage", "badge", "regulation", "items")
    record = {
        "행": key,
        "상태": status,
        "site": site.model_dump(mode="json"),
        "area_selection": selection,
        "limitations": data.get("limitations", []),
        "대상": {name: target[name] for name in keep},
    }
    return summary, score_rows(key, ranked), record


def _without_errors(state: dict[str, list[dict]]) -> dict[str, list[dict]]:
    kept = {s["행"] for s in state["summaries"] if s.get("상태") != "오류"}
    return {
        "summaries": [s for s in state["summaries"] if s["행"] in kept],
        "scores": [s for s in state["scores"] if s["행"] in kept],
        "records": [r for r in state["records"] if r["행"] in kept],
    }


async def run_rows(
    rows: list[dict],
    *,
    out: Path,
    data_path: Path,
    requests_db: Path,
    score: Scorer = score_address,
    state: dict[str, list[dict]] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    current = _without_errors(state) if state else {"summaries": [], "scores": [], "records": []}
    finished = {s["행"] for s in current["summaries"]}
    streak: list[str] = []
    stopped = None
    processed = 0
    for row in rows:
        if row_key(row) in finished:
            continue
        if limit is not None and processed >= limit:
            stopped = "limit"
            break
        processed += 1
        try:
            summary, scores, record = await score_row(
                row, data_path=data_path, requests_db=requests_db, score=score
            )
        except Exception as error:
            message = f"{type(error).__name__}: {str(error)[:200]}"
            summary = {**base_summary(row), "상태": "오류", "오류": message}
            scores, record = [], {"행": row_key(row), "상태": "오류", "오류": message}
        current["summaries"].append(summary)
        current["scores"].extend(scores)
        current["records"].append(record)
        try:
            write_outputs(out, current)
        except OSError as error:
            print(f"결과 저장 실패, 다음 주소에서 다시 저장합니다: {error}", file=sys.stderr)
        line = {"행": summary["행"], "상태": summary["상태"], "순위": summary.get("순위")}
        print(json.dumps(line, ensure_ascii=False), flush=True)
        streak = [*streak, summary["오류"]][-REPEATED_ERRORS:] if summary["상태"] == "오류" else []
        if len(streak) == REPEATED_ERRORS and len(set(streak)) == 1:
            stopped = "repeated_error"
            break
    write_outputs(out, current)
    return {
        "rows": len(current["summaries"]),
        "processed": processed,
        "status": dict(Counter(s["상태"] for s in current["summaries"])),
        "stopped": stopped,
    }


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="과거 시점 51업종 코드 채점 백테스트")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--baselines", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--requests", type=Path)
    parser.add_argument("--quarter", default="20234")
    parser.add_argument("--rows")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.resume and not (args.out / STATE).exists():
        parser.error("이어 돌릴 결과 폴더가 아닙니다.")
    if not args.resume and args.out.exists():
        parser.error("결과 폴더가 이미 있습니다. 새 폴더를 쓰거나 --resume을 붙이세요.")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    picks = set(args.rows.split(",")) if args.rows else None
    rows = read_sample(args.input, picks)
    if picks is not None and len(rows) != len(picks):
        print(f"없는 행 키: {sorted(picks - {row_key(r) for r in rows})}", file=sys.stderr)
        return 2
    problems = invalid_rows(rows)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 2
    load_environment()
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
    state = json.loads((args.out / STATE).read_text(encoding="utf-8")) if args.resume else None
    started = datetime.now().isoformat(timespec="seconds")
    with swapped(values):
        result = asyncio.run(
            run_rows(
                rows,
                out=args.out,
                data_path=args.data,
                requests_db=requests_db,
                state=state,
                limit=args.limit,
            )
        )
    final = json.loads((args.out / STATE).read_text(encoding="utf-8"))
    metrics = summarize(final["summaries"])
    atomic_text(args.out / METRICS, json.dumps(metrics, ensure_ascii=False, indent=1))
    runs = (
        json.loads((args.out / META).read_text(encoding="utf-8"))["runs"]
        if (args.out / META).exists()
        else []
    )
    runs.append(
        {
            "command": sys.argv,
            "commit": git_commit(),
            "quarter": args.quarter,
            "data": data_info,
            "baselines": {"path": str(args.baselines), "sha256": file_sha256(args.baselines)},
            "requests_db": str(requests_db),
            "input": str(args.input),
            "started": started,
            "finished": datetime.now().isoformat(timespec="seconds"),
            **result,
        }
    )
    atomic_text(args.out / META, json.dumps({"runs": runs}, ensure_ascii=False, indent=1))
    print(json.dumps(metrics, ensure_ascii=False))
    return 0 if result["stopped"] in (None, "limit") else 1


if __name__ == "__main__":
    raise SystemExit(main())

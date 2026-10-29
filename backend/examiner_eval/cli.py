"""심사위원 시험의 복사본 만들기와 실행 명령을 처리합니다."""

import argparse
import asyncio
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from app.config import load_environment
from app.llm.config import LLMSettings
from examiner_eval.cases import dump_cases, load_cases
from examiner_eval.generator import build_cases
from examiner_eval.runner import (
    CALLS_PER_CASE,
    FAKE_MODEL,
    RESULTS,
    append_row,
    fake_generate,
    read_results,
    run_pending,
)
from examiner_eval.score import REPORT_FILES, rejection_reasons, score_case, write_report
from examiner_eval.store import candidate_facts, copy_store, fact_sources, load_contexts
from examiner_eval.variants import VARIANTS

CASES = "cases.json"
SPLITS = ("tune", "test", "all")
HEADER_KEYS = ("variant", "split", "mode", "model", "code")
PROTECTED = Path.home() / ".chaeum"
MARK = ".examiner_eval"
BACKEND = Path(__file__).resolve().parents[1]


def marker(db: Path) -> Path:
    return Path(str(db) + MARK)


def code_version() -> str:
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=BACKEND, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        head = git("rev-parse", "--short", "HEAD")
        dirty = git("status", "--porcelain", "--", "app", "examiner_eval")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return head + ("+수정중" if dirty else "")


def _refuse(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _protected(path: Path) -> bool:
    return Path(path).resolve().is_relative_to(PROTECTED.resolve())


def _header_differs(header: dict, current: dict) -> int:
    keys = [k for k in HEADER_KEYS if k in current and header.get(k) != current[k]]
    if not keys:
        return 0
    return _refuse(
        "기존 결과와 머리 행이 다릅니다: "
        + ", ".join(f"{k}={header.get(k)}→{current[k]}" for k in keys)
    )


def _run_parser():
    parser = argparse.ArgumentParser(prog="python -m examiner_eval")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--split", choices=SPLITS, default="tune")
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fake", action="store_true")
    mode.add_argument("--real", action="store_true")
    parser.add_argument("--max-calls", type=int)
    return parser


def _build_parser():
    parser = argparse.ArgumentParser(prog="python -m examiner_eval build")
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def _report_parser():
    parser = argparse.ArgumentParser(prog="python -m examiner_eval report")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def build(args) -> int:
    target = args.out / CASES
    if not args.src.exists():
        return _refuse(f"원본 DB가 없습니다: {args.src}")
    if args.db.resolve() == args.src.resolve():
        return _refuse("복사본 경로가 원본 DB와 같습니다.")
    if args.db.exists():
        return _refuse(f"복사본 경로에 이미 파일이 있습니다: {args.db}")
    if _protected(args.db):
        return _refuse(f"복사본은 {PROTECTED} 밖에 두어야 합니다.")
    if target.exists():
        return _refuse(f"이미 사례 파일이 있습니다: {target}")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    copy_store(args.src, args.db)
    try:
        cases = build_cases(load_contexts(args.db))
        dump_cases(cases, target)
        marker(args.db).write_text(
            json.dumps({"src": str(args.src), "cases": str(target)}, ensure_ascii=False),
            encoding="utf-8",
        )
    except BaseException:
        args.db.unlink(missing_ok=True)
        marker(args.db).unlink(missing_ok=True)
        raise
    sources = Counter(c.source for c in cases)
    splits = Counter(c.split for c in cases)
    addresses = Counter(split for _, split in {(c.request_id, c.split) for c in cases})
    print(f"복사본: {args.db}")
    print(f"사례 파일: {target}")
    print(
        f"사례 {len(cases)}개: clean {sources['clean']}, seeded {sources['seeded']}, "
        f"real {sources['real']}, 심은 오류 {sum(len(c.seeds) for c in cases)}개"
    )
    print(
        f"주소 tune {addresses['tune']}곳, test {addresses['test']}곳 / "
        f"사례 tune {splits['tune']}개, test {splits['test']}개"
    )
    return 0


def run(args) -> int:
    if args.real and args.max_calls is None:
        return _refuse("--real에는 --max-calls가 필요합니다.")
    if args.repeats < 1:
        return _refuse("--repeats는 1 이상이어야 합니다.")
    if not args.db.exists():
        return _refuse(f"복사본 DB가 없습니다: {args.db}")
    if _protected(args.db):
        return _refuse(f"{PROTECTED} 안의 DB에는 실행하지 않습니다. build로 만든 복사본을 쓰세요.")
    if not marker(args.db).exists():
        return _refuse(
            f"build로 만든 복사본이 아닙니다(표식 {marker(args.db).name} 없음): {args.db}"
        )
    if not args.cases.exists():
        return _refuse(f"사례 파일이 없습니다: {args.cases}")
    cases = [c for c in load_cases(args.cases) if args.split in ("all", c.split)]
    path = args.out / RESULTS
    try:
        header, done = read_results(path)
    except ValueError as exc:
        return _refuse(str(exc))
    finished = {(r.case_id, r.variant, r.repeat) for r in done}
    pending = [
        (case, repeat)
        for repeat in range(1, args.repeats + 1)
        for case in cases
        if (case.case_id, args.variant, repeat) not in finished
    ]
    expected = len(pending) * CALLS_PER_CASE
    if args.max_calls is not None and expected > args.max_calls:
        return _refuse(
            f"예상 호출 {expected}회(사례·회차 {len(pending)}개 × {CALLS_PER_CASE})가 "
            f"상한 {args.max_calls}회보다 많아 시작하지 않습니다."
        )
    current = {
        "type": "header",
        "variant": args.variant,
        "split": args.split,
        "mode": "real" if args.real else "fake",
        "code": code_version(),
    }
    if header is not None and (refused := _header_differs(header, current)):
        return refused
    contexts = {ctx.request_id: ctx for ctx in load_contexts(args.db)}
    missing = sorted({case.request_id for case, _ in pending} - set(contexts))
    if missing:
        return _refuse("복사본 DB에 없는 요청입니다: " + ", ".join(missing))
    if not pending:
        print("남은 사례가 없습니다.")
        return 0
    generate: Callable | None = fake_generate
    model: str | None = FAKE_MODEL
    if args.real:
        load_environment()
        settings = LLMSettings.from_env("evaluator")
        try:
            settings.require_credentials()
        except ValueError as exc:
            return _refuse(str(exc))
        generate, model = None, settings.model
    current |= {"model": model, "first_repeats": args.repeats, "first_max_calls": args.max_calls}
    if header is not None and (refused := _header_differs(header, current)):
        return refused
    print(f"평가자 모델: {model}, 사례·회차 {len(pending)}개, 예상 호출 최대 {expected}회")
    args.out.mkdir(parents=True, exist_ok=True)
    if header is None:
        append_row(path, current)
    results, total, stopped = asyncio.run(
        run_pending(
            pending,
            contexts,
            args.db,
            args.out,
            variant=args.variant,
            generate=generate,
            model=model,
            max_calls=args.max_calls,
        )
    )
    statuses = Counter(r.status for r in results)
    print(f"완료 {statuses['completed']}, 실패 {statuses['failed']}, 호출 {total}회 → {path}")
    if stopped:
        print(
            f"호출 상한 {args.max_calls}회에 닿아 멈췄습니다. 남은 사례·회차 "
            f"{len(pending) - len(results)}개",
            file=sys.stderr,
        )
        return 3
    return 0


def report(args) -> int:
    existing = [name for name in REPORT_FILES if (args.out / name).exists()]
    if existing:
        return _refuse("이미 보고 파일이 있습니다: " + ", ".join(existing))
    if not args.db.exists():
        return _refuse(f"복사본 DB가 없습니다: {args.db}")
    if not args.cases.exists():
        return _refuse(f"사례 파일이 없습니다: {args.cases}")
    cases = {c.case_id: c for c in load_cases(args.cases)}
    per_run = []
    for run_dir in args.runs:
        path = run_dir / RESULTS
        if not path.exists():
            return _refuse(f"결과 파일이 없습니다: {path}")
        try:
            _, rows = read_results(path)
        except ValueError as exc:
            return _refuse(str(exc))
        unknown = sorted({r.case_id for r in rows} - set(cases))
        if unknown:
            return _refuse("사례 파일에 없는 case_id입니다: " + ", ".join(unknown))
        per_run.append((run_dir, rows))
    results = [r for _, rows in per_run for r in rows]
    keys = Counter((r.case_id, r.variant, r.repeat) for r in results)
    duplicated = sorted(k for k, n in keys.items() if n > 1)
    if duplicated:
        return _refuse("같은 사례·버전·회차가 여러 번 있습니다: " + ", ".join(map(str, duplicated)))
    loaded = load_contexts(args.db)
    contexts = {ctx.request_id: ctx for ctx in loaded}
    missing = sorted({cases[r.case_id].request_id for r in results} - set(contexts))
    if missing:
        return _refuse("복사본 DB에 없는 요청입니다: " + ", ".join(missing))
    facts = candidate_facts(args.db, loaded)
    sources = fact_sources(args.db, loaded)
    scores = [
        score_case(
            cases[r.case_id],
            r,
            facts[cases[r.case_id].request_id],
            sources[cases[r.case_id].request_id],
        )
        for r in results
    ]
    splits = {case_id: case.split for case_id, case in cases.items()}
    rejections: dict = {}
    for run_dir, rows in per_run:
        for key, counter in rejection_reasons(run_dir, rows, splits).items():
            if counter is None:
                rejections.setdefault(key, None)
            else:
                rejections[key] = rejections.get(key) or Counter()
                rejections[key].update(counter)
    write_report(results, scores, args.out, rejections=rejections)
    print(f"보고서: {args.out} (결과 {len(results)}건)")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["build"]:
        return build(_build_parser().parse_args(argv[1:]))
    if argv[:1] == ["report"]:
        return report(_report_parser().parse_args(argv[1:]))
    return run(_run_parser().parse_args(argv))

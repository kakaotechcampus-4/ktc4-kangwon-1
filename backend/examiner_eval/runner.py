"""준비된 사례에 심사위원 평가자만 돌리고 결과를 한 줄씩 남깁니다."""

import argparse
import asyncio
import copy
import json
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from time import monotonic
from typing import Literal
from unittest.mock import patch

from openai.types.chat import ChatCompletionMessage

from app.agentic import evaluators
from app.agentic.recording import CallRecording
from app.agentic.runtime import DecisionLoop
from app.config import load_environment
from app.llm.config import LLMSettings
from examiner_eval.cases import Case, dump_cases, load_cases
from examiner_eval.generator import build_cases
from examiner_eval.store import RequestContext, copy_store, load_contexts, make_scope
from examiner_eval.variants import VARIANTS, use_variant

CALLS_PER_CASE = 6
FAKE_MODEL = "fake"
RESULTS = "results.jsonl"
CASES = "cases.json"
SPLITS = ("tune", "test", "all")
END_KEYS = ("issues_count", "reads", "rejections", "model_calls")
HEADER_KEYS = ("variant", "model", "split")
PROTECTED = Path.home() / ".chaeum"


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    variant: str
    repeat: int
    status: Literal["completed", "failed"]
    error_code: str | None
    verdict: str | None
    issues: list[dict]
    end_event: dict
    calls: int
    input_tokens: int
    output_tokens: int
    elapsed_ms: int
    model: str | None
    packet_chars: int
    omitted_fact_ids: int


class CaseDraft:
    def __init__(self, payload: dict):
        self.report_id = payload["report_id"]
        self._payload = payload

    def model_dump(self, mode: str = "python") -> dict:
        return copy.deepcopy(self._payload)


def fake_generate(messages, definitions, settings, receipt):
    packet = json.loads(messages[1]["content"])
    candidates = packet.get("candidates") or packet.get("top5") or []
    first = candidates[0] if candidates else {}
    aliases = first.get("fact_ids") or []
    issues = []
    if aliases:
        issues.append(
            {
                "issue_id": "fake",
                "industry_code": first["industry_code"],
                "target": "claim",
                "kind": "missing_evidence",
                "comment": "문장을 뒷받침하는 근거 슬롯을 확인해야 합니다.",
                "fact_ids": [aliases[0]],
                "suggested_check": "후보 문장에 근거가 붙어 있는지 확인하세요.",
            }
        )
    receipt["model"] = FAKE_MODEL
    arguments = {
        "draft_id": packet["draft_id"],
        "verdict": "conditional" if issues else "agree",
        "issues": issues,
    }
    return ChatCompletionMessage(
        role="assistant",
        tool_calls=[
            {
                "id": "fake_submit",
                "type": "function",
                "function": {
                    "name": "submit_review",
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        ],
    )


def _skip_save(scope, review):
    return None


def _watch(loop, seen, events):
    model_call, event = loop.model_call, loop.event

    async def watched_call(role, messages, settings, definitions=None, receipt=None):
        if role == "examiner":
            seen.setdefault("packet", messages[1]["content"])
        return await model_call(role, messages, settings, definitions, receipt)

    async def watched_event(stage, name, detail):
        events.append((stage, detail))
        await event(stage, name, detail)

    loop.model_call, loop.event = watched_call, watched_event


def _omitted(content):
    try:
        packet = json.loads(content)
    except ValueError:
        return 0
    return len(packet.get("omitted_fact_ids", [])) if isinstance(packet, dict) else 0


async def run_case(
    case: Case,
    variant: str,
    ctx: RequestContext,
    db_path: Path,
    *,
    repeat: int,
    generate=None,
    recorder_path: Path | None = None,
) -> CaseResult:
    started = monotonic()
    seen: dict[str, str] = {}
    events: list[tuple[str, dict]] = []
    loop = None
    review = None
    failure = None
    with use_variant(variant), patch.object(evaluators, "save_review", _skip_save):
        try:
            loop = await DecisionLoop.create(
                make_scope(ctx, db_path),
                ctx.site,
                evaluator_generate=generate,
                recorder=CallRecording(recorder_path) if recorder_path else None,
                measurement=False,
            )
            _watch(loop, seen, events)
            review = await evaluators.review(
                loop, "examiner", loop.evaluator_executors()["examiner"], CaseDraft(case.draft)
            )
        except Exception as exc:
            failure = type(exc).__name__
    rows = [c for c in loop.budget.calls if c.get("role") == "examiner"] if loop else []
    end = next(
        (d for stage, d in reversed(events) if stage == "evaluation" and "model_calls" in d), {}
    )
    packet = seen.get("packet", "")
    return CaseResult(
        case_id=case.case_id,
        variant=variant,
        repeat=repeat,
        status=review.status if review else "failed",
        error_code=review.error_code if review else failure,
        verdict=review.verdict if review else None,
        issues=[i.model_dump(mode="json") for i in review.issues] if review else [],
        end_event={key: end[key] for key in END_KEYS if key in end},
        calls=len(rows),
        input_tokens=sum(r.get("input_tokens") or 0 for r in rows),
        output_tokens=sum(r.get("output_tokens") or 0 for r in rows),
        elapsed_ms=int((monotonic() - started) * 1000),
        model=next((r["model"] for r in rows if r.get("model")), None),
        packet_chars=len(packet),
        omitted_fact_ids=_omitted(packet),
    )


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()


def read_results(path: Path) -> tuple[dict | None, list[CaseResult]]:
    header = None
    results: list[CaseResult] = []
    if not path.exists():
        return header, results
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
            if number == 1:
                if row.get("type") != "header":
                    raise ValueError("첫 줄이 머리 행이 아닙니다")
                header = row
            elif row.get("type") == "result":
                results.append(CaseResult(**{k: v for k, v in row.items() if k != "type"}))
            else:
                raise ValueError("알 수 없는 행입니다")
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"{path.name} {number}번째 줄을 읽지 못했습니다: {exc}") from exc
    return header, results


def _recording_name(case_id: str, variant: str, repeat: int) -> str:
    return f"{re.sub(r'[^0-9A-Za-z_-]', '_', case_id)}__{variant}__{repeat}.json"


async def run_pending(
    pending: list[tuple[Case, int]],
    contexts: dict[str, RequestContext],
    db_path: Path,
    out_dir: Path,
    *,
    variant: str,
    generate,
    model: str | None,
    max_calls: int | None = None,
) -> tuple[list[CaseResult], int, bool]:
    results: list[CaseResult] = []
    total = 0
    for case, repeat in pending:
        if max_calls is not None and total >= max_calls:
            return results, total, True
        recording = out_dir / "calls" / _recording_name(case.case_id, variant, repeat)
        recording.unlink(missing_ok=True)
        outcome = await run_case(
            case,
            variant,
            contexts[case.request_id],
            db_path,
            repeat=repeat,
            generate=generate,
            recorder_path=recording,
        )
        if outcome.model is None:
            outcome = replace(outcome, model=model)
        _append(out_dir / RESULTS, {"type": "result", **asdict(outcome)})
        total += outcome.calls
        results.append(outcome)
        print(
            f"{outcome.case_id} {variant} {repeat}회차: {outcome.status}"
            f" {outcome.error_code or ''} 호출 {outcome.calls}",
            flush=True,
        )
    return results, total, False


def _refuse(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _protected(path: Path) -> bool:
    return Path(path).resolve().is_relative_to(PROTECTED.resolve())


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
    except BaseException:
        args.db.unlink(missing_ok=True)
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
    current = {
        "type": "header",
        "variant": args.variant,
        "split": args.split,
        "repeats": args.repeats,
        "model": model,
        "mode": "real" if args.real else "fake",
        "max_calls": args.max_calls,
    }
    if header is not None and any(header.get(k) != current[k] for k in HEADER_KEYS):
        return _refuse(
            "기존 결과와 버전·모델·분할이 다릅니다: "
            + ", ".join(f"{k}={header.get(k)}" for k in HEADER_KEYS)
        )
    contexts = {ctx.request_id: ctx for ctx in load_contexts(args.db)}
    missing = sorted({case.request_id for case, _ in pending} - set(contexts))
    if missing:
        return _refuse("복사본 DB에 없는 요청입니다: " + ", ".join(missing))
    if not pending:
        print("남은 사례가 없습니다.")
        return 0
    print(f"평가자 모델: {model}, 사례·회차 {len(pending)}개, 예상 호출 최대 {expected}회")
    args.out.mkdir(parents=True, exist_ok=True)
    if header is None:
        _append(path, current)
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["build"]:
        return build(_build_parser().parse_args(argv[1:]))
    return run(_run_parser().parse_args(argv))

"""준비된 사례에 심사위원 평가자만 돌리고 결과를 한 줄씩 남깁니다."""

import copy
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Literal
from unittest.mock import patch

from openai.types.chat import ChatCompletionMessage

from app.agentic import evaluators
from app.agentic.recording import CallRecording
from app.agentic.runtime import DecisionLoop
from app.llm.budget import BudgetExceeded
from examiner_eval.cases import Case
from examiner_eval.store import RequestContext, make_scope
from examiner_eval.variants import use_variant

CALLS_PER_CASE = 6
FAKE_MODEL = "fake"
RESULTS = "results.jsonl"
END_KEYS = ("issues_count", "reads", "rejections", "model_calls")


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
    calls = 0

    async def watched_call(role, messages, settings, definitions=None, receipt=None):
        nonlocal calls
        if role == "examiner":
            if calls >= CALLS_PER_CASE:
                raise BudgetExceeded()
            calls += 1
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


def append_row(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()


def read_results(path: Path) -> tuple[dict | None, list[CaseResult]]:
    header = None
    results: list[CaseResult] = []
    if not path.exists():
        return header, results
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except ValueError as exc:
            if number == len(lines):
                raise ValueError(
                    f"{path.name} {number}번째 줄: 마지막 줄이 끊겼습니다. "
                    "그 줄을 지우고 다시 실행하세요."
                ) from exc
            raise ValueError(f"{path.name} {number}번째 줄을 읽지 못했습니다: {exc}") from exc
        try:
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


def _fresh_recording(out_dir: Path, case_id: str, variant: str, repeat: int) -> Path:
    name = re.sub(r"[^0-9A-Za-z_-]", "_", case_id)
    path = out_dir / "calls" / f"{name}__{variant}__{repeat}.json"
    if path.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        path.rename(path.with_name(f"{path.stem}.partial-{stamp}.json"))
    return path


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
        recording = _fresh_recording(out_dir, case.case_id, variant, repeat)
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
        append_row(out_dir / RESULTS, {"type": "result", **asdict(outcome)})
        total += outcome.calls
        results.append(outcome)
        print(
            f"{outcome.case_id} {variant} {repeat}회차: {outcome.status}"
            f" {outcome.error_code or ''} 호출 {outcome.calls}",
            flush=True,
        )
    return results, total, False

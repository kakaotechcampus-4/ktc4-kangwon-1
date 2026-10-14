"""고정 관점의 네 평가자가 같은 읽기 도구·예산으로 초안을 검토합니다."""

import asyncio
import json
import uuid
from collections import Counter
from dataclasses import replace

from pydantic import ValidationError

from app.canonical import canonical_json
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect
from app.llm.budget import BudgetExceeded
from app.llm.client import LLMHTTPError, LLMResponseError
from app.llm.config import LLMSettings
from app.text import has_digit

from .aliases import encode
from .contracts import EvaluatorReview, ReviewRef, ToolReply
from .report import ReportInvalid, fact_rows
from .sql_tool import error

PERSONAS = {
    "examiner": (
        "심사관입니다. 근거의 원천·기간·반경, L 중복 채점과 전체 업종의 unknown 이유를 "
        "검증하세요. 검토 전 공간 초안이 확정 사실이나 점수 근거가 되었는지 확인하세요."
    ),
    "founder": (
        "창업자 편입니다. 공간 초안과 임대인의 확인된 조건을 대조해 설비·운영 제약을 "
        "검토하세요. 소매업의 주방·조리 배기 부재만으로 불리하게 판단하지 마세요."
    ),
    "customer": (
        "손님 편입니다. 방문 동기·동선·확인된 고객층과 업종의 적합성을 검토하세요. "
        "결측 자료나 운영 가설을 확인된 수요로 단정하지 마세요."
    ),
    "landlord_advocate": (
        "임대인 편입니다. 공실 해소·임대 지속성·확인된 공간 조건과 과도한 확신을 검토하세요. "
        "예약·기업 거래 중심 업종에 층·보행 통행 조건을 일괄 적용하지 마세요."
    ),
}
COMMON = """검토 패킷을 읽고 읽기 도구는 최대 세 번 사용한 뒤 submit_review를 제출하세요.
get_facts는 업종·source·metrics 또는 받은 fact_ids로 좁혀 조회하고 같은 요청을 반복하지 마세요.
공간 요건은 source=industry_profile, metrics=[space_requirements]의 reviewed=false 초안입니다.
공간 비교 space_fit의 확인된 일치·불일치와 초안 표시를 검토하세요.
해당 없음·미확인을 불리 요인으로 쓰거나 초안을 법규·확정 시설 요건으로 단정하면 지적하세요.
패킷의 생략 표시가 있으면 get_facts로 원문을 확인하세요. fact_id는 요청 전용 별칭입니다.
새 점수·순위를 만들지 마세요. 지적마다 실제 fact_id 근거를 최대 다섯 개 붙이세요.
문장에 숫자를 직접 쓰지 말고 fact_ids로 인용하세요. 확인하지 못한 것은 확인 조건으로 남기세요.
실패한 조회를 동의로 해석하지 마세요."""


def save_review(scope, review):
    with connect(scope.path) as db:
        db.execute(
            "INSERT INTO agentic_reviews VALUES(?,?,?,?,?)",
            (
                scope.request_id,
                scope.snapshot_id,
                review.actor,
                review.model_dump_json(),
                utc_now_iso(),
            ),
        )


def compact_draft(draft):
    payload = draft.model_dump(mode="json")
    records = payload.get("L_records", [])
    top5 = payload.get("top5", [])[:5]
    candidates = {c["industry_code"] for c in top5}
    selected = [r for r in records if r["industry_code"] in candidates]
    limitations = {}
    for record in records:
        for limitation in record.get("limitations", []):
            limitations.setdefault(limitation, []).append(record["industry_code"])
    packet = {
        "draft_id": draft.report_id,
        "top5": [
            {
                k: v
                for k, v in candidate.items()
                if k
                in {
                    "industry_code",
                    "code_points",
                    "L_points",
                    "L_status",
                    "A",
                    "B",
                    "H",
                    "lower_ratio",
                    "upper_ratio",
                    "coverage",
                    "G",
                    "badge",
                    "fact_ids",
                }
            }
            for candidate in top5
        ],
        "L_counts": dict(
            Counter("unknown" if r.get("grade") is None else str(r["grade"]) for r in records)
        ),
        "candidate_factors": [
            {k: r[k] for k in ("industry_code", "status", "grade", "new_factors") if k in r}
            for r in selected
        ],
        "limitations": [
            {"text": text, "industry_codes": codes} for text, codes in limitations.items()
        ],
        "limitations_segments": payload.get("limitations_segments", []),
        "additional_context": "전체 점수는 get_scorecard, 사실 원문은 get_facts로 조회하세요.",
    }
    ids = set()

    def references(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "fact_id":
                    ids.add(item)
                elif key.endswith("fact_ids"):
                    ids.update(item)
                else:
                    references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)

    references(packet)
    packet["facts"] = list(
        {
            fact["fact_id"]: {k: v for k, v in fact.items() if k != "provenance_ref"}
            for fact in payload.get("facts", [])
            if fact["fact_id"] in ids
        }.values()
    )
    available = {f["fact_id"] for f in packet["facts"]}
    packet["facts"].extend(
        {"fact_id": fid, "read_required": True} for fid in sorted(ids - available)
    )
    return packet


def review_packet(scope, draft):
    packet = encode(scope, compact_draft(draft))
    for fact in packet["facts"]:
        if len(canonical_json(fact.get("value"))) > 500:
            fact.pop("value", None)
            fact["read_required"] = True
    if len(canonical_json(packet)) > 12000:
        # 원천·범위는 원문 조회로 넘기되 인용 ID와 관측 숫자는 보존합니다.
        for fact in packet["facts"]:
            for key in ("spatial_scope", "calc_version", "period", "unit", "industry_code"):
                fact.pop(key, None)
            fact["read_required"] = True
    if len(canonical_json(packet)) > 12000:
        raise ValueError("평가 패킷 상한 안에서 인용 근거를 보존할 수 없습니다.")
    return packet


async def review(loop, actor, executor, draft):
    submitted = None
    accepted = {}

    async def submit(input):
        nonlocal submitted
        if input.draft_id != draft.report_id:
            return error("DRAFT_MISMATCH", "검토할 초안 ID가 다릅니다.")
        if len({i.issue_id for i in input.issues}) != len(input.issues):
            return error("INVALID_REFERENCE", "지적 ID가 중복됩니다.")
        if len(set(accepted) | {i.issue_id for i in input.issues}) > 4:
            return error("INVALID_REFERENCE", "지적은 수정 제출을 포함해 최대 네 개입니다.")
        rejected = []
        for issue in input.issues:
            try:
                if not issue.fact_ids:
                    raise ReportInvalid("fact 근거를 붙이거나 이 지적을 제외하세요.")
                if has_digit(issue.comment + issue.suggested_check):
                    raise ReportInvalid("측정 숫자는 문장 대신 fact 근거로 인용하세요.")
                facts = await run_in_thread(fact_rows, loop.scope, set(issue.fact_ids))
                if any(not f["citable"] or f["status"] != "observed" for f in facts.values()):
                    raise ReportInvalid("관측된 인용 가능 근거로 바꾸세요.")
            except ReportInvalid as exc:
                rejected.append({"issue_id": issue.issue_id, "reason": str(exc)})
                continue
            accepted[issue.issue_id] = issue
        if rejected:
            reply = error("INVALID_REFERENCE", "거절된 지적만 수정하거나 제외해 다시 제출하세요.")
            reply.data = {"accepted": list(accepted), "rejected": rejected}
            return reply
        submitted = EvaluatorReview(
            actor=actor,
            status="completed",
            review_id="review_" + str(uuid.uuid4()),
            verdict=input.verdict,
            issues=list(accepted.values()),
        )
        for issue in submitted.issues:
            issue.issue_id = actor + ":" + issue.issue_id
        return ToolReply(status="ok", data=ReviewRef(review_id=submitted.review_id))

    executor.handlers = {"submit_review": submit}
    settings = replace(LLMSettings.from_env("evaluator"), reasoning_effort="none", max_tokens=4000)
    code = "SOURCE_UNAVAILABLE"
    try:
        messages = [
            {"role": "system", "content": PERSONAS[actor] + "\n" + COMMON},
            {
                "role": "user",
                "content": canonical_json(await run_in_thread(review_packet, loop.scope, draft)),
            },
        ]
        reads = 0
        submit_failures = 0
        while submitted is None:
            submit_only = reads >= 3 or submit_failures > 0
            if submit_only:
                loop.budget.submitting.add(actor)
            definitions = executor.definitions()
            if submit_only:
                definitions = [d for d in definitions if d["function"]["name"] == "submit_review"]
            async with asyncio.timeout(
                max(0.01, loop.budget.seconds_limit - loop.budget.active_seconds)
            ):
                message, _ = await loop._model(actor, messages, settings, definitions)
            calls = message.tool_calls or []
            if len(calls) != 1:
                code = "REPORT_INVALID"
                break
            call = calls[0]
            messages.append(message.model_dump(mode="json", exclude_none=True))
            try:
                arguments = json.loads(call.function.arguments)
            except (TypeError, ValueError):
                arguments = {}
            reply = (
                error("INVALID_ARGUMENT", "읽기를 마쳤습니다. submit_review만 제출하세요.")
                if submit_only and call.function.name != "submit_review"
                else await executor.execute(call.function.name, arguments)
            )
            if call.function.name == "submit_review":
                submit_failures += int(submitted is None)
            else:
                reads += 1
            await loop.event(
                "evaluation",
                "completed",
                {"actor": actor, "tool": call.function.name, "status": reply.status},
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": canonical_json(
                        await run_in_thread(encode, loop.scope, reply.model_dump(mode="json"))
                    ),
                }
            )
            if submitted is None and (reads >= 3 or submit_failures):
                messages.append(
                    {
                        "role": "user",
                        "content": "읽기를 마쳤습니다. 오류를 수정해 submit_review를 제출하세요.",
                    }
                )
            if submit_failures >= 3:
                code = reply.error.code if reply.error else "REPORT_INVALID"
                break
    except (
        BudgetExceeded,
        TimeoutError,
        LLMHTTPError,
        LLMResponseError,
        ValidationError,
        ValueError,
    ) as exc:
        code = (
            "BUDGET_EXCEEDED"
            if isinstance(exc, BudgetExceeded)
            else "TIMEOUT"
            if isinstance(exc, TimeoutError)
            else "SOURCE_UNAVAILABLE"
        )
    finally:
        loop.budget.submitting.discard(actor)
    result = submitted or EvaluatorReview(actor=actor, status="failed", issues=[], error_code=code)
    await run_in_thread(save_review, loop.scope, result)
    await loop.event(
        "evaluation",
        "completed" if submitted else "failed",
        {"actor": actor, "error_code": result.error_code},
    )
    return result

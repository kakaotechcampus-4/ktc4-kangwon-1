"""고정 관점의 네 평가자가 같은 읽기 도구·예산으로 초안을 검토합니다."""

import asyncio
import json
import re
import uuid
from dataclasses import replace

from pydantic import ValidationError

from app.canonical import canonical_json
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect
from app.llm.budget import BudgetExceeded
from app.llm.client import LLMHTTPError, LLMResponseError
from app.llm.config import LLMSettings

from .contracts import EvaluatorReview, ReviewRef, ToolReply
from .raw_query import error
from .report import ReportInvalid, fact_rows

PERSONAS = {
    "examiner": (
        "심사관입니다. 근거의 원천·기간·반경, L 중복 채점과 상위 열 업종의 unknown 이유를 "
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
COMMON = """제공한 초안을 읽고 읽기 도구는 최대 세 번 사용한 뒤 submit_review를 한 번 제출하세요.
get_facts는 업종·source·metrics 또는 받은 fact_ids로 좁혀 조회하고 같은 요청을 반복하지 마세요.
공간 요건은 source=industry_profile, metrics=[space_requirements]의 reviewed=false 초안입니다.
임대인 조건과 대조할 확인 항목으로만 사용하고 법규·확정 시설 요건·L 가감점 근거로 쓰지 마세요.
새 점수·순위를 만들지 마세요. 지적마다 실제 fact_id 근거를 붙이세요.
문장에 숫자를 직접 쓰지 말고 fact_ids로 인용하세요. 확인하지 못한 것은 확인 조건으로 남기세요.
검토를 마치면 submit_review로 제출하세요. 실패한 조회를 동의로 해석하지 마세요."""


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


async def review(loop, actor, executor, draft):
    submitted = None

    async def submit(input):
        nonlocal submitted
        if input.draft_id != draft.report_id:
            return error("DRAFT_MISMATCH", "검토할 초안 ID가 다릅니다.")
        if len({i.issue_id for i in input.issues}) != len(input.issues):
            return error("INVALID_REFERENCE", "지적 ID가 중복됩니다.")
        try:
            ids = {f for i in input.issues for f in i.fact_ids}
            facts = await run_in_thread(fact_rows, loop.scope, ids)
            if any(
                not i.fact_ids or re.search(r"\d", i.comment + i.suggested_check)
                for i in input.issues
            ):
                raise ReportInvalid("지적에는 fact 근거가 필요하며 문장 숫자는 허용하지 않습니다.")
            if any(not f["citable"] or f["status"] != "observed" for f in facts.values()):
                raise ReportInvalid("인용할 수 없는 근거입니다.")
        except ReportInvalid as exc:
            return error("INVALID_REFERENCE", str(exc))
        submitted = EvaluatorReview(
            actor=actor,
            status="completed",
            review_id="review_" + str(uuid.uuid4()),
            verdict=input.verdict,
            issues=input.issues,
        )
        for issue in submitted.issues:
            issue.issue_id = actor + ":" + issue.issue_id
        return ToolReply(status="ok", data=ReviewRef(review_id=submitted.review_id))

    executor.handlers = {"submit_review": submit}
    messages = [
        {"role": "system", "content": PERSONAS[actor] + "\n" + COMMON},
        {
            "role": "user",
            "content": canonical_json({"actor": actor, "draft": draft.model_dump(mode="json")}),
        },
    ]
    settings = replace(LLMSettings.from_env("evaluator"), reasoning_effort="none", max_tokens=16000)
    code = "SOURCE_UNAVAILABLE"
    try:
        no_progress = 0
        while submitted is None:
            async with asyncio.timeout(
                max(0.01, loop.budget.seconds_limit - loop.budget.active_seconds)
            ):
                message, _ = await loop._model(actor, messages, settings, executor.definitions())
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
            reply = await executor.execute(call.function.name, arguments)
            await loop.event(
                "evaluation",
                "completed",
                {"actor": actor, "tool": call.function.name, "status": reply.status},
            )
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": reply.model_dump_json()}
            )
            no_progress = no_progress + 1 if reply.error or reply.duplicate else 0
            if no_progress >= 3 or (reply.error and reply.error.code == "BUDGET_EXCEEDED"):
                code = reply.error.code if reply.error else "DUPLICATE_CALL"
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
    result = submitted or EvaluatorReview(actor=actor, status="failed", issues=[], error_code=code)
    await run_in_thread(save_review, loop.scope, result)
    await loop.event(
        "evaluation",
        "completed" if submitted else "failed",
        {"actor": actor, "error_code": result.error_code},
    )
    return result

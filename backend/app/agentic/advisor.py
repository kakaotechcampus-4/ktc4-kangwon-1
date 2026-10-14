"""decision이 선택한 근거만 사용하는 자문과 감사 기록입니다."""

import asyncio
import json
import uuid

from pydantic import ValidationError

from app.canonical import canonical_json
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect
from app.llm.budget import BudgetExceeded
from app.llm.client import LLMHTTPError, LLMResponseError
from app.llm.config import LLMSettings

from .contracts import AdvisorAnswer, ToolReply
from .report import ReportInvalid, fact_rows
from .sql_tool import error

ADVISOR_PROMPT = """당신은 decision의 상권 자문역입니다. 질문과 제공한 fact만 읽으며
도구는 없습니다.
점수·순위는 매기지 않습니다. 대안 해석·성립 조건·확신도·부족한 사실을 짧은
JSON으로 반환하세요.
형식은 consult_id, status(ok),
interpretations[{claim,fact_ids,conditions,confidence(high/medium/low)}],
missing_facts, limitations입니다.
제공되지 않은 fact_id나 수치를 만들지 마세요."""


async def ask_advisor(loop, input):
    if not loop.budget.measurement and loop.state.get("advisor_calls", 0) >= 2:
        return error("BUDGET_EXCEEDED", "자문은 요청당 두 회까지입니다.")
    loop.state["advisor_calls"] = loop.state.get("advisor_calls", 0) + 1
    try:
        facts = await run_in_thread(fact_rows, loop.scope, input.fact_ids)
    except ReportInvalid:
        return error("UNKNOWN_FACT", "현재 요청의 fact만 자문에 전달할 수 있습니다.")
    if any(f["status"] != "observed" or not f["citable"] for f in facts.values()):
        return error("UNCITABLE", "관측된 fact만 자문에 전달할 수 있습니다.")
    consult_id = "consult_" + str(uuid.uuid4())
    receipt = {}
    settings = LLMSettings.from_env("advisor", max_tokens=1000, timeout_seconds=45)
    payload = {
        "consult_id": consult_id,
        "question": input.question,
        "industry_codes": input.industry_codes,
        "facts": [
            {
                "fact_id": f["fact_id"],
                "metric": f["metric"],
                "value": json.loads(f["value_json"]),
                "unit": f["unit"],
                "status": f["status"],
                "citable": bool(f["citable"]),
                "period": f["period"],
                "spatial_scope": json.loads(f["spatial_scope_json"]),
            }
            for f in facts.values()
        ],
    }
    try:
        async with asyncio.timeout(
            max(0.01, loop.budget.seconds_limit - loop.budget.active_seconds)
            if loop.budget.measurement
            else min(45, max(0.01, 300 - loop.budget.active_seconds))
        ):
            value, receipt = await loop._model(
                "advisor",
                [
                    {"role": "system", "content": ADVISOR_PROMPT},
                    {"role": "user", "content": canonical_json(payload)},
                ],
                settings,
                receipt=receipt,
            )
        answer = AdvisorAnswer.model_validate(value)
        if answer.consult_id != consult_id or any(
            not set(i.fact_ids) <= set(input.fact_ids) for i in answer.interpretations
        ):
            raise ValueError("자문 근거 범위 오류")
    except (
        LLMHTTPError,
        LLMResponseError,
        TimeoutError,
        ValidationError,
        ValueError,
        BudgetExceeded,
    ):
        loop.state["advisor_unavailable"] = True
        answer = AdvisorAnswer(
            consult_id=consult_id,
            status="unavailable",
            limitations=["자문을 확인하지 못해 decision이 단독 판단합니다."],
        )
    await run_in_thread(save_advisor, loop, input, answer, receipt, settings)
    return ToolReply(status="ok", data=answer, warnings=answer.limitations)


def save_advisor(loop, input, answer, receipt, settings):
    actual = receipt.get("model")
    family = (
        "anthropic"
        if "claude" in (actual or settings.model or "").lower()
        else "openai"
        if "gpt" in (actual or settings.model or "").lower()
        else "unknown"
    )
    with connect(loop.scope.path) as db:
        db.execute(
            "INSERT INTO advisor_consults VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                answer.consult_id,
                loop.scope.request_id,
                loop.scope.snapshot_id,
                input.question,
                canonical_json(input.fact_ids),
                actual,
                family,
                canonical_json(receipt.get("usage")),
                answer.model_dump_json(),
                answer.status,
                utc_now_iso(),
            ),
        )

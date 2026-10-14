"""고정 지시문·도구 루프·자문·질문 재개. 기존 그래프에는 연결하지 않습니다."""

import asyncio
import json
import uuid
from collections import Counter
from dataclasses import dataclass, replace
from time import monotonic
from types import SimpleNamespace

from pydantic import ValidationError

from app.db.connection import connect
from app.llm.budget import BudgetExceeded, llm_scope
from app.llm.client import LLMHTTPError, LLMResponseError, complete_json, complete_tools
from app.llm.config import LLMSettings
from app.storage.raw import _json, _now, _write

from .budget import RuntimeBudget
from .contracts import (
    AdvisorAnswer,
    MapResult,
    QuestionSessionRef,
    RegulationResult,
    ReportProposal,
    SubmitResult,
    ToolReply,
)
from .raw_query import error
from .report import ReportInvalid, fact_rows, finalize, load_base
from .tools import ToolExecutor

SYSTEM_PROMPT = """당신은 빈 상가의 업종 검토를 담당하는 decision입니다. 코드 점수는
고정이고 자료는 읽기 도구로 확인합니다.
계산 자료를 먼저 읽고 필요할 때만 원문·지도·규제를 조회하세요. 수치
계산·점수 순위·배지는 서버가 정합니다.
L은 코드 하한 상위 열 업종과 fact 근거로 추가한 최대 두 업종만
검토합니다. 나머지는 판단 미검토입니다.
L에는 실제 조회한 새 fact만 사용하세요. D/C/S 지표 반복은 금지하며
근거가 없으면 unknown입니다.
L 등급은 새 요인 기준: 유리 요인 둘 이상·불리 없음이면 최고, 유리
하나·불리 없음이면 그다음,
중립 또는 유리·불리 상쇄는 중간, 불리 하나는 낮음, 불리 둘 이상 또는 큰
운영 제약은 최저입니다.
애매하면 ask_advisor로 질문과 선택한 fact만 전달하세요. 실패하면
혼자 판단합니다. 미확인 임대 조건만 ask_user로 질문하세요.
보고서 문장 숫자는 text에 쓰지 말고 fact 슬롯으로 인용하세요. 인용
불가 사실·추측은 사실처럼 말하지 마세요.
LRecord에는 초기 score_snapshot_id·코드 순위·선정 사유,
실제 tool_call_id, 확인 질문, 새 요인·fact_id·등급을
기록하세요.
추가 선정은 decision_extra와 reason_fact_ids가
필요합니다. 자문은 점수를 매기지 않습니다.
같은 조회를 반복하지 말고 submit_draft(phase=draft)로
제출하세요. 모델은 점수·배지를 제출하지 않습니다."""
ADVISOR_PROMPT = """당신은 decision의 상권 자문역입니다. 질문과 제공한 fact만 읽으며
도구는 없습니다.
점수·순위는 매기지 않습니다. 대안 해석·성립 조건·확신도·부족한 사실을 짧은
JSON으로 반환하세요.
형식은 consult_id, status(ok),
interpretations[{claim,fact_ids,conditions,confidence(high/medium/low)}],
missing_facts, limitations입니다.
제공되지 않은 fact_id나 수치를 만들지 마세요."""


@dataclass
class LoopOutcome:
    status: str
    result: object = None
    question_session_id: str | None = None
    questions: list | None = None
    budget: dict | None = None


def _save(scope, state, status, result_model=None):
    with connect(scope.path) as db:
        db.execute(
            "INSERT INTO agentic_runs VALUES(?,?,?,?,?,?,?) ON "
            "CONFLICT(request_id) DO UPDATE SET "
            "status=excluded.status,state_json=excluded.state_json,result_json=excluded.result_json,updated_at=excluded.updated_at",
            (
                scope.request_id,
                scope.snapshot_id,
                scope.run_id,
                status,
                _json(state),
                result_model.model_dump_json() if result_model else None,
                _now(),
            ),
        )


class DecisionLoop:
    def __init__(
        self,
        scope,
        site,
        base_id,
        base_rows,
        *,
        generate=None,
        advisor_generate=None,
        saved=None,
        budget=None,
    ):
        self.scope, self.site, self.base_id, self.base_rows = scope, site, base_id, base_rows
        self.generate, self.advisor_generate = generate, advisor_generate
        self.state = saved or {
            "messages": [],
            "advisor_unavailable": False,
            "asked": False,
            "limitations": [],
            "tool_sequence": [],
            "known_fact_ids": [],
        }
        self.budget = budget or RuntimeBudget(self.state.get("budget"))
        self.budget.on_change = self._budget_changed
        self.tools = ToolExecutor(
            scope,
            site,
            handlers={
                "ask_advisor": self.ask_advisor,
                "ask_user": self.ask_user,
                "submit_draft": self.submit_draft,
            },
        )
        self.tools.shared.calls = Counter(
            {
                tuple(k.split("|")) if "|" in k else k: v
                for k, v in self.state.get("tool_counts", {}).items()
            }
        )
        self.tools.shared.seen = set(self.state.get("tool_seen", []))
        self.tools.shared.map_keys = set(self.state.get("map_keys", []))
        self.tools.shared.map_http = self.state.get("map_http", 0)
        if self.state.get("regulation"):
            self.tools.shared.regulation = RegulationResult.model_validate(self.state["regulation"])
        self.tools.shared.map_cache = {
            k: ToolReply[MapResult].model_validate(v)
            for k, v in self.state.get("map_cache", {}).items()
        }
        self.done = None
        self.waiting = None
        self.settings = replace(
            LLMSettings.from_env("decision"), reasoning_effort="none", max_tokens=3000
        )
        if not self.state["messages"]:
            summary = [
                [i, r["code"], r["lower"], r["applicable_weight"], r["coverage"]]
                for i, r in enumerate(base_rows, 1)
            ]
            self.state["messages"] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _json(
                        {
                            "request_id": scope.request_id,
                            "site": site.model_dump(mode="json"),
                            "snapshot_id": scope.snapshot_id,
                            "score_snapshot_id": base_id,
                            "score_summary": {
                                "columns": ["rank", "code", "B", "A", "coverage"],
                                "rows": summary,
                            },
                            "L_top10": [r["code"] for r in base_rows[:10]],
                        }
                    ),
                },
            ]

    @classmethod
    async def create(cls, scope, site, **kwargs):
        base_id, rows = await _write(load_base, scope)
        return cls(scope, site, base_id, rows, **kwargs)

    def evaluator_executors(self):
        return {
            actor: self.tools.for_actor(actor)
            for actor in ("examiner", "founder", "customer", "landlord_advocate")
        }

    async def _budget_changed(self, budget):
        self.state["budget"] = budget
        await self.save()

    async def save(self, status="running", result_model=None):
        shared = self.tools.shared
        self.state.update(
            tool_counts={
                "|".join(k) if isinstance(k, tuple) else k: v for k, v in shared.calls.items()
            },
            tool_seen=sorted(shared.seen),
            map_keys=sorted(shared.map_keys),
            map_http=shared.map_http,
            regulation=shared.regulation.model_dump(mode="json") if shared.regulation else None,
            map_cache={k: v.model_dump(mode="json") for k, v in shared.map_cache.items()},
            budget=self.budget.snapshot(),
        )
        await _write(_save, self.scope, self.state, status, result_model)

    async def _model(self, role, messages, settings, definitions=None, receipt=None):
        receipt = receipt if receipt is not None else {}
        started = monotonic()
        remaining = 24000 - self.budget.totals()[1]
        if remaining <= 0:
            raise BudgetExceeded()
        settings = replace(settings, max_tokens=min(settings.max_tokens or 3000, remaining))
        generator = self.generate if role == "decision" else self.advisor_generate
        if generator is None:
            with llm_scope(self.budget, role):
                if role == "decision":
                    value = await complete_tools(messages, definitions, settings, receipt=receipt)
                else:
                    value = await complete_json(
                        messages[0]["content"], messages[1]["content"], settings, receipt=receipt
                    )
        else:
            attempt = await self.budget.reserve(role, input_chars=len(_json(messages)))
            status = "error"
            try:
                value = generator(messages, definitions, settings, receipt)
                if hasattr(value, "__await__"):
                    value = await value
                status = "ok"
            finally:
                usage = receipt.get("usage")
                await self.budget.finish(
                    attempt,
                    status=status,
                    elapsed_ms=int((monotonic() - started) * 1000),
                    usage=SimpleNamespace(**usage) if usage else None,
                    model=receipt.get("model"),
                )
        return value, receipt

    async def ask_advisor(self, input):
        if self.state.get("advisor_calls", 0) >= 2:
            return error("BUDGET_EXCEEDED", "자문은 요청당 두 회까지입니다.")
        self.state["advisor_calls"] = self.state.get("advisor_calls", 0) + 1
        try:
            facts = await _write(fact_rows, self.scope, input.fact_ids)
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
            async with asyncio.timeout(min(45, max(0.01, 300 - self.budget.active_seconds))):
                value, receipt = await self._model(
                    "advisor",
                    [
                        {"role": "system", "content": ADVISOR_PROMPT},
                        {"role": "user", "content": _json(payload)},
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
            self.state["advisor_unavailable"] = True
            answer = AdvisorAnswer(
                consult_id=consult_id,
                status="unavailable",
                limitations=["자문을 확인하지 못해 decision이 단독 판단합니다."],
            )
        await _write(self._save_advisor, input, answer, receipt, settings)
        return ToolReply(status="ok", data=answer, warnings=answer.limitations)

    def _save_advisor(self, input, answer, receipt, settings):
        actual = receipt.get("model")
        family = (
            "anthropic"
            if "claude" in (actual or settings.model or "").lower()
            else "openai"
            if "gpt" in (actual or settings.model or "").lower()
            else "unknown"
        )
        with connect(self.scope.path) as db:
            db.execute(
                "INSERT INTO advisor_consults VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    answer.consult_id,
                    self.scope.request_id,
                    self.scope.snapshot_id,
                    input.question,
                    _json(input.fact_ids),
                    actual,
                    family,
                    _json(receipt.get("usage")),
                    answer.model_dump_json(),
                    answer.status,
                    _now(),
                ),
            )

    async def ask_user(self, input):
        if self.state["asked"]:
            return error("ALREADY_ANSWERED", "질문 세션을 반복할 수 없습니다.")
        self.state["asked"] = True
        session_id = "question_" + str(uuid.uuid4())
        await _write(self._save_question, session_id, input)
        self.waiting = LoopOutcome(
            "waiting_for_input",
            question_session_id=session_id,
            questions=input.questions,
            budget=self.budget.snapshot(),
        )
        return ToolReply(status="ok", data=QuestionSessionRef(question_session_id=session_id))

    def _save_question(self, session_id, input):
        with connect(self.scope.path) as db:
            db.execute(
                "INSERT INTO agentic_questions VALUES(?,?,?,?,?,?,?)",
                (
                    session_id,
                    self.scope.request_id,
                    self.scope.snapshot_id,
                    _json([q.model_dump(mode="json") for q in input.questions]),
                    "{}",
                    "waiting",
                    _now(),
                ),
            )

    async def submit_draft(self, input):
        if input.phase != "draft" or input.review_resolutions:
            return error("INVALID_ARGUMENT", "PR5는 피드백 없는 초안만 제출합니다.")
        try:
            self.done = await _write(
                lambda: finalize(
                    self.scope,
                    input.report,
                    self.base_id,
                    self.base_rows,
                    advisor_unavailable=self.state["advisor_unavailable"],
                    regulation_result=self.tools.shared.regulation,
                )
            )
            self.state["last_draft"] = input.report.model_dump(mode="json")
        except ReportInvalid:
            return error(
                "L_EVIDENCE_INVALID",
                "새 근거·중복·검토 범위·fact 슬롯·실제 호출 기록을 확인하세요.",
            )
        return ToolReply(
            status="ok",
            data=SubmitResult(
                report_id=self.done.report_id,
                validation_status="valid",
                rendered_preview_ref="agentic_reports:" + self.done.report_id,
                score_snapshot_id=self.done.score_snapshot_id,
            ),
        )

    async def fallback(self, reason):
        self.state["limitations"].append(reason)
        proposal = ReportProposal.model_validate(self.state.get("last_draft", {}))
        self.done = await _write(
            lambda: finalize(
                self.scope,
                proposal,
                self.base_id,
                self.base_rows,
                limitations=self.state["limitations"],
                advisor_unavailable=self.state["advisor_unavailable"],
                regulation_result=self.tools.shared.regulation,
            )
        )
        await self.save("draft_available", self.done)
        return LoopOutcome("draft_available", result=self.done, budget=self.budget.snapshot())

    def model_messages(self):
        messages = self.state["messages"]
        if len(messages) == 2:
            return messages
        last = next(
            i for i in range(len(messages) - 1, 1, -1) if messages[i]["role"] == "assistant"
        )
        prefix = messages[:2]
        if self.state.get("user_answers"):
            prefix = prefix + [
                {"role": "user", "content": _json({"user_answers": self.state["user_answers"]})}
            ]
        memory = self.state.get("working_facts", [])
        while True:
            model = (
                prefix
                + (
                    [{"role": "user", "content": _json({"previous_facts": memory})}]
                    if memory
                    else []
                )
                + messages[last:]
            )
            if len(_json(model)) + self.budget.schema_chars <= 24000 or not memory:
                return model
            memory = memory[1:]

    async def compact_reply(self, reply, name, arguments):
        body = reply.model_dump(mode="json")
        ids = list(dict.fromkeys(reply.fact_ids))
        data = body.get("data") or {}
        if "facts" in data:
            ids.extend(f["fact_id"] for f in data["facts"])
        if ids:
            facts = await _write(fact_rows, self.scope, list(dict.fromkeys(ids))[:64])
            added = [
                {
                    "fact_id": f["fact_id"],
                    "metric": f["metric"],
                    "value": json.loads(f["value_json"]),
                    "unit": f["unit"],
                    "tool_call_id": self.tools.last_call_id,
                }
                for f in facts.values()
            ]
            self.state["working_facts"] = (self.state.get("working_facts", []) + added)[-64:]
        if name == "check_regulation" and data:
            data["zones"] = [{k: v for k, v in z.items() if k != "geometry"} for z in data["zones"]]
            data["industry_restrictions"] = [
                r for r in data["industry_restrictions"] if r["status"] != "해당 없음"
            ]
        body["fact_ids"] = []  # 행별 근거 ID는 data에 보존하고 중복 전송만 줄입니다.
        for field in ("summaries", "scorecards", "facts", "places", "rows"):
            entries = data.get(field)
            if not entries:
                continue
            original = len(entries)
            while entries and len(_json(body)) > 4000:
                entries.pop()
            if len(entries) < original:
                body["truncated"] = True
                body["warnings"].append(
                    "응답 예산으로 일부만 제공합니다. 필요한 범위를 추가 조회하세요."
                )
                if field in {"summaries", "scorecards", "facts"} and not arguments.get("fact_ids"):
                    data["next_cursor"] = str(int(arguments.get("cursor") or 0) + len(entries))
                if field == "places":
                    data["has_more"] = True
        return {"tool_call_id": self.tools.last_call_id} | body

    async def run(self):
        while True:
            try:
                definitions = self.tools.definitions()
                decision_used = sum(c["role"] == "decision" for c in self.budget.calls)
                if decision_used >= 7:
                    definitions = [
                        d for d in definitions if d["function"]["name"] == "submit_draft"
                    ]
                self.budget.schema_chars = len(_json(definitions))
                if self.budget.totals()[1] >= 24000 or self.budget.active_seconds >= 300:
                    raise BudgetExceeded()
                async with asyncio.timeout(max(0.01, min(180, 300 - self.budget.active_seconds))):
                    message, _ = await self._model(
                        "decision", self.model_messages(), self.settings, definitions
                    )
                calls = message.tool_calls or []
                if len(calls) != 1:
                    return await self.fallback(
                        "단일 도구 호출 조건을 지키지 않아 코드 점수로 마무리했습니다."
                    )
                self.state["messages"].append(message.model_dump(mode="json", exclude_none=True))
                call = calls[0]
                name = call.function.name
                try:
                    arguments = json.loads(call.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                self.state["tool_sequence"].append(name)
                try:
                    reply = await self.tools.execute(name, arguments)
                except ReportInvalid:
                    reply = error("UNKNOWN_FACT", "현재 요청의 fact만 조회할 수 있습니다.")
                content = await self.compact_reply(reply, name, arguments)
                self.state["messages"].append(
                    {"role": "tool", "tool_call_id": call.id, "content": _json(content)}
                )
                if self.done:
                    await self.save("draft_available", self.done)
                    return LoopOutcome(
                        "draft_available", result=self.done, budget=self.budget.snapshot()
                    )
                if self.waiting:
                    await self.save("waiting_for_input")
                    return self.waiting
                if reply.error and reply.error.code in {
                    "DUPLICATE_CALL",
                    "ALREADY_ANSWERED",
                    "BUDGET_EXCEEDED",
                }:
                    return await self.fallback(
                        "반복 조회·질문 또는 도구 상한으로 코드 점수와 확인한 근거만 제공합니다."
                    )
                await self.save()
            except (BudgetExceeded, TimeoutError):
                return await self.fallback(
                    "호출·시간·토큰 예산 상한에 도달해 코드 점수로 마무리했습니다."
                )
            except LLMResponseError as exc:
                if exc.code != "LLM_OUTPUT_LIMIT":
                    raise
                return await self.fallback("모델 출력 상한에 도달해 코드 점수로 마무리했습니다.")

    @classmethod
    async def resume(cls, scope, site, answers, **kwargs):
        def load():
            with connect(scope.path) as db:
                row = db.execute(
                    "SELECT state_json,status FROM agentic_runs WHERE request_id=? AND "
                    "snapshot_id=?",
                    (scope.request_id, scope.snapshot_id),
                ).fetchone()
                question = db.execute(
                    "SELECT question_session_id,questions_json,status FROM "
                    "agentic_questions WHERE request_id=? AND snapshot_id=?",
                    (scope.request_id, scope.snapshot_id),
                ).fetchone()
                if (
                    row is None
                    or row[1] != "waiting_for_input"
                    or question is None
                    or question[2] != "waiting"
                ):
                    raise ValueError("재개할 질문 세션이 없습니다.")
                fields = {q["field"] for q in json.loads(question[1])}
                if set(answers) != fields or any(
                    not isinstance(v, str) or not v.strip() or len(v) > 500
                    for v in answers.values()
                ):
                    raise ValueError("답변 항목·길이가 잘못되었습니다.")
                return json.loads(row[0]), question[0]

        saved, question_id = await _write(load)
        saved = await _write(_save_user_facts, scope, answers, question_id, saved)
        return await cls.create(scope, site, saved=saved, **kwargs)


def _save_user_facts(scope, answers, question_id, saved):
    from .registry import register_fact

    response = scope.record_sync(
        source="user", source_type="api", args={}, page="1", status=200, payload={"rows": [answers]}
    )
    with connect(scope.path) as db:
        db.execute("BEGIN IMMEDIATE")
        question = db.execute(
            "SELECT status FROM agentic_questions WHERE question_session_id=?",
            (question_id,),
        ).fetchone()
        if question is None or question[0] != "waiting":
            raise ValueError("이미 답변한 질문입니다.")
        ref = db.execute(
            "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
        ).fetchone()[0]
        ids = {}
        for field, value in answers.items():
            metric = (
                field
                if field
                in {"floor", "exclusive_area", "existing_facilities", "industry_preferences"}
                else "space_condition"
            )
            ids[field] = register_fact(
                scope,
                industry_code=None,
                source="user",
                metric=metric,
                value=value,
                unit="임대인 답변",
                status="observed",
                row_ids=[ref],
                field_pointer="/" + field,
                connection=db,
            )
        saved["user_answers"] = {"answers": answers, "fact_ids": ids}
        saved["messages"].append(
            {"role": "user", "content": _json({"user_answers": saved["user_answers"]})}
        )
        db.execute(
            "UPDATE agentic_questions SET status='answered',answers_json=? "
            "WHERE question_session_id=?",
            (_json(answers), question_id),
        )
        db.execute(
            "UPDATE agentic_runs SET status='running',state_json=? "
            "WHERE request_id=? AND snapshot_id=?",
            (_json(saved), scope.request_id, scope.snapshot_id),
        )
    return saved

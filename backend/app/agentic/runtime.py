"""고정 지시문·도구 루프·자문·질문 재개. 기존 그래프에는 연결하지 않습니다."""

import asyncio
import json
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from time import monotonic
from types import SimpleNamespace

from pydantic import ValidationError

from app.canonical import canonical_json
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect
from app.db.repository import append_event
from app.industries.catalog import INDUSTRIES
from app.llm.budget import BudgetExceeded, llm_scope
from app.llm.client import LLMHTTPError, LLMResponseError, complete_json, complete_tools
from app.llm.config import LLMSettings

from . import advisor, questions
from .aliases import encode, encode_messages
from .budget import RuntimeBudget
from .contracts import (
    EvaluatorReview,
    LInput,
    LRecord,
    MapResult,
    RegulationResult,
    ReportProposal,
    ScorecardResult,
    SubmitLResult,
    SubmitResult,
    TextSegment,
    ToolReply,
)
from .evaluators import review
from .l_input import build_record
from .questions import LoopOutcome
from .read_tools import score_summary
from .report import (
    ReportInvalid,
    complete_l_records,
    finalize,
    load_base,
    recompute_l_scores,
    validate_l_records,
)
from .scoring import rank_candidates
from .snapshot import persist_space_requirements
from .space import ensure_space_fits
from .sql_tool import error
from .tools import ToolExecutor, validation_message

SYSTEM_PROMPT = """당신은 빈 상가의 업종 검토를 담당하는 decision입니다.
계산·코드 점수·순위·배지는 서버가 정합니다. 초기 score_summary를 재사용하세요.
전체 카탈로그의 모든 업종을 같은 기준으로 검토합니다. 코드 순위로 검토 범위를 제한하지 마세요.
순서는 초기 점수표 확인 → 필요한 공간 질문 한 번 → 공간 비교 근거 확인 → 필요한 추가 조사
→ submit_l → 재계산된 Top Five로 submit_draft입니다.
submit_l은 industry_code와 factors(fact_id의 짧은 별칭·direction·severe)만 받습니다.
중립으로 검토했으면 neutral=true와 확인한 새 근거 fact_ids를 쓰세요.
근거가 없으면 factors 없이 제출하고 짧은 note에 이유를 남기세요.
등급·상태·선정 사유·도구 호출 ID는 쓰지 마세요. 코드가 계산합니다.
모든 업종을 제출하세요. 묶음 크기 제한은 없고 이미 채택한 업종은 무시됩니다.
거절 목록의 업종만 고쳐서 다시 제출하세요. note의 숫자는 코드가 설명으로 대체합니다.
전체 제출 또는 finish=true로 L을 닫습니다.
L을 닫으면 서버가 전체 점수와 Top Five를 다시 계산합니다. 그 결과로 보고서를 작성하세요.
submit_draft는 보고서만 제출하며 추천·제외 후보는 각각 최대 다섯 업종입니다.
L을 다시 제출하지 마세요.
get_facts는 업종·source·metrics를 지정하거나 받은 fact_ids로 좁혀 읽으세요.
공간 비교는 source=industry_profile, metrics=[space_fit], limit=51로 한 번 묶어 조회하세요.
공간 요건의 면적은 운영 추정입니다.
층과 필수·선호 설비는 규칙이 추천 제외·순위에 반영하므로 L에 중복 사용하지 마세요.
공간 L 근거는 확인된 면적 비교를 사용하세요.
조건부 설비 비교는 현재 미확인이므로 확인 조건에 남기세요.
space_fit의 fact_id와 방향만 제출하면 코드가 L에 허용된 비교 항목을 선택합니다.
해당 없음·미확인은 요인으로 쓰지 말고 요건과 미확인 조건을 함께 설명하세요.
confirmed_space의 층·전용면적은 source=user의 확인 화면 확정 사실이며 다시 묻지 마세요.
설비 상태 present는 있음, installable은 설치 가능, unavailable은 설치 불가입니다.
설치 가능을 설치 완료로, 단순한 설비 부재를 설치 불가로 바꾸지 마세요.
소매업은 주방·조리 배기가 없다는 이유로 불리하게 판단하지 마세요.
기업 간 거래·예약 중심 업종도 보행 통행이나 층 조건만으로 일괄 탈락시키지 마세요.
임대인이 아직 확인하지 않은 핵심 공간 조건만 처음에 최대 세 항목을 한 번 묶어 ask_user로
질문하세요. 자료로 확인할 수 있거나 이미 답한 조건은 다시 묻지 마세요.
기존 fact로 설명할 수 없는 경쟁·시설·규제 조건이 있을 때만 원문·지도·규제를 조회하세요.
해석 충돌이나 결측으로 후보·확인 조건이 달라질 때만 ask_advisor로 질문과 선택한 fact를
전달하세요. 자문은 점수를 매기지 않으며 실패하면 불확실성을 남겨 직접 판단합니다.
L에는 실제 조회한 새 fact만 사용하세요. D/C/S 지표 반복과 같은 근거의 중복 채점은 금지합니다.
L 등급은 새 요인 기준: 유리 둘 이상·불리 없음은 최고, 유리 하나·불리 없음은 그다음,
중립 또는 유리·불리 상쇄는 중간, 불리 하나는 낮음, 불리 둘 이상 또는 큰 운영 제약은 최저입니다.
fact는 도구에서 받은 여덟 자리 별칭만 쓰세요. 별칭을 만들거나 추측하지 마세요.
모든 보고서 문장 숫자는 text에 직접 쓰지 말고 fact_id 슬롯으로 인용하세요.
인용 불가 사실·추측은 확인 조건으로 남기세요. 동일 조회를 반복하지 말고
submit_draft(phase=draft)로 제출하세요. 모델은 점수·배지를 제출하지 않습니다."""


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
                canonical_json(state),
                result_model.model_dump_json() if result_model else None,
                utc_now_iso(),
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
        evaluator_generate=None,
        saved=None,
        budget=None,
        measurement=False,
        recorder=None,
        allow_questions=True,
        confirmed_space=None,
    ):
        self.scope, self.site, self.base_id, self.base_rows = scope, site, base_id, base_rows
        self.generate, self.advisor_generate = generate, advisor_generate
        self.evaluator_generate = evaluator_generate
        self.state = saved or {
            "messages": [],
            "advisor_unavailable": False,
            "asked": False,
            "limitations": [],
            "tool_sequence": [],
            "known_fact_ids": list(confirmed_space["fact_ids"].values()) if confirmed_space else [],
        }
        self.budget = budget or RuntimeBudget(self.state.get("budget"), measurement=measurement)
        self.state.setdefault("allow_questions", allow_questions)
        self.state.setdefault(
            "confirmed_question_fields",
            [
                field
                for field in (confirmed_space or {}).get("values", {})
                if field in {"floor", "exclusive_area"}
            ],
        )
        self.state.setdefault("L_records", {})
        self.state.setdefault("L_closed", False)
        self.state.setdefault("phase", "L")
        self.recorder = recorder
        self.budget.on_change = self._budget_changed
        self.tools = ToolExecutor(
            scope,
            site,
            handlers={
                "ask_advisor": self.ask_advisor,
                "ask_user": self.ask_user,
                "submit_draft": self.submit_draft,
                "submit_l": self.submit_l,
            },
        )
        self.tools.shared.measurement = self.budget.measurement
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
            LLMSettings.from_env("decision"),
            reasoning_effort="none",
            max_tokens=16000,
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
                    "content": canonical_json(
                        {
                            "request_id": scope.request_id,
                            "site": site.model_dump(mode="json"),
                            "snapshot_id": scope.snapshot_id,
                            "score_snapshot_id": base_id,
                            "score_summary": {
                                "columns": ["rank", "code", "B", "A", "coverage"],
                                "rows": summary,
                            },
                            "L_industry_codes": list(INDUSTRIES),
                            "industry_names": INDUSTRIES,
                            **({"confirmed_space": confirmed_space} if confirmed_space else {}),
                        }
                    ),
                },
            ]

    @classmethod
    async def create(cls, scope, site, **kwargs):
        base_id, rows = await run_in_thread(load_base, scope)
        await run_in_thread(persist_space_requirements, scope)
        await run_in_thread(ensure_space_fits, scope)
        return cls(scope, site, base_id, rows, **kwargs)

    def evaluator_executors(self):
        return {
            actor: self.tools.for_actor(actor)
            for actor in ("examiner", "founder", "customer", "landlord_advocate")
        }

    async def _budget_changed(self, budget):
        self.state["budget"] = budget
        await self.save()

    async def event(self, stage, event, detail):
        try:
            await run_in_thread(
                lambda: append_event(
                    self.scope.request_id, stage, event, detail, db_path=self.scope.path
                )
            )
        except Exception:
            # 진행 기록만 격리합니다. 결과·예산 저장 실패는 호출자에게 전파합니다.
            pass

    async def review_and_finalize(self):
        draft = self.done
        if draft is None:
            raise ValueError("평가할 초안이 없습니다.")
        await self.event("evaluation", "started", {})
        reviewers = self.evaluator_executors()
        async with asyncio.TaskGroup() as group:
            tasks = [
                group.create_task(review(self, actor, executor, draft))
                for actor, executor in reviewers.items()
            ]
        reviews = [task.result() for task in tasks]
        self.state["reviews"] = [r.model_dump(mode="json") for r in reviews]
        self.state["phase"] = "final"
        self.state["feedback_rounds"] = 1
        self.state["messages"].append(
            {
                "role": "user",
                "content": canonical_json(
                    {
                        "instruction": (
                            "평가 결과를 한 번 반영하여 submit_draft(phase=final)로 제출하세요. "
                            "모든 issue_id에 accepted/partial/rejected와 이유·근거를 "
                            "review_resolutions에 기록하세요. 추가 임대인 질문은 하지 마세요."
                        ),
                        "reviews": self.state["reviews"],
                    }
                ),
            }
        )
        self.done = None
        self.state["no_progress"] = 0
        await self.event("final", "started", {"feedback_round": 1})
        outcome = await self.run()
        if outcome.result is None:
            raise ValueError("최종 결과가 없습니다.")
        if outcome.result.evaluator_reviews != reviews:
            # 최종 모델 실패에도 완료된 검토를 보존하며 반영 실패를 명시합니다.
            result = outcome.result.model_copy(
                update={
                    "evaluator_reviews": reviews,
                    "review_completeness": sum(r.status == "completed" for r in reviews) / 4,
                    "limitations_segments": [
                        *outcome.result.limitations_segments,
                        TextSegment(type="text", text="피드백 최종 반영을 완료하지 못했습니다."),
                    ],
                }
            )
            result = type(result).model_validate(result.model_dump(mode="json"))
            await run_in_thread(self._save_final_result, result)
            outcome.result = result
        outcome.status = "completed"
        await self.save("completed", outcome.result)
        await self.event(
            "final",
            "completed",
            {"feedback_rounds": 1, "review_completeness": outcome.result.review_completeness},
        )
        return outcome

    def _save_final_result(self, result):
        with connect(self.scope.path) as db:
            db.execute(
                "UPDATE agentic_reports SET result_json=?,phase='final' WHERE report_id=?",
                (result.model_dump_json(), result.report_id),
            )

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
        await run_in_thread(_save, self.scope, self.state, status, result_model)

    async def _model(self, role, messages, settings, definitions=None, receipt=None):
        if role != "advisor":
            messages = await run_in_thread(encode_messages, self.scope, messages)
        started = monotonic()
        receipt = receipt if receipt is not None else {}
        if self.recorder:
            receipt["_record_raw"] = True
        value, failure = None, None
        used = self.budget.used
        requested = min(
            settings.max_tokens or 16000, 4000 if role not in {"decision", "advisor"} else 16000
        )
        self.budget.schema_chars_by_role[role] = (
            len(canonical_json(definitions)) if definitions else 0
        )
        final = self.state.get("phase") == "final"
        reserved = await self.budget.claim_output(requested, role=role, final=final)
        try:
            value, receipt = await self.model_call(
                role, messages, replace(settings, max_tokens=reserved), definitions, receipt
            )
            return value, receipt
        except BaseException as exc:
            failure = exc
            raise
        finally:
            await self.budget.release_output(reserved, role=role, final=final)
            if self.recorder and (value is not None or self.budget.used > used):
                await self.recorder.record(
                    role,
                    messages,
                    value,
                    receipt,
                    int((monotonic() - started) * 1000),
                    error=failure,
                )

    async def model_call(self, role, messages, settings, definitions=None, receipt=None):
        receipt = receipt if receipt is not None else {}
        started = monotonic()
        remaining = self.budget.output_limit - self.budget.totals()[1]
        if remaining <= 0:
            raise BudgetExceeded()
        settings = replace(
            settings,
            max_tokens=min(settings.max_tokens or 16000, remaining),
            timeout_seconds=max(0.01, self.budget.seconds_limit - self.budget.active_seconds),
        )
        generator = (
            self.generate
            if role == "decision"
            else self.advisor_generate
            if role == "advisor"
            else self.evaluator_generate
        )
        if generator is None:
            with llm_scope(self.budget, role, final=self.state.get("phase") == "final"):
                if definitions is not None:
                    value = await complete_tools(messages, definitions, settings, receipt=receipt)
                else:
                    value = await complete_json(
                        messages[0]["content"], messages[1]["content"], settings, receipt=receipt
                    )
        else:
            attempt = await self.budget.reserve(
                role,
                final=self.state.get("phase") == "final",
                input_chars=len(canonical_json(messages)),
            )
            status = "error"
            try:
                value = generator(messages, definitions, settings, receipt)
                if hasattr(value, "__await__"):
                    value = await value
                status = "ok"
            finally:
                if receipt.get("replay_elapsed_ms"):
                    self.budget.active_base += max(
                        0, receipt["replay_elapsed_ms"] / 1000 - (monotonic() - started)
                    )
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
        return await advisor.ask_advisor(self, input)

    async def ask_user(self, input):
        return await questions.ask_user(self, input)

    async def submit_l(self, input):
        if self.state["L_closed"]:
            return ToolReply(
                status="ok",
                data=SubmitLResult(
                    submitted_count=len(self.state["L_records"]),
                    remaining_count=0,
                    closed=True,
                    ignored=[
                        raw["industry_code"]
                        for raw in input.L_records
                        if raw.get("industry_code") in self.state["L_records"]
                    ],
                ),
            )
        submitted = self.state["L_records"]
        accepted, ignored, rejected, warnings, batch = [], [], [], [], []
        for raw in input.L_records:
            code = raw.get("industry_code", "미지정")
            if not isinstance(code, str):
                code = "미지정"
            if code in submitted or code in accepted:
                ignored.append(code)
                continue
            try:
                record, note_dropped = await run_in_thread(
                    build_record, self.scope, raw, self.base_id, self.base_rows
                )
                await run_in_thread(
                    validate_l_records,
                    self.scope,
                    [record],
                    self.base_id,
                    self.base_rows,
                    self.state["advisor_unavailable"],
                )
                batch.append(record)
                accepted.append(record.industry_code)
                if note_dropped:
                    warnings.append(
                        code + ": 숫자 note를 버리고 검증한 근거 설명으로 대체했습니다."
                    )
            except ValidationError as exc:
                rejected.append(
                    {
                        "industry_code": str(code),
                        "reason": validation_message(LInput, exc),
                        "correction": "업종·factors 또는 neutral/fact_ids만 제출하세요.",
                    }
                )
            except (ValueError, ReportInvalid) as exc:
                rejected.append(
                    {
                        "industry_code": str(code),
                        "reason": str(exc)[:400],
                        "correction": "도구가 반환한 같은 업종의 새 근거 별칭만 제출하세요.",
                    }
                )
        try:
            combined = {**submitted, **{r.industry_code: r.model_dump(mode="json") for r in batch}}
            close = input.finish or len(combined) == len(INDUSTRIES)
            score_id = None
            scorecard = None
            if close:
                records = complete_l_records(
                    [LRecord.model_validate(r) for r in combined.values()],
                    self.base_id,
                    self.base_rows,
                    self.state["advisor_unavailable"],
                )
                score_id, rows = await run_in_thread(
                    recompute_l_scores,
                    self.scope,
                    records,
                    self.base_id,
                    self.base_rows,
                    self.tools.shared.regulation,
                )
                scorecard = ScorecardResult(
                    summaries=[score_summary(r) for r in rank_candidates(rows)[:5]]
                )
                missing = len(INDUSTRIES) - len(combined)
                if missing:
                    self.state["limitations"].append(f"L 판단 미제출 업종 수: {missing}")
                combined = {r.industry_code: r.model_dump(mode="json") for r in records}
        except ReportInvalid as exc:
            return error("L_EVIDENCE_INVALID", str(exc))
        self.state["L_records"] = combined
        self.state["L_closed"] = close
        if close:
            self.state["phase"] = "draft"
            self.state["L_score_snapshot_id"] = score_id
        await self.save()
        return ToolReply(
            status="ok",
            data=SubmitLResult(
                submitted_count=len(submitted) + len(batch),
                remaining_count=0 if close else len(INDUSTRIES) - len(combined),
                closed=close,
                score_snapshot_id=score_id,
                scorecard=scorecard,
                accepted=accepted,
                ignored=ignored,
                rejected=rejected,
                unsubmitted=[
                    code for code in INDUSTRIES if code not in submitted and code not in accepted
                ],
            ),
            warnings=warnings,
        )

    async def submit_draft(self, input):
        if not self.state["L_closed"]:
            return error("L_STAGE_REQUIRED", "전체 업종 L 판단을 먼저 확정하세요.")
        phase = self.state.get("phase", "draft")
        if input.phase != phase or (phase == "draft" and input.review_resolutions):
            return error("INVALID_ARGUMENT", "현재 제출 단계와 피드백 형식이 다릅니다.")
        try:
            self.done = await run_in_thread(
                lambda: finalize(
                    self.scope,
                    input.report,
                    self.base_id,
                    self.base_rows,
                    l_records=[LRecord.model_validate(r) for r in self.state["L_records"].values()],
                    advisor_unavailable=self.state["advisor_unavailable"],
                    regulation_result=self.tools.shared.regulation,
                    limitations=self.state["limitations"],
                    reviews=[EvaluatorReview.model_validate(r) for r in self.state["reviews"]]
                    if phase == "final"
                    else None,
                    resolutions=input.review_resolutions,
                )
            )
            self.state["last_draft"] = input.report.model_dump(mode="json")
        except ReportInvalid as exc:
            return error(
                "L_EVIDENCE_INVALID",
                str(exc),
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
        missing = len(INDUSTRIES) - len(self.state["L_records"])
        records = complete_l_records(
            [LRecord.model_validate(r) for r in self.state["L_records"].values()],
            self.base_id,
            self.base_rows,
            self.state["advisor_unavailable"],
        )
        self.state["L_records"] = {r.industry_code: r.model_dump(mode="json") for r in records}
        self.state["L_closed"] = True
        if missing:
            self.state["limitations"].append(f"L 판단 미제출 업종 수: {missing}")
        self.state["limitations"].append(reason)
        self.state["limitations"].append(
            "미제출 L 판단은 unknown으로 남기고 이미 확인한 판단은 보존했습니다"
        )
        proposal = ReportProposal.model_validate(self.state.get("last_draft", {}))
        if not proposal.summary_segments:
            proposal = proposal.model_copy(
                update={
                    "summary_segments": [
                        TextSegment(
                            type="text",
                            text=(
                                "확인된 코드 점수의 하한과 자료 충족도를 기준으로 "
                                "검토 후보를 정렬했습니다."
                            ),
                        )
                    ]
                }
            )
        self.done = await run_in_thread(
            lambda: finalize(
                self.scope,
                proposal,
                self.base_id,
                self.base_rows,
                l_records=[LRecord.model_validate(r) for r in self.state["L_records"].values()],
                limitations=self.state["limitations"],
                advisor_unavailable=self.state["advisor_unavailable"],
                regulation_result=self.tools.shared.regulation,
            )
        )
        await self.save("draft_available", self.done)
        return LoopOutcome("draft_available", result=self.done, budget=self.budget.snapshot())

    def model_messages(self):
        return deepcopy(self.state["messages"])

    def definitions(self):
        blocked = not self.state["allow_questions"] or self.state.get("phase") == "final"
        definitions = [
            d
            for d in self.tools.definitions()
            if not (blocked and d["function"]["name"] == "ask_user")
            and not (self.state["L_closed"] and d["function"]["name"] == "submit_l")
            and not (not self.state["L_closed"] and d["function"]["name"] == "submit_draft")
        ]
        for definition in definitions:
            function = definition["function"]
            if function["name"] == "ask_user":
                fields = function["parameters"]["properties"]["questions"]["items"]["properties"][
                    "field"
                ]
                fields["enum"] = [
                    field
                    for field in fields["enum"]
                    if field not in self.state["confirmed_question_fields"]
                ]
        return definitions

    async def compact_reply(self, reply, name, arguments):
        body = reply.model_dump(mode="json")
        data = body.get("data") or {}
        space_fits = name == "get_facts" and any(
            fact.get("metric") == "space_fit" for fact in data.get("facts", [])
        )
        if space_fits:
            data["facts"] = [
                {
                    key: value
                    for key, value in fact.items()
                    if key in {"fact_id", "industry_code", "value", "status", "citable"}
                }
                if fact.get("metric") == "space_fit"
                else fact
                for fact in data["facts"]
            ]
            data["provenance_refs"] = []
            data["source"] = "industry_profile"
            data["metric"] = "space_fit"
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
            if space_fits and field == "facts":
                continue
            while entries and len(canonical_json(body)) > 4000:
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
        return await run_in_thread(
            encode, self.scope, {"tool_call_id": self.tools.last_call_id} | body
        )

    async def run(self):
        while True:
            try:
                definitions = self.definitions()
                self.budget.schema_chars = len(canonical_json(definitions))
                if (
                    self.budget.totals()[1] >= self.budget.output_limit
                    or self.budget.active_seconds >= self.budget.seconds_limit
                ):
                    raise BudgetExceeded()
                async with asyncio.timeout(
                    max(0.01, self.budget.seconds_limit - self.budget.active_seconds)
                ):
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
                await self.event("decision", "completed", {"tool": name, "status": reply.status})
                self.state["messages"].append(
                    {"role": "tool", "tool_call_id": call.id, "content": canonical_json(content)}
                )
                self.state["no_progress"] = (
                    self.state.get("no_progress", 0) + 1 if reply.duplicate or reply.error else 0
                )
                if self.done:
                    await self.save("draft_available", self.done)
                    return LoopOutcome(
                        "draft_available", result=self.done, budget=self.budget.snapshot()
                    )
                if self.waiting:
                    await self.event(
                        "question",
                        "waiting",
                        {"question_session_id": self.waiting.question_session_id},
                    )
                    await self.save("waiting_for_input")
                    return self.waiting
                if not self.budget.measurement and self.state["no_progress"] >= 3:
                    return await self.fallback(
                        "새 정보가 없는 반복·오류 호출이 연속 세 번 발생했습니다."
                    )
                await self.save()
            except (BudgetExceeded, TimeoutError):
                return await self.fallback(
                    "호출·시간·토큰 예산 상한에 도달해 코드 점수로 마무리했습니다."
                )
            except LLMResponseError as exc:
                if exc.code in {"LLM_TIMEOUT", "LLM_CONNECTION_ERROR"} and not self.state.get(
                    "model_retried"
                ):
                    self.state["model_retried"] = True
                    continue
                return await self.fallback("모델 응답을 완료하지 못해 코드 점수로 마무리했습니다.")
            except LLMHTTPError as exc:
                if exc.diagnostics.get("http_status") in {
                    429,
                    500,
                    502,
                    503,
                    504,
                } and not self.state.get("model_retried"):
                    self.state["model_retried"] = True
                    continue
                return await self.fallback(
                    "모델 서비스를 확인하지 못해 코드 점수로 마무리했습니다."
                )

    @staticmethod
    async def validate_resume(scope, answers):
        return await questions.validate_resume(scope, answers)

    @classmethod
    async def resume(cls, scope, site, answers, *, resume_state=None, **kwargs):
        return await questions.resume(
            cls, scope, site, answers, resume_state=resume_state, **kwargs
        )

"""요청별 읽기 도구 권한·횟수·중복·감사 기록의 공통 실행 경계입니다."""

import asyncio
import uuid
from collections import Counter
from dataclasses import dataclass, field

from pydantic import TypeAdapter, ValidationError

from app.agents.map_analysis.client import MapApiError
from app.canonical import canonical_hash, canonical_json
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect
from app.storage.scrub import env_secrets, scrub

from .aliases import decode, decode_report
from .contracts import TOOL_INPUTS, Actor, ToolReply, tool_definitions
from .map_regulation import check_regulation, map_search
from .read_tools import InvalidCursor, get_facts, get_scorecard
from .sql_tool import error, query_raw

READS = {"get_scorecard", "get_facts", "query_raw", "map_search", "check_regulation"}
EVALUATORS = {"examiner", "founder", "customer", "landlord_advocate"}
EVALUATOR_READS = {"get_scorecard", "get_facts", "query_raw"}


def validation_message(model, failure):
    """오류 입력·사용자 키는 제외하고 공개 필드 경로·유형·상한만 돌려줍니다."""
    fields = set()

    def collect(schema):
        if isinstance(schema, dict):
            fields.update(schema.get("properties", {}))
            for value in schema.values():
                collect(value)
        elif isinstance(schema, list):
            for value in schema:
                collect(value)

    collect(model.model_json_schema())
    issues = []
    for detail in failure.errors(include_input=False, include_url=False)[:3]:
        path = []
        freeform = detail["type"] == "extra_forbidden"
        for part in detail["loc"]:
            path.append(
                str(part) if not freeform and (isinstance(part, int) or part in fields) else "?"
            )
            freeform = freeform or part == "params"
        context = detail.get("ctx") or {}
        upper = next((context[key] for key in ("max_length", "le", "lt") if key in context), None)
        maximum = f" max={upper}" if type(upper) in (int, float) else ""
        rule = " " + str(context["error"])[:120] if detail["type"] == "value_error" else ""
        issues.append(".".join(path)[:80] + " " + detail["type"][:40] + maximum + rule)
    return ("입력 오류: " + "; ".join(issues))[:400]


@dataclass
class SharedTools:
    measurement: bool = False
    calls: Counter = field(default_factory=Counter)
    seen: set = field(default_factory=set)
    replies: dict = field(default_factory=dict)
    map_cache: dict = field(default_factory=dict)
    map_keys: set = field(default_factory=set)
    map_http: int = 0
    map_client: object = None
    regulation_lookup: object = None
    regulation_scan: object = None
    regulation: object = None
    observation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _audit(scope, call_id, actor, name, arguments, reply):
    with connect(scope.path) as db:
        db.execute(
            "INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?,?,?)",
            (
                call_id,
                scope.request_id,
                scope.snapshot_id,
                scope.run_id,
                actor,
                name,
                canonical_json(scrub(arguments, env_secrets())),
                reply.model_dump_json(),
                utc_now_iso(),
            ),
        )


def previous_reply(scope, actor, name, signature):
    with connect(scope.path) as db:
        rows = db.execute(
            "SELECT input_json,reply_json FROM tool_calls WHERE request_id=? AND "
            "snapshot_id=? AND actor=? AND tool_name=? ORDER BY rowid",
            (scope.request_id, scope.snapshot_id, actor, name),
        ).fetchall()
    for arguments, reply in rows:
        try:
            validated = TOOL_INPUTS[name].model_validate_json(arguments)
        except ValidationError:
            continue
        if (
            canonical_hash([actor, name, validated.model_dump(mode="json"), scope.snapshot_id])
            == signature
        ):
            return ToolReply.model_validate_json(reply)
    return None


def space_revision(scope):
    with connect(scope.path) as db:
        rows = db.execute(
            "SELECT fact_id FROM space_fit_current WHERE request_id=? AND snapshot_id=? "
            "ORDER BY industry_code",
            (scope.request_id, scope.snapshot_id),
        ).fetchall()
    return canonical_hash([row[0] for row in rows])


class ToolExecutor:
    def __init__(
        self, scope, site, *, actor="decision", shared=None, advisor_fact_ids=(), handlers=None
    ):
        self.scope, self.site = scope, site
        self.actor = TypeAdapter(Actor).validate_python(actor)
        self.shared = shared or SharedTools()
        self.advisor_fact_ids = set(advisor_fact_ids)
        self.handlers = handlers or {}
        self.last_call_id = None

    def for_actor(self, actor, *, advisor_fact_ids=()):
        return ToolExecutor(
            self.scope,
            self.site,
            actor=actor,
            shared=self.shared,
            advisor_fact_ids=advisor_fact_ids,
            handlers=self.handlers,
        )

    def definitions(self):
        permitted = (
            EVALUATOR_READS | {"submit_review"}
            if self.actor in EVALUATORS
            else {"get_facts"}
            if self.actor == "advisor"
            else set(TOOL_INPUTS) - {"submit_review"}
        )
        if self.actor == "examiner":
            permitted = permitted - {"query_raw"}
        return [d for d in tool_definitions() if d["function"]["name"] in permitted]

    def _reserve(self, name, args, *, duplicate=False):
        allowed = {d["function"]["name"] for d in self.definitions()}
        calls = self.shared.calls
        evaluator = self.actor in EVALUATORS
        enforce = evaluator or not self.shared.measurement
        total_actor = 20 if self.actor == "decision" else 1 if self.actor == "advisor" else 3
        maxima = {"get_scorecard": 6, "get_facts": 8, "query_raw": 4, "check_regulation": 1}
        if evaluator:
            maxima.update(get_scorecard=3, get_facts=3, query_raw=3, submit_review=1)
        if self.actor == "advisor":
            maxima["get_facts"] = 1
        if name not in {"submit_review", "submit_draft", "submit_l"}:
            if enforce and (calls["total"] >= 40 or calls[(self.actor, "total")] >= total_actor):
                return error("BUDGET_EXCEEDED", "도구 호출 상한을 초과했습니다.")
            calls["total"] += 1
            calls[(self.actor, "total")] += 1
        if name not in allowed:
            return error("INVALID_ARGUMENT", "현재 actor에 허용되지 않은 도구입니다.")
        if name == "submit_review":
            return None
        if (
            enforce
            and (not duplicate or name == "submit_review")
            and calls[(self.actor, name)] >= maxima.get(name, 20)
        ):
            return error("BUDGET_EXCEEDED", "도구별 호출 상한을 초과했습니다.")
        calls[(self.actor, name)] += 1
        return None

    async def execute(self, name, arguments):
        input, signature = None, None
        current_space = False
        invalid_message = "도구 입력 형식이나 상한이 잘못되었습니다."
        alias_warnings = []
        if name in TOOL_INPUTS:
            try:
                if name == "submit_draft":
                    arguments, alias_warnings = await run_in_thread(
                        decode_report, self.scope, arguments
                    )
                elif name != "submit_l":
                    arguments = await run_in_thread(decode, self.scope, arguments)
                input = TOOL_INPUTS[name].model_validate(arguments)
            except ValidationError as exc:
                invalid_message = validation_message(TOOL_INPUTS[name], exc)
            except ValueError as exc:
                invalid_message = str(exc)
            else:
                current_space = (
                    name == "get_facts"
                    and input.source == "industry_profile"
                    and input.metrics == ["space_fit"]
                    and not input.fact_ids
                )
                identity = [self.actor, name, input.model_dump(mode="json"), self.scope.snapshot_id]
                if current_space:
                    identity.append(await run_in_thread(space_revision, self.scope))
                try:
                    signature = canonical_hash(identity)
                except ValueError:
                    input = None
        duplicate = (
            name not in {"submit_l", "submit_review"}
            and signature is not None
            and signature in self.shared.seen
        )
        rejected = self._reserve(name, arguments, duplicate=duplicate)
        call_id = "tc_" + str(uuid.uuid4())
        if rejected is not None:
            reply = rejected
        elif input is None:
            reply = error("INVALID_ARGUMENT", invalid_message)
        elif duplicate:
            original = self.shared.replies.get(signature)
            if original is None:
                # 감사 입력에는 포인터 버전이 없으므로 재개한 공간 조회만 현재 DB에서 복구합니다.
                original = (
                    await self._execute(name, input)
                    if current_space
                    else await run_in_thread(
                        previous_reply, self.scope, self.actor, name, signature
                    )
                )
                if current_space:
                    self.shared.replies[signature] = original.model_copy(deep=True)
            reply = (
                original.model_copy(
                    deep=True,
                    update={
                        "duplicate": True,
                        "warnings": [*original.warnings, "이미 조회한 결과"],
                    },
                )
                if original is not None
                else error("SOURCE_UNAVAILABLE", "이전 도구 응답 기록 없음")
            )
        else:
            reply = await self._execute(name, input)
            if name not in {"submit_l", "submit_review"} and (
                not reply.error
                or reply.error.code
                not in {
                    "MAP_UNAVAILABLE",
                    "SQL_TIMEOUT",
                    "TIMEOUT",
                    "SOURCE_UNAVAILABLE",
                }
            ):
                self.shared.seen.add(signature)
                self.shared.replies[signature] = reply.model_copy(deep=True)
        if alias_warnings:
            reply.warnings.extend(alias_warnings)
        await run_in_thread(_audit, self.scope, call_id, self.actor, name, arguments, reply)
        self.last_call_id = call_id
        return reply

    async def _execute(self, name, input):
        try:
            if name in self.handlers:
                return await self.handlers[name](input)
            if name == "query_raw":
                return await query_raw(self.scope, input.sql, input.params, input.max_rows)
            if name in {"get_facts", "get_scorecard"}:
                if self.actor == "advisor" and (
                    not input.fact_ids or not set(input.fact_ids) <= self.advisor_fact_ids
                ):
                    return error(
                        "INVALID_ARGUMENT", "보조 에이전트는 전달받은 fact_id만 조회할 수 있습니다."
                    )
                result = await (get_facts if name == "get_facts" else get_scorecard)(
                    self.scope, input
                )
                if isinstance(result, ToolReply):
                    return result
                return ToolReply(status="ok", data=result)
            if name == "map_search":
                key = canonical_hash(input.model_dump(mode="json"))
                async with self.shared.observation_lock:
                    if key not in self.shared.map_cache:
                        if (
                            not self.shared.measurement
                            and key not in self.shared.map_keys
                            and len(self.shared.map_keys) >= 6
                        ):
                            return error("BUDGET_EXCEEDED", "서로 다른 지도 검색 6개 상한입니다.")
                        self.shared.map_keys.add(key)
                        self.shared.map_cache[key] = await map_search(
                            self.scope, self.site, input, self.shared
                        )
                    return self.shared.map_cache[key]
            if name == "check_regulation":
                async with self.shared.observation_lock:
                    result = await check_regulation(self.scope, self.site, self.shared)
                    return ToolReply(
                        status="partial"
                        if result.status != "ok" or not result.contains_verified
                        else "ok",
                        data=result,
                        fact_ids=result.fact_ids,
                        warnings=result.limitations,
                    )
            return error("SOURCE_UNAVAILABLE", "이 도구는 후속 PR 런타임에서 연결됩니다.")
        except MapApiError:
            return error("MAP_UNAVAILABLE", "지도 API 자료를 확인하지 못했습니다.")
        except TimeoutError:
            return error("TIMEOUT", "도구 실행 시간 상한을 초과했습니다.")
        except InvalidCursor:
            return error("INVALID_ARGUMENT", "커서 또는 조회 범위가 잘못되었습니다.")

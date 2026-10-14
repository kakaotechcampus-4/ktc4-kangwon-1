"""요청별 읽기 도구 권한·횟수·중복·감사 기록의 공통 실행 경계입니다."""

import asyncio
import uuid
from collections import Counter
from dataclasses import dataclass, field

from pydantic import TypeAdapter, ValidationError

from app.agents.map_analysis.client import MapApiError
from app.db.connection import connect
from app.storage.raw import _hash, _json, _now, _write

from .contracts import TOOL_INPUTS, Actor, ToolReply, tool_definitions
from .observations import check_regulation, map_search
from .raw_query import error, query_raw
from .reads import InvalidCursor, get_facts, get_scorecard

READS = {"get_scorecard", "get_facts", "query_raw", "map_search", "check_regulation"}
EVALUATORS = {"examiner", "founder", "customer", "landlord_advocate"}


@dataclass
class SharedTools:
    calls: Counter = field(default_factory=Counter)
    seen: set = field(default_factory=set)
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
                _json(arguments),
                reply.model_dump_json(),
                _now(),
            ),
        )


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
            READS
            if self.actor in EVALUATORS
            else {"get_facts"}
            if self.actor == "advisor"
            else set(TOOL_INPUTS) - {"submit_review"}
        )
        return [d for d in tool_definitions() if d["function"]["name"] in permitted]

    def _reserve(self, name, args):
        allowed = {d["function"]["name"] for d in self.definitions()}
        calls = self.shared.calls
        total_actor = 20 if self.actor == "decision" else 1 if self.actor == "advisor" else 4
        maxima = {"get_scorecard": 6, "get_facts": 8, "query_raw": 4, "check_regulation": 1}
        if self.actor in EVALUATORS:
            maxima.update(get_scorecard=2, get_facts=3, query_raw=2)
        if self.actor == "advisor":
            maxima["get_facts"] = 1
        if calls["total"] >= 40 or calls[(self.actor, "total")] >= total_actor:
            return error("BUDGET_EXCEEDED", "도구 호출 상한을 초과했습니다.")
        calls["total"] += 1
        calls[(self.actor, "total")] += 1
        if name not in allowed:
            return error("INVALID_ARGUMENT", "현재 actor에 허용되지 않은 도구입니다.")
        if calls[(self.actor, name)] >= maxima.get(name, 20):
            return error("BUDGET_EXCEEDED", "도구별 호출 상한을 초과했습니다.")
        calls[(self.actor, name)] += 1
        return None

    async def execute(self, name, arguments):
        rejected = self._reserve(name, arguments)
        call_id = "tc_" + str(uuid.uuid4())
        if rejected is not None:
            reply = rejected
        else:
            try:
                input = TOOL_INPUTS[name].model_validate(arguments)
            except ValidationError:
                reply = error("INVALID_ARGUMENT", "도구 입력 형식이나 상한이 잘못되었습니다.")
            else:
                signature = _hash(
                    [self.actor, name, input.model_dump(mode="json"), self.scope.snapshot_id]
                )
                if signature in self.shared.seen:
                    reply = error("DUPLICATE_CALL", "같은 스냅샷의 동일 조회를 반복할 수 없습니다.")
                else:
                    self.shared.seen.add(signature)
                    reply = await self._execute(name, input)
        await _write(_audit, self.scope, call_id, self.actor, name, arguments, reply)
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
                key = _hash(input.model_dump(mode="json"))
                async with self.shared.observation_lock:
                    if key not in self.shared.map_cache:
                        if key not in self.shared.map_keys and len(self.shared.map_keys) >= 6:
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

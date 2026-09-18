"""주소 처리와 분석 에이전트 실행 흐름을 연결합니다.

주소 → 좌표 → 분석 에이전트 병렬 실행 → 최종판단까지가 한 흐름입니다.
세 분석기는 같은 요청 설정을 명시적으로 전달받습니다.
한 에이전트가 실패해도 나머지는 계속 돕니다.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import replace
from functools import partial
from importlib.resources import files
from typing import Any

from openai.types.chat import ChatCompletionMessage
from pydantic import ValidationError

from app.agents import business_lifecycle, commercial_area, decision, floating_population
from app.agents.commercial_area.config import Settings
from app.agents.decision.agent import GenerateDecision
from app.agents.floating_population import llm as floating_llm
from app.config import AddressSettings
from app.schemas import (
    AGENT_IDS,
    AgentAnalysis,
    AgentError,
    AgentId,
    AnalysisTask,
    DecisionRequest,
    DecisionResult,
    Site,
)
from app.services.settings import ExecutionSettings, validate_timeout

from . import llm, tools

AnalysisAgent = Callable[[AnalysisTask], Awaitable[AgentAnalysis]]
AgentRegistry = dict[AgentId, AnalysisAgent]
GenerateAction = Callable[[list[Any], list[Any]], Awaitable[ChatCompletionMessage]]

__all__ = [
    "AgentRegistry",
    "AnalysisAgent",
    "build_react_agents",
    "default_agents",
    "prepare_task",
    "run_agents",
    "run_analysis",
    "run_react",
]


async def prepare_task(
    address: str,
    *,
    resolve: Callable[[str], Awaitable[Site]],
    request_id: str | None = None,
) -> AnalysisTask:
    """주소 변환 도구를 호출하고 공통 입력을 검증합니다."""
    cleaned = address.strip()
    if not cleaned:
        raise ValueError("주소가 비어 있습니다.")
    resolved = Site.model_validate(await resolve(cleaned))
    return AnalysisTask(
        request_id=uuid.uuid4().hex if request_id is None else request_id,
        site=resolved,
    )


def default_agents(settings: Settings | None = None) -> AgentRegistry:
    """기존 상권 설정 인자를 유지하면서 공통 3종 등록을 재사용합니다."""
    execution = ExecutionSettings.from_env()
    return build_react_agents(replace(execution, commercial=settings) if settings else execution)


def build_react_agents(settings: ExecutionSettings | None = None) -> AgentRegistry:
    """등록 시 외부 호출 없이 세 실제 분석기를 같은 설정 묶음에 연결합니다."""
    settings = settings or ExecutionSettings.from_env()

    async def guarded(
        task: AnalysisTask, *, agent_id: AgentId, analyze: AnalysisAgent
    ) -> AgentAnalysis:
        if (task.site.latitude, task.site.longitude) == (0, 0):
            return AgentAnalysis(
                request_id=task.request_id,
                agent_id=agent_id,
                status="error",
                error=AgentError(
                    code="INVALID_ANALYSIS_COORDINATES",
                    message="목업 좌표 (0, 0)는 실제 분석에 사용할 수 없습니다.",
                ),
            )
        return await analyze(task)

    return {
        "floating_population": partial(
            guarded,
            agent_id="floating_population",
            analyze=partial(
                floating_population.analyze,
                settings=settings.floating,
                select=partial(floating_llm.select_blocks, settings=settings.floating_llm),
            ),
        ),
        "business_lifecycle": partial(
            guarded,
            agent_id="business_lifecycle",
            analyze=partial(
                business_lifecycle.analyze,
                settings=settings.lifecycle,
                llm_settings=settings.lifecycle_llm,
            ),
        ),
        "commercial_area": partial(
            guarded,
            agent_id="commercial_area",
            analyze=partial(commercial_area.analyze, settings=settings.commercial),
        ),
    }


def _crash_to_analysis(task: AnalysisTask, agent_id: AgentId, _exc: BaseException) -> AgentAnalysis:
    return AgentAnalysis(
        request_id=task.request_id,
        agent_id=agent_id,
        status="error",
        error=AgentError(
            code="AGENT_CRASHED",
            message="분석 에이전트 실행에 실패했습니다.",
        ),
    )


async def run_agents(
    task: AnalysisTask,
    agents: AgentRegistry,
    *,
    on_analysis_completed: Callable[[AgentAnalysis], Awaitable[None]] | None = None,
    agent_timeout: float = 180.0,
) -> list[AgentAnalysis]:
    """등록된 분석 에이전트를 동시에 실행합니다."""
    if not agents:
        raise ValueError("실행할 분석 에이전트가 없습니다.")
    validate_timeout(agent_timeout)

    async def run_one(agent_id: AgentId) -> AgentAnalysis:
        try:
            async with asyncio.timeout(agent_timeout) as deadline:
                result = await agents[agent_id](task)
        except ValidationError:
            raise
        except Exception as exc:
            result = _crash_to_analysis(task, agent_id, exc)
            if isinstance(exc, TimeoutError) and deadline.expired():
                result.error = AgentError(
                    code="AGENT_TIMEOUT", message="분석 제한시간이 초과됐습니다."
                )
        # 계약 오류와 저장 실패는 분석 함수의 실행 오류로 바꾸지 않습니다.
        analysis = AgentAnalysis.model_validate(result)
        if analysis.agent_id != agent_id or analysis.request_id != task.request_id:
            raise ValueError("분석 결과의 요청 ID 또는 에이전트 ID가 일치하지 않습니다.")
        if on_analysis_completed is not None:
            await on_analysis_completed(analysis)
        return analysis

    results = await asyncio.gather(*(run_one(key) for key in agents), return_exceptions=True)
    analyses = []
    for result in results:
        if isinstance(result, BaseException):
            raise result
        analyses.append(result)
    return analyses


async def run_analysis(
    address: str,
    *,
    site: Site | None = None,
    settings: Settings | None = None,
    agents: AgentRegistry | None = None,
    generate: GenerateDecision | None = None,
    request_id: str | None = None,
) -> DecisionResult:
    """주소 하나로 최종판단 결과까지 만듭니다.

    `site`를 주면 좌표 변환을 건너뜁니다. `agents`와 `generate`는 시험용
    대역을 넣기 위한 자리입니다.
    """
    settings = settings or Settings.from_env()

    async def resolve(address: str) -> Site:
        return (
            site
            if site is not None
            else await tools.resolve_site(
                address,
                AddressSettings(
                    api_key=settings.geocoding_api_key, timeout=settings.request_timeout_s
                ),
            )
        )

    task = await prepare_task(
        address,
        resolve=resolve,
        request_id=request_id,
    )
    analyses = await run_agents(task, agents or default_agents(settings))
    request = DecisionRequest(
        request_id=task.request_id,
        address=task.site.input_address,
        analyses=analyses,
    )
    return await decision.analyze(request, generate=generate)


async def run_react(
    address: str,
    *,
    resolve: Callable[[str], Awaitable[Site]],
    agents: AgentRegistry,
    generate_action: GenerateAction | None = None,
    generate: GenerateDecision | None = None,
    request_id: str | None = None,
    on_task_prepared: Callable[[AnalysisTask], Awaitable[None]] | None = None,
    on_analysis_completed: Callable[[AgentAnalysis], Awaitable[None]] | None = None,
    agent_timeout: float = 180.0,
) -> DecisionResult:
    """도구 호출과 관찰을 반복합니다. 주소 도구와 세 분석기는 명시적으로 연결합니다."""
    address = address.strip()
    if not address:
        raise ValueError("주소가 비어 있습니다.")
    if set(agents) != set(AGENT_IDS):
        raise ValueError("세 분석 에이전트를 모두 연결해 주세요.")
    # 요청 ID를 모델이 만들거나 변경하지 못하게 먼저 검증합니다.
    request_id = uuid.uuid4().hex if request_id is None else request_id
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("요청 ID가 비어 있습니다.")
    messages: list[Any] = [
        {"role": "system", "content": files(__package__).joinpath("prompt.md").read_text("utf-8")},
        {"role": "user", "content": json.dumps({"address": address}, ensure_ascii=False)},
    ]
    task = None
    analyses = None
    choose = generate_action or llm.generate_action
    for _ in range(6):
        produced = await choose(messages, tools.TOOL_DEFINITIONS)
        message = ChatCompletionMessage.model_validate(produced)
        if message.refusal or not message.tool_calls or len(message.tool_calls) != 1:
            raise RuntimeError("모델은 한 번에 하나의 도구를 호출해야 합니다.")
        call = message.tool_calls[0]
        if call.type != "function":
            raise RuntimeError("지원하지 않는 도구 호출 형식입니다.")
        messages.append(
            message.model_dump(
                include={"role", "content", "tool_calls"},
                exclude_none=True,
            )
        )
        try:
            arguments = json.loads(call.function.arguments)
        except (ValueError, TypeError):
            arguments = None
        name = call.function.name
        expected = (
            "prepare_address"
            if task is None
            else ("run_analyses" if analyses is None else "make_decision")
        )
        observation: dict[str, Any]
        if arguments != {} or name != expected:
            observation = {"status": "error", "message": f"빈 인자로 {expected}를 호출하세요."}
        elif name == "prepare_address":
            task = await prepare_task(address, resolve=resolve, request_id=request_id)
            if on_task_prepared is not None:
                await on_task_prepared(task)
            observation = {"status": "ok", "task": task.model_dump(mode="json")}
        elif name == "run_analyses":
            assert task is not None
            analyses = await run_agents(
                task,
                agents,
                on_analysis_completed=on_analysis_completed,
                agent_timeout=agent_timeout,
            )
            observation = {
                "status": "ok",
                "analyses": [
                    item.model_dump(mode="json", include={"agent_id", "status", "scope"})
                    for item in analyses
                ],
            }
        else:
            assert task is not None and analyses is not None
            return await decision.analyze(
                DecisionRequest(
                    request_id=task.request_id,
                    address=task.site.input_address,
                    analyses=analyses,
                ),
                generate=generate,
            )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(observation, ensure_ascii=False, allow_nan=False),
            }
        )
    raise RuntimeError("오케스트레이터의 최대 모델 호출 횟수 6회를 초과했습니다.")

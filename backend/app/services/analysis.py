"""오케스트레이터 실행 중 검증된 결과를 SQLite에 저장합니다."""

import asyncio
import sqlite3
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from functools import partial
from pathlib import Path
from typing import Any

from app.address import resolve_site
from app.agents.decision import agent as decision
from app.agents.decision.agent import GenerateDecision
from app.agents.orchestration import llm
from app.agents.orchestration.supplement import OnSupplement, validate_tools
from app.agents.orchestration.tools import SupplementTool
from app.agents.orchestration.workflow import (
    AgentRegistry,
    GenerateAction,
    build_react_agents,
    run_react,
)
from app.db import repository
from app.db.connection import initialize
from app.schemas import (
    AGENT_IDS,
    DEFAULT_RADIUS_M,
    AgentAnalysis,
    AgentError,
    AnalysisTask,
    DecisionResult,
    Site,
    SupplementEvent,
    validate_radius,
)
from app.services.settings import ExecutionSettings, validate_timeout


async def _settle[T](operation: Coroutine[Any, Any, T]) -> T:
    """DB 스레드는 강제 중단할 수 없어 쓰기 결말 확인 후 취소를 전달합니다."""
    task = asyncio.create_task(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


async def execute_analysis(
    address: str,
    *,
    db_path: str | Path | None = None,
    radius_m: int = DEFAULT_RADIUS_M,
    resolve: Callable[[str], Awaitable[Site]] | None = None,
    agents: AgentRegistry | None = None,
    generate_action: GenerateAction | None = None,
    generate: GenerateDecision | None = None,
    request_id: str | None = None,
    agent_timeout: float | None = None,
    overall_timeout: float | None = None,
    settings: ExecutionSettings | None = None,
    supplements: list[SupplementTool] | None = None,
    on_supplement: OnSupplement | None = None,
) -> DecisionResult:
    """요청·중간 결과·최종 결과를 저장하며 실패는 호출자에게 전달합니다."""
    radius_m = validate_radius(radius_m)
    supplements = list(supplements or [])
    validate_tools(supplements)
    if not isinstance(address, str) or not address.strip():
        raise ValueError("주소가 비어 있습니다.")
    if request_id is None:
        request_id = uuid.uuid4().hex
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("요청 ID가 비어 있습니다.")
    request_id = request_id.strip()
    settings = settings or ExecutionSettings.from_env()
    resolve = resolve if resolve is not None else partial(resolve_site, settings=settings.address)
    agents = agents if agents is not None else build_react_agents(settings)
    generate_action = generate_action or partial(
        llm.generate_action, settings=settings.orchestration_llm
    )
    generate = generate or partial(decision.generate_decision, settings=settings.decision_llm)
    db_path = db_path if db_path is not None else settings.db_path
    agent_timeout = settings.agent_timeout if agent_timeout is None else agent_timeout
    overall_timeout = settings.overall_timeout if overall_timeout is None else overall_timeout
    if set(agents) != set(AGENT_IDS) or not all(callable(agent) for agent in agents.values()):
        raise ValueError("세 분석 에이전트의 호출 함수를 등록해 주세요.")
    if not callable(resolve):
        raise ValueError("주소 변환 함수가 필요합니다.")

    validate_timeout(agent_timeout)
    validate_timeout(overall_timeout)
    owned = False
    source_attempts = dict.fromkeys(AGENT_IDS, 1)

    async def create() -> None:
        nonlocal owned
        await asyncio.to_thread(
            repository.create_request, request_id, address, radius_m=radius_m, db_path=path
        )
        owned = True

    async def save_task(task: AnalysisTask) -> None:
        await _settle(asyncio.to_thread(repository.save_site, task, db_path=path))

    async def save_analysis(analysis: AgentAnalysis) -> None:
        await _settle(asyncio.to_thread(repository.save_agent, analysis, db_path=path))

    async def save_supplement(event: SupplementEvent) -> None:
        await _settle(asyncio.to_thread(repository.save_supplement_event, event, db_path=path))
        if event.adopted:
            source_attempts[event.request.agent_id] = 2
        if on_supplement is not None:
            await on_supplement(event.model_copy(deep=True))

    try:
        async with asyncio.timeout(overall_timeout):
            path = await _settle(asyncio.to_thread(initialize, db_path))
            # INSERT 성공을 확인한 호출만 이 요청의 실패 상태를 변경할 수 있습니다.
            await _settle(create())
            await _settle(asyncio.to_thread(repository.mark_running, request_id, db_path=path))
            result = await run_react(
                address,
                radius_m=radius_m,
                resolve=resolve,
                agents=agents,
                request_id=request_id,
                generate_action=generate_action,
                generate=generate,
                on_task_prepared=save_task,
                on_analysis_completed=save_analysis,
                agent_timeout=agent_timeout,
                supplements=supplements,
                on_supplement=save_supplement,
            )
            await _settle(
                asyncio.to_thread(
                    repository.complete_request,
                    result,
                    source_attempts=source_attempts,
                    db_path=path,
                )
            )
            return result
    except (Exception, asyncio.CancelledError) as exc:
        if not owned:
            raise
        code, message = "ANALYSIS_FAILED", "분석 실행 또는 결과 검증에 실패했습니다."
        if isinstance(exc, asyncio.CancelledError):
            code, message = "ANALYSIS_CANCELLED", "분석 실행이 취소됐습니다."
        elif isinstance(exc, TimeoutError):
            code, message = "ANALYSIS_TIMEOUT", "전체 분석 제한시간이 초과됐습니다."
        elif isinstance(exc, sqlite3.Error):
            code, message = "STORAGE_ERROR", "결과 저장에 실패했습니다."

        def fail_if_open() -> None:
            row = repository.get_request(request_id, db_path=path)
            if row and row["status"] in {"pending", "running"}:
                repository.fail_request(
                    request_id, AgentError(code=code, message=message), db_path=path
                )

        try:
            await _settle(asyncio.to_thread(fail_if_open))
        except asyncio.CancelledError:
            raise
        except Exception:
            exc.add_note("DB 실패 상태를 기록하지 못했습니다. 기존 상태를 확인해 주세요.")
        raise

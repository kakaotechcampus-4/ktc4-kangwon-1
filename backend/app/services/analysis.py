"""오케스트레이터 실행 중 검증된 결과를 SQLite에 저장합니다."""

import asyncio
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.agents.decision.agent import GenerateDecision
from app.agents.orchestration.workflow import AgentRegistry, GenerateAction, run_react
from app.db import repository
from app.db.connection import initialize
from app.schemas import AGENT_IDS, AgentAnalysis, AgentError, AnalysisTask, DecisionResult, Site


async def execute_analysis(
    address: str,
    *,
    db_path: str | Path | None = None,
    resolve: Callable[[str], Awaitable[Site]],
    agents: AgentRegistry,
    generate_action: GenerateAction | None = None,
    generate: GenerateDecision | None = None,
    request_id: str | None = None,
) -> DecisionResult:
    """요청·중간 결과·최종 결과를 저장하며 실패는 호출자에게 전달합니다."""
    if not isinstance(address, str) or not address.strip():
        raise ValueError("주소가 비어 있습니다.")
    if request_id is None:
        request_id = uuid.uuid4().hex
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("요청 ID가 비어 있습니다.")
    request_id = request_id.strip()
    if set(agents) != set(AGENT_IDS) or not all(callable(agent) for agent in agents.values()):
        raise ValueError("세 분석 에이전트의 호출 함수를 등록해 주세요.")
    if not callable(resolve):
        raise ValueError("주소 변환 함수가 필요합니다.")

    path = await asyncio.to_thread(initialize, db_path)
    # 중복 요청은 기존 행의 상태를 바꾸지 않고 여기서 거절합니다.
    await asyncio.to_thread(repository.create_request, request_id, address, db_path=path)

    async def save_task(task: AnalysisTask) -> None:
        await asyncio.to_thread(repository.save_site, task, db_path=path)

    async def save_analysis(analysis: AgentAnalysis) -> None:
        await asyncio.to_thread(repository.save_agent, analysis, db_path=path)

    try:
        await asyncio.to_thread(repository.mark_running, request_id, db_path=path)
        result = await run_react(
            address,
            resolve=resolve,
            agents=agents,
            request_id=request_id,
            generate_action=generate_action,
            generate=generate,
            on_task_prepared=save_task,
            on_analysis_completed=save_analysis,
        )
        await asyncio.to_thread(repository.complete_request, result, db_path=path)
        return result
    except Exception as exc:
        # 예외 원문에는 URL·키가 섞일 수 있어 DB에는 고정된 메시지만 기록합니다.
        error = AgentError(
            code="STORAGE_ERROR" if isinstance(exc, sqlite3.Error) else "ANALYSIS_FAILED",
            message="결과 저장에 실패했습니다."
            if isinstance(exc, sqlite3.Error)
            else "분석 실행 또는 결과 검증에 실패했습니다.",
        )
        try:
            await asyncio.to_thread(repository.fail_request, request_id, error, db_path=path)
        except Exception:
            exc.add_note("DB에 실패 상태를 기록하지 못했습니다. 기존 실행 상태를 확인해 주세요.")
        raise

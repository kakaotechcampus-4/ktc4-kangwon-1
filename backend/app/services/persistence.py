"""검증된 그래프 변경분의 저장과 취소 중 쓰기 완료를 담당합니다."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from app.agents.orchestration.graph import RunHooks
from app.db import repository
from app.db.analysis_repository import SqliteAnalysisRepository
from app.logging import log_exception
from app.storage.contracts import AnalysisPersistenceProtocol

logger = logging.getLogger("app.services.analysis")


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
            except Exception as exc:
                log_exception(logger, "취소 대기 중 저장 작업 실패", exc)
                break
        if not task.cancelled():
            task.exception()
        raise


async def _emit(path, request_id: str, stage: str, event: str, **detail) -> None:
    """진행 이벤트는 화면 표시용이라 저장 실패가 분석을 멈추지 않게 기록만 남깁니다."""
    try:
        await _settle(
            asyncio.to_thread(
                repository.append_event, request_id, stage, event, detail, db_path=path
            )
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log_exception(logger, "진행 이벤트 저장 실패: %s %s", exc, stage, event)


def _storage_hooks(
    path,
    source_attempts,
    on_supplement=None,
    *,
    request_id=None,
    storage: AnalysisPersistenceProtocol | None = None,
) -> RunHooks:
    storage = storage if storage is not None else SqliteAnalysisRepository(path)

    async def write(fn, *args, **kwargs):
        return await _settle(asyncio.to_thread(fn, *args, **kwargs))

    async def save_task(task):
        await write(storage.save_site, task)

    async def save_analysis(analysis):
        await write(storage.save_agent, analysis)

    async def start_map(task, plan):
        await write(storage.start_map_lookup, task, plan)

    async def save_map(observation, adopted=True):
        await write(storage.complete_map_lookup, observation, adopted=adopted)

    async def save_supplement(event):
        attempt = await write(storage.save_supplement_event, event)
        if event.adopted:
            source_attempts[event.request.agent_id] = attempt
        if on_supplement is not None:
            await on_supplement(event.model_copy(deep=True))

    async def save_brief(brief):
        await write(storage.save_agent_brief, brief)

    async def save_answer(answer):
        await write(storage.save_specialist_answer, answer)

    async def save_evaluation(draft, evaluations):
        await write(storage.save_evaluation, draft, evaluations)

    async def save_log(entries):
        await write(storage.save_evaluation_log, request_id, entries)

    async def on_step(stage, event, detail):
        if stage == "evaluate" and "skipped" in detail:
            await write(
                storage.update_execution_state, request_id, evaluation_skipped=detail["skipped"]
            )
        await _emit(path, request_id, stage, event, **detail)

    return RunHooks(
        on_evaluation=save_evaluation,
        on_evaluation_log=save_log,
        on_task_prepared=save_task,
        on_analysis_completed=save_analysis,
        on_supplement=save_supplement,
        on_map_requested=start_map,
        on_map_completed=save_map,
        on_map_result=save_map,
        on_brief=save_brief,
        on_consult=save_answer,
        on_step=on_step if request_id else None,
    )

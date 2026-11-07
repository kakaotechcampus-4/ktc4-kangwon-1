"""단일 프로세스 분석 작업의 등록과 종료를 관리합니다."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

logger = logging.getLogger(__name__)


class JobConflictError(RuntimeError):
    """같은 요청의 작업이 아직 실행 중입니다."""


class JobLimitError(RuntimeError):
    """실행 가능한 작업 수를 넘었습니다."""


class JobClosedError(RuntimeError):
    """종료 중이라 작업을 접수할 수 없습니다."""


class AnalysisJobRegistry:
    """작업표와 접수 한도는 이 인스턴스의 이벤트 루프 안에서만 유효합니다."""

    def __init__(self, max_concurrency: int):
        self.max_concurrency = max_concurrency
        self.tasks: dict[str, asyncio.Task] = {}
        self.closed = False

    def is_active(self, request_id: str) -> bool:
        task = self.tasks.get(request_id)
        return task is not None and not task.done()

    def start(self, request_id: str, work: Coroutine[Any, Any, Any]) -> asyncio.Task:
        try:
            if self.closed:
                raise JobClosedError
            if self.is_active(request_id):
                raise JobConflictError
            if len(self.tasks) >= self.max_concurrency:
                raise JobLimitError
        except (JobClosedError, JobConflictError, JobLimitError):
            work.close()
            raise
        task = asyncio.create_task(work, name="analysis-" + request_id)
        self.tasks[request_id] = task
        task.add_done_callback(lambda done: self._finished(request_id, done))
        return task

    def _finished(self, request_id: str, done: asyncio.Task) -> None:
        if self.tasks.get(request_id) is done:
            del self.tasks[request_id]
        if not done.cancelled() and (error := done.exception()) is not None:
            # 실패의 상세 진단은 서비스가 저장하며 여기서는 원문·스택을 남기지 않습니다.
            logger.warning("백그라운드 분석 실패: %s (%s)", request_id, type(error).__name__)

    async def shutdown(self, timeout_seconds: float = 10) -> None:
        tasks = [task for task in self.tasks.values() if not task.done()]
        if not self.closed:
            self.closed = True
            for task in tasks:
                task.cancel()
        if tasks:
            # wait_for는 제한시간이 지나면 cleanup을 다시 취소하므로 사용하지 않습니다.
            _, pending = await asyncio.wait(tasks, timeout=timeout_seconds)
            if pending:
                logger.warning("분석 종료 정리 대기 초과: 남은 작업 %s개", len(pending))

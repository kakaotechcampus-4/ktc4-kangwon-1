"""외부 연결 없이 그래프와 저장 서비스를 실행하는 테스트 보조 함수입니다."""

import tempfile
from dataclasses import replace
from pathlib import Path

from app.agents.orchestration.graph import RunHooks, run_graph
from app.services.analysis import execute_analysis
from app.services.settings import ExecutionSettings


async def run_flow(address, **kwargs):
    hooks = RunHooks(
        **{name: kwargs.pop(name) for name in RunHooks.__dataclass_fields__ if name in kwargs}
    )
    kwargs.setdefault("request_id", "graph-test")
    kwargs.setdefault("radius_m", 500)
    return await run_graph(address, hooks=hooks, **kwargs)


async def run_service(address, *, site=None, settings=None, **kwargs):
    """이전 저장 없는 통합 시험을 임시 DB 기반 서비스 시험으로 옮깁니다."""
    with tempfile.TemporaryDirectory() as directory:
        config = ExecutionSettings(db_path=Path(directory) / "test.sqlite3")
        if settings is not None:
            config = (
                replace(settings, db_path=config.db_path)
                if isinstance(settings, ExecutionSettings)
                else replace(config, commercial=settings)
            )
        if site is not None:

            async def resolve(_):
                return site

            kwargs["resolve"] = resolve
        return await execute_analysis(address, settings=config, **kwargs)

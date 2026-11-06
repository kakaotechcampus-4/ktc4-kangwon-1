import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.ai.preflight import collect_preflight
from app.application.local_snapshot import persist_local
from app.domain.schemas import AnalysisTask, Site
from app.infrastructure.clients.address import resolve_site
from app.infrastructure.llm.session import with_client_session
from app.infrastructure.market_data.local.adapter import LocalAdapter
from app.infrastructure.persistence import repository
from app.infrastructure.persistence.connection import initialize
from app.infrastructure.persistence.raw_capture import capture_scope
from app.shared.concurrency import run_in_thread

RADIUS_M = 500


@with_client_session
async def score_address(
    address: str,
    *,
    local_data_path: Path,
    db_path: Path,
    request_id: str | None = None,
    resolve: Callable[[str], Awaitable[Site]] | None = None,
) -> tuple[Site, dict[str, Any], dict[str, Any]]:
    rid = request_id or f"bt-{uuid.uuid4().hex}"
    path = await run_in_thread(initialize, db_path)
    await run_in_thread(
        lambda: repository.create_request(rid, address, radius_m=RADIUS_M, db_path=path)
    )
    await run_in_thread(lambda: repository.mark_running(rid, db_path=path))
    async with capture_scope(rid, path) as scope:
        adapter = await run_in_thread(LocalAdapter, local_data_path)
        site = await (resolve or resolve_site)(address)
        task = AnalysisTask(request_id=rid, site=site, radius_m=RADIUS_M)
        await run_in_thread(lambda: repository.save_site(task, db_path=path))
        observations, _ = await collect_preflight(scope, site)
        data, report, _ = await run_in_thread(
            persist_local, task, scope, adapter, None, observations
        )
        await scope.finish()
    return site, data, report

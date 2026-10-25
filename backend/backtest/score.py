import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from app.address import resolve_site
from app.agentic.preflight import collect_preflight
from app.concurrency import run_in_thread
from app.db import repository
from app.db.connection import initialize
from app.llm.session import with_client_session
from app.local_data.adapter import LocalAdapter
from app.local_data.persistence import persist_local
from app.schemas import AnalysisTask, Site
from app.storage.raw import capture_scope

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

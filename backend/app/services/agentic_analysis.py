"""새 단일 도구 루프 서비스입니다. 기존 API·모드 전환은 PR7에서 합니다."""

import asyncio
import json
import logging
import os
import re
import uuid
from time import monotonic

from app.address import resolve_site
from app.agents.agentic.budget import RuntimeBudget
from app.agents.agentic.registry import persist_snapshot_scores
from app.agents.agentic.runtime import DecisionLoop
from app.agents.orchestration.workflow import build_react_agents, run_agents
from app.db import repository
from app.db.connection import connect, initialize
from app.llm.session import with_client_session
from app.schemas import AgentError, AnalysisTask, Site
from app.storage.raw import CaptureScope, _now, _write, capture_scope, scrub

logger = logging.getLogger(__name__)


def _persist_outcome(path, request_id, outcome):
    with connect(path) as db:
        if outcome.status == "waiting_for_input":
            db.execute(
                "UPDATE analysis_requests SET status='waiting_for_input' WHERE request_id=?",
                (request_id,),
            )
        else:
            db.execute(
                "UPDATE analysis_requests SET "
                "status='completed',result_json=?,completed_at=? WHERE "
                "request_id=?",
                (outcome.result.model_dump_json(), _now(), request_id),
            )


async def _failure(path, request_id, exc, stage, timings=None):
    secrets = [
        v for k, v in os.environ.items() if any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET"))
    ]

    def safe(value):
        text = scrub(str(value), secrets)
        text = re.sub(r"https?://[^\s<>\"']+", "[URL 생략]", text)
        text = re.sub(
            r"(?i)(?:servicekey|api[_-]?key|authorization|token)\s*[=:]\s*\S+", "[인증 생략]", text
        )
        return text[:1000]

    causes = []
    cause = exc.__cause__
    while cause is not None and len(causes) < 4:
        causes.append(
            {
                "exception_class": type(cause).__name__,
                "message": safe(cause),
                "error_code": safe(getattr(cause, "sqlite_errorname", type(cause).__name__)),
            }
        )
        cause = cause.__cause__
    provider = getattr(exc, "diagnostics", {})
    diagnostics = [
        {
            "exception_class": type(exc).__name__,
            "error_code": safe(
                getattr(exc, "code", None) or provider.get("provider_code") or type(exc).__name__
            ),
            "http_status": provider.get("http_status"),
            "message": safe(exc),
            "stage": stage,
            "causes": causes,
            "phase_seconds": timings or {},
        }
    ]
    logger.error("새 판단 실행 실패: %s", json.dumps(diagnostics, ensure_ascii=False))

    def save():
        error = AgentError(code="AGENTIC_FAILED", message="새 판단 실행을 완료하지 못했습니다.")
        failed_at = _now()
        with connect(path) as db:
            changed = db.execute(
                "UPDATE analysis_requests SET error_json=?,status='failed',completed_at=? "
                "WHERE request_id=? AND status IN ('pending','running','waiting_for_input')",
                (error.model_dump_json(), failed_at, request_id),
            )
            if changed.rowcount != 1:
                raise ValueError("종료할 수 있는 요청이 없습니다.")
            db.execute(
                "INSERT INTO decision_failures VALUES(?,?,?,?)",
                (
                    request_id,
                    failed_at,
                    error.model_dump_json(),
                    json.dumps(diagnostics, ensure_ascii=False),
                ),
            )

    await _write(save)


@with_client_session
async def execute_agentic_analysis(
    address,
    *,
    radius_m=500,
    db_path=None,
    request_id=None,
    resolve=None,
    agents=None,
    generate=None,
    advisor_generate=None,
):
    request_id = request_id or uuid.uuid4().hex
    path = await _write(initialize, db_path)
    await _write(
        lambda: repository.create_request(request_id, address, radius_m=radius_m, db_path=path)
    )
    budget = RuntimeBudget()
    stage, started, timings = "수집", monotonic(), {}
    try:
        await _write(lambda: repository.mark_running(request_id, db_path=path))
        async with capture_scope(request_id, path) as scope:
            async with asyncio.timeout(120):
                site = await (resolve or resolve_site)(address)
                task = AnalysisTask(request_id=request_id, site=site, radius_m=radius_m)
                await _write(lambda: repository.save_site(task, db_path=path))

                async def completed(analysis):
                    await _write(lambda: repository.save_agent(analysis, db_path=path))

                await run_agents(
                    task,
                    agents or build_react_agents(),
                    on_analysis_completed=completed,
                    agent_timeout=110,
                )
                await scope.finish()
                timings[stage] = monotonic() - started
                stage, started = "채점", monotonic()
                await persist_snapshot_scores(task)
                timings[stage] = monotonic() - started
            stage, started = "루프", monotonic()
            loop = await DecisionLoop.create(
                scope, site, generate=generate, advisor_generate=advisor_generate, budget=budget
            )
            loop.state["phase_seconds"] = timings
            outcome = await loop.run()
            timings[stage] = monotonic() - started
            await loop.save(outcome.status, outcome.result)
            await _write(_persist_outcome, path, request_id, outcome)
            return outcome
    except (Exception, asyncio.CancelledError) as exc:
        timings[stage] = monotonic() - started
        await _failure(path, request_id, exc, stage, timings)
        raise


@with_client_session
async def resume_agentic_analysis(
    request_id, answers, *, db_path=None, generate=None, advisor_generate=None
):
    path = await _write(initialize, db_path)

    def context():
        with connect(path) as db:
            row = db.execute(
                "SELECT a.site_json,r.snapshot_id,r.run_id FROM analysis_requests "
                "a JOIN agentic_runs r USING(request_id) WHERE a.request_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise ValueError("새 판단 요청을 찾을 수 없습니다.")
        return Site.model_validate_json(row[0]), row[1], row[2]

    site, snapshot, run_id = await _write(context)
    scope = CaptureScope(request_id, path, run_id, snapshot)
    try:
        loop = await DecisionLoop.resume(
            scope, site, answers, generate=generate, advisor_generate=advisor_generate
        )
        outcome = await loop.run()
        await scope.finish()
        await _write(_persist_outcome, path, request_id, outcome)
        return outcome
    except ValueError:
        raise
    except (Exception, asyncio.CancelledError) as exc:
        await _failure(path, request_id, exc, "루프")
        raise

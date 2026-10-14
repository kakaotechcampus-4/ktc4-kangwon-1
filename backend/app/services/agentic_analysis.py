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
from app.agents.agentic.recording import CallRecording
from app.agents.agentic.registry import persist_snapshot_scores
from app.agents.agentic.runtime import DecisionLoop
from app.agents.orchestration.workflow import run_agents
from app.config import BACKEND_DIR
from app.db import repository
from app.db.connection import connect, initialize
from app.llm.session import with_client_session
from app.local_data.adapter import LocalAdapter
from app.local_data.persistence import persist_local
from app.local_data.provenance import validate_snapshot
from app.schemas import AgentError, AnalysisTask, Site
from app.storage.raw import CaptureScope, _now, _write, capture_scope, scrub

logger = logging.getLogger(__name__)


async def _event(path, request_id, stage, event):
    try:
        await _write(lambda: repository.append_event(request_id, stage, event, {}, db_path=path))
    except Exception as exc:
        logger.warning("진행 이벤트 저장 실패: %s", type(exc).__name__)


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
    evaluator_generate=None,
    local_data_path=None,
    measurement=False,
    recording_path=None,
):
    request_id = request_id or uuid.uuid4().hex
    path = await _write(initialize, db_path)
    await _write(
        lambda: repository.create_request(request_id, address, radius_m=radius_m, db_path=path)
    )
    budget = RuntimeBudget(measurement=measurement)
    recorder = (
        CallRecording(recording_path or BACKEND_DIR / "cache" / f"{request_id}-model-calls.json")
        if measurement or recording_path
        else None
    )
    stage, started, timings = "수집", monotonic(), {}
    try:
        await _write(lambda: repository.mark_running(request_id, db_path=path))
        await _event(path, request_id, "address", "started")
        async with capture_scope(request_id, path) as scope:
            adapter = await _write(LocalAdapter, local_data_path) if agents is None else None
            async with asyncio.timeout(600 if measurement else 120):
                site = await (resolve or resolve_site)(address)
                task = AnalysisTask(request_id=request_id, site=site, radius_m=radius_m)
                await _write(lambda: repository.save_site(task, db_path=path))
                await _event(path, request_id, "address", "completed")
                await _event(path, request_id, "local_data", "started")

                async def completed(analysis):
                    await _write(lambda: repository.save_agent(analysis, db_path=path))

                if adapter is None:
                    await run_agents(
                        task, agents, on_analysis_completed=completed, agent_timeout=110
                    )
                timings[stage] = monotonic() - started
                stage, started = "조회·채점" if adapter is not None else "채점", monotonic()
                if adapter is not None:
                    data, _, _ = await _write(persist_local, task, scope, adapter)
                else:
                    await persist_snapshot_scores(task)
                    data = {}
                await scope.finish()
                timings[stage] = monotonic() - started
            stage, started = "루프", monotonic()
            await _event(path, request_id, "local_data", "completed")
            loop = await DecisionLoop.create(
                scope,
                site,
                generate=generate,
                advisor_generate=advisor_generate,
                evaluator_generate=evaluator_generate,
                budget=budget,
                recorder=recorder,
            )
            loop.state["limitations"].extend(data.get("limitations", []))
            loop.state["phase_seconds"] = timings
            outcome = await loop.run()
            if outcome.status == "draft_available":
                outcome = await loop.review_and_finalize()
            timings[stage] = monotonic() - started
            await loop.save(outcome.status, outcome.result)
            await _write(_persist_outcome, path, request_id, outcome)
            return outcome
    except (Exception, asyncio.CancelledError) as exc:
        timings[stage] = monotonic() - started
        await _failure(path, request_id, exc, stage, timings)
        await _event(path, request_id, "final", "failed")
        raise


@with_client_session
async def resume_agentic_analysis(
    request_id,
    answers,
    *,
    db_path=None,
    generate=None,
    advisor_generate=None,
    evaluator_generate=None,
    measurement=False,
    recording_path=None,
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
    recorder = (
        CallRecording(recording_path or BACKEND_DIR / "cache" / f"{request_id}-model-calls.json")
        if measurement or recording_path
        else None
    )
    try:
        await _write(validate_snapshot, scope)
        loop = await DecisionLoop.resume(
            scope,
            site,
            answers,
            generate=generate,
            advisor_generate=advisor_generate,
            evaluator_generate=evaluator_generate,
            measurement=measurement,
            recorder=recorder,
        )
        outcome = await loop.run()
        if outcome.status == "draft_available":
            outcome = await loop.review_and_finalize()
        await scope.finish()
        await _write(_persist_outcome, path, request_id, outcome)
        return outcome
    except ValueError:
        raise
    except (Exception, asyncio.CancelledError) as exc:
        await _failure(path, request_id, exc, "루프")
        raise

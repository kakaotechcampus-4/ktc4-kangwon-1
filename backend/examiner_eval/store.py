"""저장된 요청 DB에서 심사 시험에 쓸 요청 재료를 읽습니다."""

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from app.schemas import Site
from app.storage.raw import CaptureScope


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    snapshot_id: str
    run_id: str
    site: Site
    stored_draft: dict
    facts: dict[tuple[str, str, str], str]


def open_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def copy_store(src: Path, dest: Path) -> Path:
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(dest)
    with closing(open_readonly(src)) as source, closing(sqlite3.connect(dest)) as target:
        source.backup(target)
    return dest


def load_contexts(db_path: Path) -> list[RequestContext]:
    contexts = []
    with closing(open_readonly(db_path)) as db:
        requests = db.execute(
            "SELECT request_id, site_json FROM analysis_requests ORDER BY request_id"
        ).fetchall()
        for request in requests:
            request_id = request["request_id"]
            draft = db.execute(
                "SELECT snapshot_id, result_json FROM agentic_reports "
                "WHERE request_id=? AND phase='draft_candidate' "
                "ORDER BY created_at, report_id LIMIT 1",
                (request_id,),
            ).fetchone()
            if draft is None or not request["site_json"]:
                continue
            snapshot_id = draft["snapshot_id"]
            run = db.execute(
                "SELECT run_id FROM agentic_runs WHERE request_id=? AND snapshot_id=? "
                "ORDER BY updated_at DESC LIMIT 1",
                (request_id, snapshot_id),
            ).fetchone()
            if run is None:
                continue
            facts = {}
            for fact in db.execute(
                "SELECT fact_id, industry_code, source, metric FROM facts "
                "WHERE request_id=? AND snapshot_id=? AND status='observed' AND citable=1 "
                "ORDER BY fact_id",
                (request_id, snapshot_id),
            ):
                key = (fact["industry_code"], fact["source"], fact["metric"])
                facts.setdefault(key, fact["fact_id"])
            contexts.append(
                RequestContext(
                    request_id=request_id,
                    snapshot_id=snapshot_id,
                    run_id=run["run_id"],
                    site=Site.model_validate_json(request["site_json"]),
                    stored_draft=json.loads(draft["result_json"]),
                    facts=facts,
                )
            )
    return contexts


def make_scope(ctx: RequestContext, db_path: Path) -> CaptureScope:
    return CaptureScope(
        request_id=ctx.request_id,
        path=Path(db_path),
        run_id=ctx.run_id,
        snapshot_id=ctx.snapshot_id,
    )

"""녹화와 요청 DB 복사본으로 모델·지도·규제 네트워크 없이 초안을 재생합니다."""

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.agentic.contracts import MapResult, RegulationResult, ToolReply  # noqa: E402
from app.agents.agentic.recording import ReplayGenerate  # noqa: E402
from app.agents.agentic.runtime import DecisionLoop  # noqa: E402
from app.config import load_environment  # noqa: E402
from app.db.connection import connect  # noqa: E402
from app.local_data.provenance import validate_snapshot  # noqa: E402
from app.schemas import AnalysisTask, Site  # noqa: E402
from app.storage.raw import CaptureScope  # noqa: E402


def prepare(source, output, request_id):
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError("원본과 다른 새 재생 DB 경로를 지정하세요.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(output) as target:
            original.backup(target)
    with connect(output) as db:
        rows = db.execute("SELECT request_id,site_json FROM analysis_requests").fetchall()
        if request_id is None:
            if len(rows) != 1:
                raise ValueError("여러 요청 DB는 --request-id가 필요합니다.")
            request_id = rows[0][0]
        row = db.execute(
            "SELECT r.*,a.site_json FROM agentic_runs r "
            "JOIN analysis_requests a USING(request_id) WHERE request_id=?",
            (request_id,),
        ).fetchone()
        original_state = json.loads(row["state_json"])
        proposal = db.execute(
            "SELECT proposal_json FROM agentic_reports WHERE request_id=? "
            "ORDER BY rowid DESC LIMIT 1",
            (request_id,),
        ).fetchone()
        sequence = original_state["tool_sequence"]
        for table in ("agentic_runs", "agentic_questions", "agentic_reports"):
            db.execute(f"DELETE FROM {table} WHERE request_id=?", (request_id,))
        db.execute(
            "UPDATE analysis_requests SET status='running',result_json=NULL,"
            "error_json=NULL,completed_at=NULL WHERE request_id=?",
            (request_id,),
        )
    return dict(row), original_state, json.loads(proposal[0]) if proposal else None, sequence


def latest_proposal(path, request_id):
    with connect(path) as db:
        row = db.execute(
            "SELECT proposal_json FROM agentic_reports WHERE request_id=? "
            "ORDER BY rowid DESC LIMIT 1",
            (request_id,),
        ).fetchone()
    return json.loads(row[0]) if row else None


def restore_ids(value, mapping):
    if isinstance(value, dict):
        return {k: restore_ids(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [restore_ids(v, mapping) for v in value]
    return mapping.get(value, value) if isinstance(value, str) else value


async def replay(args):
    output = args.output_db or Path("cache") / f"replay-{uuid4().hex}.sqlite3"
    row, original, expected, sequence = await asyncio.to_thread(
        prepare, args.request_db, output, args.request_id
    )
    scope = CaptureScope(row["request_id"], output, row["run_id"], row["snapshot_id"])
    site = Site.model_validate_json(row["site_json"])
    generator = ReplayGenerate(args.recording)
    measurement = original.get("budget", {}).get("measurement", False)
    with patch("httpx.AsyncClient", side_effect=AssertionError("재생 HTTP 금지")):
        loop = await DecisionLoop.create(
            scope, site, generate=generator, advisor_generate=generator, measurement=measurement
        )
        adapter = await asyncio.to_thread(validate_snapshot, scope)
        if adapter:
            data = await asyncio.to_thread(
                adapter.analyze, AnalysisTask(request_id=scope.request_id, site=site, radius_m=500)
            )
            loop.state["limitations"] = data.get("limitations", [])
        shared = loop.tools.shared
        if original.get("regulation"):
            shared.regulation = RegulationResult.model_validate(original["regulation"])
        shared.map_cache = {
            k: ToolReply[MapResult].model_validate(v)
            for k, v in original.get("map_cache", {}).items()
        }
        outcome = await loop.run()
        if outcome.status == "waiting_for_input":
            answers = {
                "floor": "1층",
                "exclusive_area": "약 40㎡(12평)",
                "space_condition": "이전 업종 일반 소매, 주방·배기 설비 없음",
            }
            fields = {q.field for q in outcome.questions}
            if not fields <= answers.keys():
                raise ValueError("녹화 시험 답변 외의 항목이 필요합니다.")
            loop = await DecisionLoop.resume(
                scope,
                site,
                {k: answers[k] for k in fields},
                generate=generator,
                advisor_generate=generator,
                measurement=measurement,
            )
            outcome = await loop.run()
    actual = await asyncio.to_thread(latest_proposal, output, scope.request_id)
    actual = restore_ids(actual, {v: k for k, v in generator.mapping.items()})
    result = {
        "status": outcome.status,
        "model_calls": generator.position,
        "all_recordings_consumed": generator.position == len(generator.entries or []),
        "tool_sequence_equal": loop.state["tool_sequence"] == sequence,
        "draft_equal": actual == expected,
        "replay_db": str(output.resolve()),
    }
    print(json.dumps(result, ensure_ascii=False))
    if not all(
        result[k] for k in ("all_recordings_consumed", "tool_sequence_equal", "draft_equal")
    ):
        raise ValueError("재생 결과가 녹화 실행과 다릅니다.")


def main():
    load_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-db", type=Path, required=True)
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--output-db", type=Path)
    asyncio.run(replay(parser.parse_args()))


if __name__ == "__main__":
    main()

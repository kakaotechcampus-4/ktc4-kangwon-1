"""평가 초안·의견·반영 기록 저장입니다."""

import json
from pathlib import Path

from app.db.connection import connect
from app.db.types import (
    ExecutionState,
)
from app.execution import policy
from app.schemas import (
    EVALUATOR_IDS,
    DecisionResult,
    Evaluation,
    EvaluationLogEntry,
)

from .common import _dumps, _now, _require_running


def save_evaluation(
    draft: DecisionResult, evaluations: list[Evaluation], *, db_path: str | Path | None = None
) -> None:
    draft = DecisionResult.model_validate(draft)
    evaluations = [Evaluation.model_validate(e) for e in evaluations]
    policy.validate_evaluations(
        evaluations, draft.request_id, "같은 요청의 평가자 네 명이 필요합니다."
    )
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        _require_running(db, draft.request_id)
        db.execute(
            "INSERT INTO evaluation_drafts VALUES (?,?,?)",
            (
                draft.request_id,
                draft.model_dump_json(
                    include={"request_id", "summary", "recommendations", "not_recommended"}
                ),
                _now(),
            ),
        )
        for evaluation in evaluations:
            db.execute(
                "INSERT INTO evaluations VALUES (?,?,?,?,?)",
                (
                    draft.request_id,
                    evaluation.evaluator,
                    evaluation.source,
                    evaluation.model_dump_json(),
                    _now(),
                ),
            )
        row = db.execute(
            "SELECT execution_json FROM analysis_requests WHERE request_id=?", (draft.request_id,)
        ).fetchone()
        state: ExecutionState = json.loads(row[0])
        state["evaluation_start_round"] = db.execute(
            "SELECT COALESCE(MAX(round),0) FROM specialist_consults WHERE request_id=?",
            (draft.request_id,),
        ).fetchone()[0]
        db.execute(
            "UPDATE analysis_requests SET execution_json=? WHERE request_id=?",
            (_dumps(state), draft.request_id),
        )


def save_evaluation_log(
    request_id: str, entries: list[EvaluationLogEntry], *, db_path: str | Path | None = None
) -> None:
    payload = [EvaluationLogEntry.model_validate(e).model_dump(mode="json") for e in entries]
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        _require_running(db, request_id)
        db.execute(
            "INSERT INTO evaluation_logs VALUES (?,?,?) ON CONFLICT(request_id) DO UPDATE "
            "SET log_json=excluded.log_json, updated_at=excluded.updated_at",
            (request_id, _dumps(payload), _now()),
        )


def get_evaluation(request_id: str, *, db_path: str | Path | None = None) -> dict | None:
    with connect(db_path) as db:
        return _get_evaluation(db, request_id)


def _get_evaluation(db, request_id):
    draft = db.execute(
        "SELECT draft_json FROM evaluation_drafts WHERE request_id=?", (request_id,)
    ).fetchone()
    if draft is None:
        return None
    evaluations = [
        Evaluation.model_validate_json(row[0])
        for row in db.execute(
            "SELECT evaluation_json FROM evaluations WHERE request_id=?", (request_id,)
        )
    ]
    policy.validate_evaluations(evaluations, request_id, "저장된 평가 기록이 불완전합니다.")
    log = db.execute(
        "SELECT log_json FROM evaluation_logs WHERE request_id=?", (request_id,)
    ).fetchone()
    return {
        "draft": json.loads(draft[0]),
        "evaluations": sorted(evaluations, key=lambda e: EVALUATOR_IDS.index(e.evaluator)),
        "log": [EvaluationLogEntry.model_validate(e) for e in json.loads(log[0])] if log else [],
    }

"""전문가와 실행 상태 저장입니다."""

import json
from pathlib import Path

from app.db.connection import connect
from app.db.types import (
    DeliberationState,
    ExecutionState,
)
from app.execution import policy
from app.execution.validation import validate_execution_state
from app.schemas import (
    AgentBrief,
    MapLookupPlan,
    SpecialistAnswer,
)

from .common import _dumps, _now, _require_running, _text


def update_execution_state(
    request_id: str,
    *,
    budget: dict | None = None,
    elapsed_seconds: float | None = None,
    capabilities: dict | None = None,
    evaluation_skipped: str | None = None,
    time_limit: float | None = None,
    db_path: str | Path | None = None,
) -> None:
    """소비 예산·활성 실행 시간은 되돌리지 않고 저장합니다."""
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = _require_running(db, request_id)
        state: ExecutionState = json.loads(row["execution_json"])
        validate_execution_state(state)
        policy.update_execution(
            state,
            budget=budget,
            elapsed_seconds=elapsed_seconds,
            capabilities=capabilities,
            evaluation_skipped=evaluation_skipped,
            time_limit=time_limit,
        )
        db.execute(
            "UPDATE analysis_requests SET execution_json=? WHERE request_id=?",
            (_dumps(state), request_id),
        )


def save_agent_brief(brief: AgentBrief, *, db_path: str | Path | None = None) -> None:
    brief = AgentBrief.model_validate(brief)
    with connect(db_path) as db:
        _require_running(db, brief.request_id, multi=True)
        db.execute(
            "INSERT INTO agent_briefs VALUES (?,?,?,?)",
            (brief.request_id, brief.agent_id, brief.model_dump_json(), _now()),
        )


# 저장 이력·복원 불변식을 직접 검사하는 테스트용 조회 경로를 유지합니다.
def list_agent_briefs(request_id: str, *, db_path: str | Path | None = None) -> list[AgentBrief]:
    with connect(db_path) as db:
        return [
            AgentBrief.model_validate_json(r[0])
            for r in db.execute(
                "SELECT brief_json FROM agent_briefs WHERE request_id=? ORDER BY agent_id",
                (_text(request_id),),
            )
        ]


def save_specialist_answer(answer: SpecialistAnswer, *, db_path: str | Path | None = None) -> None:
    answer = SpecialistAnswer.model_validate(answer)
    with connect(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        _require_running(db, answer.request_id, multi=True)
        policy.validate_consult_count(
            db.execute(
                "SELECT count(*) FROM specialist_consults WHERE request_id=? AND round=?",
                (answer.request_id, answer.round),
            ).fetchone()[0]
        )
        db.execute(
            "INSERT INTO specialist_consults VALUES (?,?,?,?,?,?)",
            (
                answer.request_id,
                answer.round,
                answer.query.agent_id,
                answer.status,
                answer.model_dump_json(),
                _now(),
            ),
        )


# 저장 이력·복원 불변식을 직접 검사하는 테스트용 조회 경로를 유지합니다.
def list_specialist_answers(
    request_id: str, *, db_path: str | Path | None = None
) -> list[SpecialistAnswer]:
    with connect(db_path) as db:
        return [
            SpecialistAnswer.model_validate_json(r[0])
            for r in db.execute(
                "SELECT answer_json FROM specialist_consults WHERE request_id=? "
                "ORDER BY round,agent_id",
                (_text(request_id),),
            )
        ]


def _deliberation(db, request_id) -> DeliberationState:
    row = db.execute(
        "SELECT execution_json FROM analysis_requests WHERE request_id=?", (request_id,)
    ).fetchone()
    briefs = [
        AgentBrief.model_validate_json(r[0])
        for r in db.execute(
            "SELECT brief_json FROM agent_briefs WHERE request_id=? ORDER BY agent_id",
            (request_id,),
        )
    ]
    answers = [
        SpecialistAnswer.model_validate_json(r[0])
        for r in db.execute(
            "SELECT answer_json FROM specialist_consults WHERE request_id=? "
            "ORDER BY round,agent_id",
            (request_id,),
        )
    ]
    attempted = {}
    for saved in db.execute(
        "SELECT plan_json FROM map_observations WHERE request_id=? ORDER BY attempt", (request_id,)
    ):
        for query in MapLookupPlan.model_validate_json(saved[0]).unique_queries():
            attempted[(query.kind, query.industry_code, query.facility_code, query.query)] = query
    execution: ExecutionState = json.loads(row[0]) if row else {}
    validate_execution_state(execution)
    return {
        "briefs": briefs,
        "specialist_answers": answers,
        "map_queries": list(attempted.values()),
        "consult_round": max((a.round for a in answers), default=0),
        "map_attempt": db.execute(
            "SELECT MAX(attempt) FROM map_observations WHERE request_id=? AND adopted=1",
            (request_id,),
        ).fetchone()[0],
        "execution": execution,
    }


def get_deliberation(request_id: str, *, db_path: str | Path | None = None) -> DeliberationState:
    with connect(db_path) as db:
        return _deliberation(db, _text(request_id))

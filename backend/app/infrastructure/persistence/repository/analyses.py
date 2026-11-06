"""공개 API가 읽는 분석 상세·답변 판정·스냅샷 fact 조회입니다."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.application.ports.records import AnswerGate as AnswerGate
from app.application.ports.records import ResumeContext as ResumeContext
from app.application.ports.records import SnapshotFacts as SnapshotFacts
from app.domain.schemas import FactView, Site
from app.infrastructure.persistence.connection import connect
from app.infrastructure.persistence.repository.common import _request_row, _text

# 저장 어휘를 공개 계약 어휘로 옮깁니다. "n.a."는 facts.status 컬럼의 인코딩이라
# DB 바깥에는 쓰지 않습니다. 반대로 옮길 일이 생기면 이 표를 뒤집어 씁니다.
_PUBLIC_FACT_STATUS = {"n.a.": "not_applicable"}

# fact 하나의 근거를 어느 표에서 찾는지 가리키는 접두어입니다. 전부 테이블 이름입니다.
_SPACE_FIT_PROVENANCE = "fact_parents:"
_LOCAL_PROVENANCE = "local_fact_lineage:"
_SOURCE_PROVENANCE = "fact_sources:"


def get_analysis_detail(
    request_id: str, *, db_path: str | Path | None = None
) -> dict[str, Any] | None:
    """요청 한 건의 저장된 상태·질문·렌더 결과입니다. 요청이 없으면 None."""
    request_id = _text(request_id)
    with connect(db_path) as db:
        row = _request_row(db, request_id)
        if row is None:
            return None
        output = dict(row)
        for field in ("site", "result", "error"):
            output[field] = (
                json.loads(output.pop(field + "_json")) if row[field + "_json"] else None
            )
        question = db.execute(
            "SELECT question_session_id,questions_json,status FROM agentic_questions "
            "WHERE request_id=?",
            (request_id,),
        ).fetchone()
        output["questions"] = (
            {
                "question_session_id": question["question_session_id"],
                "questions": json.loads(question["questions_json"]),
                "status": question["status"],
            }
            if question
            else None
        )
        report = db.execute(
            "SELECT rendered_json FROM agentic_reports WHERE report_id=?",
            ((output["result"] or {}).get("report_id"),),
        ).fetchone()
    output["rendered"] = json.loads(report[0]) if report else None
    return output


def get_answer_gate(request_id: str, *, db_path: str | Path | None = None) -> AnswerGate | None:
    """답변을 받아도 되는지 판정할 최소 정보입니다. 요청이 없으면 None."""
    request_id = _text(request_id)
    with connect(db_path) as db:
        row = db.execute(
            "SELECT status FROM analysis_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if row is None:
            return None
        question = db.execute(
            "SELECT question_session_id,questions_json FROM agentic_questions WHERE request_id=?",
            (request_id,),
        ).fetchone()
    if question is None:
        return AnswerGate(status=row["status"], question_session_id=None, fields=frozenset())
    return AnswerGate(
        status=row["status"],
        question_session_id=question["question_session_id"],
        fields=frozenset(item["field"] for item in json.loads(question["questions_json"])),
    )


def list_snapshot_facts(
    request_id: str, *, db_path: str | Path | None = None
) -> SnapshotFacts | None:
    """리포트 차트용으로 요청 스냅샷의 전체 fact를 읽습니다. 요청이 없으면 None."""
    request_id = _text(request_id)
    with connect(db_path) as db:
        if not db.execute(
            "SELECT 1 FROM analysis_requests WHERE request_id=?", (request_id,)
        ).fetchone():
            return None
        snapshot = db.execute(
            "SELECT snapshot_id FROM snapshots WHERE request_id=?", (request_id,)
        ).fetchone()
        if snapshot is None:
            return SnapshotFacts(snapshot_id=None, facts=[])
        snapshot_id = snapshot["snapshot_id"]
        local = db.execute(
            "SELECT scope_json FROM local_snapshots WHERE snapshot_id=?", (snapshot_id,)
        ).fetchone()
        rows = db.execute(
            "SELECT *,EXISTS(SELECT 1 FROM local_fact_lineage l WHERE l.fact_id=facts.fact_id) "
            "AS local_lineage FROM facts WHERE request_id=? AND snapshot_id=? "
            # 공간 비교는 답변마다 새로 만들어지므로 현재 판정만 돌려줍니다.
            "AND (metric!='space_fit' OR fact_id IN (SELECT fact_id FROM space_fit_current "
            "WHERE request_id=? AND snapshot_id=?)) ORDER BY source,metric,industry_code,fact_id",
            (request_id, snapshot_id, request_id, snapshot_id),
        ).fetchall()
    # 로컬 자료 fact의 공간 범위는 스냅샷에 한 번만 저장되어 있어 읽을 때 펼칩니다.
    spatial = json.loads(local["scope_json"]) | {"snapshot_id": snapshot_id} if local else None
    return SnapshotFacts(snapshot_id=snapshot_id, facts=[_fact_view(row, spatial) for row in rows])


def _fact_view(row: sqlite3.Row, spatial: dict[str, Any] | None) -> FactView:
    """저장된 fact 행 하나를 공개 FactView로 옮깁니다."""
    local_lineage = bool(row["local_lineage"])
    if row["metric"] == "space_fit":
        provenance = _SPACE_FIT_PROVENANCE
    elif local_lineage:
        provenance = _LOCAL_PROVENANCE
    else:
        provenance = _SOURCE_PROVENANCE
    return FactView(
        fact_id=row["fact_id"],
        source=row["source"],
        metric=row["metric"],
        value=json.loads(row["value_json"]),
        unit=row["unit"],
        period=row["period"],
        spatial_scope=spatial
        if local_lineage and spatial
        else json.loads(row["spatial_scope_json"]),
        industry_code=row["industry_code"],
        status=_PUBLIC_FACT_STATUS.get(row["status"], row["status"]),
        citable=bool(row["citable"]),
        calc_version=row["calc_version"],
        provenance_ref=provenance + row["fact_id"],
    )


def get_resume_context(request_id: str, *, db_path: str | Path | None = None) -> ResumeContext:
    """재개 대상 요청의 자리·스냅샷·실행 ID입니다. 재개할 수 없으면 ValueError."""
    request_id = _text(request_id)
    with connect(db_path) as db:
        row = db.execute(
            "SELECT a.site_json,r.snapshot_id,r.run_id FROM analysis_requests "
            "a JOIN agentic_runs r USING(request_id) WHERE a.request_id=?",
            (request_id,),
        ).fetchone()
    if row is None:
        raise ValueError("새 판단 요청을 찾을 수 없습니다.")
    return ResumeContext(
        site=Site.model_validate_json(row["site_json"]),
        snapshot_id=row["snapshot_id"],
        run_id=row["run_id"],
    )

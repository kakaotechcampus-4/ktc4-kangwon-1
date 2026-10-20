"""임대인 질문·답변 검증과 원문·fact의 원자적 저장입니다."""

import json
import uuid
from dataclasses import dataclass

from app.canonical import canonical_json
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect
from app.errors import AnalysisConflictError

from .contracts import QuestionSessionRef, ToolReply
from .facts import register_fact
from .space import ensure_space_fits
from .sql_tool import error


@dataclass
class LoopOutcome:
    status: str
    result: object = None
    question_session_id: str | None = None
    questions: list | None = None
    budget: dict | None = None


async def ask_user(loop, input):
    if not loop.state["allow_questions"] or loop.state.get("phase") == "final":
        return error("QUESTION_NOT_ALLOWED", "현재 요청·단계에서 질문할 수 없습니다.")
    if loop.state["asked"]:
        return error("ALREADY_ANSWERED", "질문 세션을 반복할 수 없습니다.")
    loop.state["asked"] = True
    session_id = "question_" + str(uuid.uuid4())
    await run_in_thread(save_question, loop, session_id, input)
    loop.waiting = LoopOutcome(
        "waiting_for_input",
        question_session_id=session_id,
        questions=input.questions,
        budget=loop.budget.snapshot(),
    )
    return ToolReply(status="ok", data=QuestionSessionRef(question_session_id=session_id))


def save_question(loop, session_id, input):
    with connect(loop.scope.path) as db:
        db.execute(
            "INSERT INTO agentic_questions VALUES(?,?,?,?,?,?,?)",
            (
                session_id,
                loop.scope.request_id,
                loop.scope.snapshot_id,
                canonical_json([q.model_dump(mode="json") for q in input.questions]),
                "{}",
                "waiting",
                utc_now_iso(),
            ),
        )


async def validate_resume(scope, answers):
    def load():
        with connect(scope.path) as db:
            row = db.execute(
                "SELECT state_json,status FROM agentic_runs WHERE request_id=? AND snapshot_id=?",
                (scope.request_id, scope.snapshot_id),
            ).fetchone()
            question = db.execute(
                "SELECT question_session_id,questions_json,status FROM "
                "agentic_questions WHERE request_id=? AND snapshot_id=?",
                (scope.request_id, scope.snapshot_id),
            ).fetchone()
            if (
                row is None
                or row[1] != "waiting_for_input"
                or question is None
                or question[2] != "waiting"
            ):
                raise ValueError("재개할 질문 세션이 없습니다.")
            fields = {q["field"] for q in json.loads(question[1])}
            if set(answers) != fields or any(
                not isinstance(v, str) or not v.strip() or len(v) > 500 for v in answers.values()
            ):
                raise ValueError("답변 항목·길이가 잘못되었습니다.")
            return json.loads(row[0]), question[0]

    return await run_in_thread(load)


async def resume(loop_type, scope, site, answers, *, resume_state=None, **kwargs):
    saved, question_id = resume_state or await loop_type.validate_resume(scope, answers)
    saved = await run_in_thread(save_user_facts, scope, answers, question_id, saved)
    return await loop_type.create(scope, site, saved=saved, **kwargs)


def save_confirmed_space(scope, values):
    with connect(scope.path) as db:
        db.execute("BEGIN IMMEDIATE")
        response = scope.record_sync(
            source="user",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [values]},
            connection=db,
        )
        ref = db.execute(
            "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
        ).fetchone()[0]
        ids = {
            field: register_fact(
                scope,
                industry_code=None,
                source="user",
                metric=field,
                value=value,
                unit="확인 화면 확정값",
                status="observed",
                row_ids=[ref],
                field_pointer="/" + field,
                connection=db,
            )
            for field, value in values.items()
        }
    return {"values": dict(values), "fact_ids": ids}


def save_user_facts(scope, answers, question_id, saved):
    with connect(scope.path) as db:
        db.execute("BEGIN IMMEDIATE")
        question = db.execute(
            "SELECT status FROM agentic_questions WHERE question_session_id=?", (question_id,)
        ).fetchone()
        if question is None or question[0] != "waiting":
            raise AnalysisConflictError("이미 답변한 질문입니다.")
        response = scope.record_sync(
            source="user",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [answers]},
            connection=db,
        )
        ref = db.execute(
            "SELECT raw_row_id FROM raw_response_rows WHERE response_id=?", (response,)
        ).fetchone()[0]
        ids = {}
        for field, value in answers.items():
            metric = (
                field
                if field
                in {"floor", "exclusive_area", "existing_facilities", "industry_preferences"}
                else "space_condition"
            )
            ids[field] = register_fact(
                scope,
                industry_code=None,
                source="user",
                metric=metric,
                value=value,
                unit="임대인 답변",
                status="observed",
                row_ids=[ref],
                field_pointer="/" + field,
                connection=db,
            )
        ensure_space_fits(scope, connection=db)
        saved["user_answers"] = {"answers": answers, "fact_ids": ids}
        for message in reversed(saved["messages"]):
            if message["role"] != "tool":
                continue
            body = json.loads(message["content"])
            if (body.get("data") or {}).get("question_session_id") != question_id:
                continue
            body["data"] = {
                "question_session_id": question_id,
                "status": "answered",
                **saved["user_answers"],
            }
            body["fact_ids"] = list(ids.values())
            message["content"] = canonical_json(body)
            break
        else:
            raise ValueError("질문 도구 응답 기록 없음")
        saved["known_fact_ids"] = list(
            dict.fromkeys([*saved.get("known_fact_ids", []), *ids.values()])
        )
        db.execute(
            "UPDATE tool_calls SET reply_json=? WHERE request_id=? AND snapshot_id=? "
            "AND tool_name='ask_user' AND json_extract(reply_json,'$.data.question_session_id')=?",
            (
                canonical_json({k: v for k, v in body.items() if k != "tool_call_id"}),
                scope.request_id,
                scope.snapshot_id,
                question_id,
            ),
        )
        db.execute(
            "UPDATE agentic_questions SET status='answered',answers_json=? "
            "WHERE question_session_id=?",
            (canonical_json(answers), question_id),
        )
        db.execute(
            "UPDATE agentic_runs SET status='running',state_json=? "
            "WHERE request_id=? AND snapshot_id=?",
            (canonical_json(saved), scope.request_id, scope.snapshot_id),
        )
        db.execute(
            "UPDATE analysis_requests SET status='running' WHERE request_id=? "
            "AND status='waiting_for_input'",
            (scope.request_id,),
        )
    return saved

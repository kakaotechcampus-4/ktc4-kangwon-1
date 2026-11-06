"""임대인 질문·답변 검증과 원문·fact의 원자적 저장입니다."""

import json
import uuid
from dataclasses import dataclass

from app.agentic.contracts import QuestionSessionRef, ToolReply
from app.agentic.facts import register_fact
from app.agentic.space import CONFIRMED_UNIT, ensure_space_fits
from app.agentic.sql_tool import error
from app.canonical import canonical_json
from app.clock import utc_now_iso
from app.concurrency import run_in_thread
from app.db.connection import connect
from app.db.repository import agentic as agentic_db
from app.db.repository import raw as raw_db
from app.db.repository.agentic import begin_immediate
from app.errors import AnalysisConflictError


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
    if any(q.field in loop.state.get("confirmed_question_fields", []) for q in input.questions):
        return error("ALREADY_ANSWERED", "확인 화면에서 확정한 층·전용면적은 다시 묻지 마세요.")
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
        agentic_db.insert_question(
            db,
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
            row = agentic_db.run_state(db, scope.request_id, scope.snapshot_id)
            question = agentic_db.question_session(db, scope.request_id, scope.snapshot_id)
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
        begin_immediate(db)
        response = scope.record_sync(
            source="user",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [values]},
            connection=db,
        )
        ref = raw_db.first_row_id(db, response)
        ids = {
            field: register_fact(
                scope,
                industry_code=None,
                source="user",
                metric=field,
                value=value,
                unit=CONFIRMED_UNIT,
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
        begin_immediate(db)
        question = agentic_db.question_status(db, question_id)
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
        ref = raw_db.first_row_id(db, response)
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
        agentic_db.replace_ask_user_reply(
            db,
            scope.request_id,
            scope.snapshot_id,
            question_id,
            canonical_json({k: v for k, v in body.items() if k != "tool_call_id"}),
        )
        agentic_db.mark_question_answered(db, question_id, canonical_json(answers))
        agentic_db.resume_run(db, scope.request_id, scope.snapshot_id, canonical_json(saved))
        agentic_db.resume_request(db, scope.request_id)
    return saved

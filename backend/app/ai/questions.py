"""임대인 질문과 답변 검증입니다."""

import uuid
from dataclasses import dataclass

from app.application.answers import save_user_facts
from app.application.ports.storage import open_stores
from app.domain.contracts import QuestionSessionRef, ToolReply, error
from app.shared.clock import utc_now_iso
from app.shared.concurrency import run_in_thread


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
    with open_stores(loop.scope) as st:
        st.agentic.insert_question(
            question_session_id=session_id,
            request_id=loop.scope.request_id,
            snapshot_id=loop.scope.snapshot_id,
            questions=[q.model_dump(mode="json") for q in input.questions],
            created_at=utc_now_iso(),
        )


async def validate_resume(scope, answers):
    def load():
        with open_stores(scope) as st:
            row = st.agentic.run_state(scope.request_id, scope.snapshot_id)
            question = st.agentic.question_session(scope.request_id, scope.snapshot_id)
            if (
                row is None
                or row.status != "waiting_for_input"
                or question is None
                or question.status != "waiting"
            ):
                raise ValueError("재개할 질문 세션이 없습니다.")
            fields = {q["field"] for q in question.questions}
            if set(answers) != fields or any(
                not isinstance(v, str) or not v.strip() or len(v) > 500 for v in answers.values()
            ):
                raise ValueError("답변 항목·길이가 잘못되었습니다.")
            return row.state, question.question_session_id

    return await run_in_thread(load)


async def resume(loop_type, scope, site, answers, *, resume_state=None, **kwargs):
    saved, question_id = resume_state or await loop_type.validate_resume(scope, answers)
    saved = await run_in_thread(save_user_facts, scope, answers, question_id, saved)
    return await loop_type.create(scope, site, saved=saved, **kwargs)

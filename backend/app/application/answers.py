import json

from app.application.errors import AnalysisConflictError
from app.application.facts import register_fact
from app.application.ports.storage import open_stores
from app.application.space import CONFIRMED_UNIT, ensure_space_fits
from app.shared.canonical import canonical_json


def confirmed_space_values(floor, exclusive_area_m2, facilities):
    values = {}
    if floor is not None:
        values["floor"] = floor
    if exclusive_area_m2 is not None:
        values["exclusive_area"] = f"{exclusive_area_m2:.2f}".rstrip("0").rstrip(".") + "㎡"
    if facilities:
        values["existing_facilities"] = facilities
    return values or None


def save_confirmed_space(scope, values):
    with open_stores(scope) as st:
        st.begin_write()
        response = scope.record_sync(
            source="user",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [values]},
            stores=st,
        )
        ref = st.raw.first_row_id(response)
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
                stores=st,
            )
            for field, value in values.items()
        }
    return {"values": dict(values), "fact_ids": ids}


def save_user_facts(scope, answers, question_id, saved):
    with open_stores(scope) as st:
        st.begin_write()
        question = st.agentic.question_status(question_id)
        if question is None or question != "waiting":
            raise AnalysisConflictError("이미 답변한 질문입니다.")
        response = scope.record_sync(
            source="user",
            source_type="api",
            args={},
            page="1",
            status=200,
            payload={"rows": [answers]},
            stores=st,
        )
        ref = st.raw.first_row_id(response)
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
                stores=st,
            )
        ensure_space_fits(scope, stores=st)
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
        st.agentic.replace_ask_user_reply(
            scope.request_id,
            scope.snapshot_id,
            question_id,
            {k: v for k, v in body.items() if k != "tool_call_id"},
        )
        st.agentic.mark_question_answered(question_id, answers)
        st.agentic.resume_run(scope.request_id, scope.snapshot_id, saved)
        st.agentic.resume_request(scope.request_id)
    return saved

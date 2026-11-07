from app.application.ports.records import AnswerGate, SnapshotFacts
from app.application.ports.storage import storage
from app.domain.schemas import RequestStatus

NOT_FOUND = "분석 요청을 찾을 수 없습니다."
# 더 기다려도 바뀌지 않는 상태입니다. 타입을 붙여 오타가 mypy 에서 걸리게 합니다.
FINISHED: set[RequestStatus] = {"completed", "failed", "waiting_for_input"}


class AnswerRejected(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason
        self.message = message


def create(request_id, address, *, radius_m, user_id, db_path):
    return storage().requests.create_request(
        request_id, address, radius_m=radius_m, user_id=user_id, db_path=db_path
    )


def visible_to(request_id, user, *, db_path) -> bool:
    owner = storage().requests.owner_of(request_id, db_path=db_path)
    if owner is None:
        return False
    # 인증을 붙이기 전에 쌓인 요청은 소유자가 없습니다. 그 자료만 열어 둡니다.
    if owner == "legacy":
        return True
    return user is not None and user["user_id"] == owner


def detail(request_id, *, db_path):
    return storage().requests.get_analysis_detail(request_id, db_path=db_path)


def facts(request_id, *, db_path) -> SnapshotFacts | None:
    return storage().requests.list_snapshot_facts(request_id, db_path=db_path)


def answer_gate(request_id, *, db_path) -> AnswerGate | None:
    return storage().requests.get_answer_gate(request_id, db_path=db_path)


def check_answers(gate, question_session_id, fields, *, running) -> None:
    if gate is None:
        raise AnswerRejected("not_found", NOT_FOUND)
    # 질문 행이 없으면 question_session_id 가 None 이라 아래 비교에서 걸립니다.
    if (
        running
        or gate.status != "waiting_for_input"
        or gate.question_session_id != question_session_id
    ):
        raise AnswerRejected("conflict", "현재 대기 중인 질문 세션이 아닙니다.")
    if fields != gate.fields:
        raise AnswerRejected("mismatch", "질문 항목과 답변 항목이 다릅니다.")


def events(request_id, *, after, db_path):
    return storage().requests.get_request_events(request_id, after=after, db_path=db_path)


def mine(user_id, *, limit, offset, db_path):
    return storage().requests.list_user_requests(
        user_id, limit=limit, offset=offset, db_path=db_path
    )


def progress_view(request_id, row, events, *, after, running):
    if row is None:
        if running:
            return {
                "request_id": request_id,
                "status": "pending",
                "finished": False,
                "events": [],
                "next_after": after,
            }
        return None
    status = "running" if running and row["status"] in FINISHED else row["status"]
    return {
        "request_id": request_id,
        "status": status,
        "finished": status in FINISHED,
        "events": events,
        "next_after": events[-1]["seq"] if events else after,
    }


def record_event(scope, stage, event, detail):
    storage().requests.append_event(scope.request_id, stage, event, detail, db_path=scope.path)

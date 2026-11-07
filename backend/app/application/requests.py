from app.application.ports.records import AnswerGate, SnapshotFacts
from app.application.ports.storage import storage

NOT_FOUND = "분석 요청을 찾을 수 없습니다."


class AnswerRejected(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
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
        raise AnswerRejected(404, NOT_FOUND)
    # 질문 행이 없으면 question_session_id 가 None 이라 아래 비교에서 걸립니다.
    if (
        running
        or gate.status != "waiting_for_input"
        or gate.question_session_id != question_session_id
    ):
        raise AnswerRejected(409, "현재 대기 중인 질문 세션이 아닙니다.")
    if fields != gate.fields:
        raise AnswerRejected(422, "질문 항목과 답변 항목이 다릅니다.")


def events(request_id, *, after, db_path):
    return storage().requests.get_request_events(request_id, after=after, db_path=db_path)


def mine(user_id, *, limit, offset, db_path):
    return storage().requests.list_user_requests(
        user_id, limit=limit, offset=offset, db_path=db_path
    )

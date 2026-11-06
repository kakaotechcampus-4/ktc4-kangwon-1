from app.application.ports.records import AnswerGate, SnapshotFacts
from app.application.ports.storage import storage


def create(request_id, address, *, radius_m, user_id, db_path):
    return storage().requests.create_request(
        request_id, address, radius_m=radius_m, user_id=user_id, db_path=db_path
    )


def owner(request_id, *, db_path):
    return storage().requests.owner_of(request_id, db_path=db_path)


def detail(request_id, *, db_path):
    return storage().requests.get_analysis_detail(request_id, db_path=db_path)


def facts(request_id, *, db_path) -> SnapshotFacts | None:
    return storage().requests.list_snapshot_facts(request_id, db_path=db_path)


def answer_gate(request_id, *, db_path) -> AnswerGate | None:
    return storage().requests.get_answer_gate(request_id, db_path=db_path)


def events(request_id, *, after, db_path):
    return storage().requests.get_request_events(request_id, after=after, db_path=db_path)


def mine(user_id, *, limit, offset, db_path):
    return storage().requests.list_user_requests(
        user_id, limit=limit, offset=offset, db_path=db_path
    )

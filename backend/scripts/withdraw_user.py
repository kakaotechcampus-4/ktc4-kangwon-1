import sys

from app.application.errors import AnalysisConflictError
from app.infrastructure.persistence.repository import erasure, requests, users

USAGE = "사용법: python scripts/withdraw_user.py <요청 DB 경로> <계정 번호> [--erase-answers]"
ERASE_ANSWERS = "--erase-answers"


def main(db_path: str, user_id: str, *, erase_answers: bool) -> None:
    if users.get_user(user_id, db_path=db_path) is None:
        sys.exit(f"없는 계정입니다: {user_id}")
    request_ids = _owned_request_ids(user_id, db_path)
    erased = _erase_answers(request_ids, db_path) if erase_answers else 0
    users.delete_user(user_id, db_path=db_path)
    print(f"탈퇴했습니다: 질문 답을 지운 분석 {erased}건, 연결을 끊은 분석 {len(request_ids)}건")


def _owned_request_ids(user_id: str, db_path: str) -> list[str]:
    found: list[str] = []
    while rows := requests.list_user_requests(
        user_id, limit=100, offset=len(found), db_path=db_path
    )[0]:
        found += [row["request_id"] for row in rows]
    return found


def _erase_answers(request_ids: list[str], db_path: str) -> int:
    erased = 0
    for request_id in request_ids:
        try:
            if erasure.erase_user_answers(request_id, db_path=db_path):
                erased += 1
        except AnalysisConflictError as error:
            sys.exit(f"{request_id}: {error} 탈퇴는 하지 않았습니다.")
    return erased


if __name__ == "__main__":
    arguments = [argument for argument in sys.argv[1:] if argument != ERASE_ANSWERS]
    if len(arguments) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    main(*arguments, erase_answers=ERASE_ANSWERS in sys.argv[1:])

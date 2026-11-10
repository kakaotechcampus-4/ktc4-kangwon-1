import sys

from app.application.errors import AnalysisConflictError
from app.infrastructure.persistence.repository import erasure

USAGE = "사용법: python scripts/erase_user_answers.py <요청 DB 경로> <요청 번호>"


def main(db_path: str, request_id: str) -> None:
    try:
        print(erasure.erase_user_answers(request_id, db_path=db_path))
    except AnalysisConflictError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    main(*sys.argv[1:])

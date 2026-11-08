import sys

from app.application.errors import AnalysisConflictError
from app.infrastructure.persistence.repository import erasure


def main(db_path: str, request_id: str) -> None:
    try:
        print(erasure.erase_user_answers(request_id, db_path=db_path))
    except AnalysisConflictError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main(*sys.argv[1:3])

import sys

from app.infrastructure.persistence.repository import erasure


def main(db_path: str, request_id: str) -> None:
    print(erasure.erase_user_answers(request_id, db_path=db_path))


if __name__ == "__main__":
    main(*sys.argv[1:3])

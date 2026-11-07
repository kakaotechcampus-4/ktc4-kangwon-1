import sys

from app.domain.passwords import hash_password
from app.infrastructure.persistence.connection import initialize
from app.infrastructure.persistence.repository import users


def main(db_path: str, email: str, password: str) -> None:
    initialize(db_path)
    if users.get_user_by_email(email, db_path=db_path):
        return
    user_id = users.create_email_user(
        email, hash_password(password), "시험 사용자", db_path=db_path
    )
    users.mark_email_verified(user_id, db_path=db_path)


if __name__ == "__main__":
    main(*sys.argv[1:4])

import sys

from app.db.connection import initialize
from app.db.repository import users
from app.passwords import hash_password


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

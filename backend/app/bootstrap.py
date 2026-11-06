from app.application.ports import storage
from app.infrastructure.persistence.stores import SqliteStorage


def wire() -> None:
    storage.configure(SqliteStorage())


wire()

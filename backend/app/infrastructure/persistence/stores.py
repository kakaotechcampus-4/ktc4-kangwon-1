from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from app.application.ports.storage import (
    AgenticStore,
    FactStore,
    ProvenanceStore,
    RawStore,
    RequestStore,
    ScoreStore,
    SessionStore,
    Stores,
    UserStore,
)
from app.infrastructure.persistence import provenance, raw_capture, raw_query
from app.infrastructure.persistence.connection import connect, initialize
from app.infrastructure.persistence.repository import (
    agentic,
    analyses,
    events,
    facts,
    raw,
    requests,
    scores,
    sessions,
    users,
)
from app.infrastructure.persistence.repository.common import begin_immediate


class _Bound:
    def __init__(self, module: ModuleType, db: Any):
        self._module = module
        self._db = db

    def __getattr__(self, name: str) -> Any:
        return partial(getattr(self._module, name), self._db)


class _Modules:
    def __init__(self, *modules: ModuleType):
        self._modules = modules

    def __getattr__(self, name: str) -> Any:
        for module in self._modules:
            if hasattr(module, name):
                return getattr(module, name)
        raise AttributeError(name)


class SqliteStores:
    def __init__(self, db: Any):
        self.db = db
        self.agentic = cast(AgenticStore, _Bound(agentic, db))
        self.facts = cast(FactStore, _Bound(facts, db))
        self.scores = cast(ScoreStore, _Bound(scores, db))
        self.raw = cast(RawStore, _Bound(raw, db))

    def begin_immediate(self) -> None:
        begin_immediate(self.db)

    def pin_provenance(self, *args: Any, **kwargs: Any) -> Any:
        return provenance.pin_provenance(self.db, *args, **kwargs)


class SqliteStorage:
    requests = cast(RequestStore, _Modules(requests, analyses, events))
    users = cast(UserStore, _Modules(users))
    sessions = cast(SessionStore, _Modules(sessions))
    provenance = cast(ProvenanceStore, _Modules(provenance))

    initialize = staticmethod(initialize)
    capture = staticmethod(raw_capture.capture_scope)
    resume_scope = staticmethod(raw_capture.CaptureScope)
    current_capture = staticmethod(raw_capture.current_capture)
    raw_query = staticmethod(raw_query.run_query)

    @contextmanager
    def stores(self, path: str | Path | None, *, immediate: bool = False) -> Iterator[Stores]:
        with connect(path) as db:
            if immediate:
                begin_immediate(db)
            yield SqliteStores(db)

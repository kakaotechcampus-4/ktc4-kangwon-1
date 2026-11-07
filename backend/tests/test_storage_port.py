import inspect
import unittest

from app.application.ports import storage as port
from app.infrastructure.persistence import provenance
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

BOUND = {
    port.AgenticStore: (agentic,),
    port.FactStore: (facts,),
    port.ScoreStore: (scores,),
    port.RawStore: (raw,),
}
PATHED = {
    port.UserStore: (users,),
    port.SessionStore: (sessions,),
    port.RequestStore: (requests, analyses, events),
    port.ProvenanceStore: (provenance,),
}


def shape(signature, *, skip):
    params = list(signature.parameters.values())[skip:]
    return [(p.name, p.kind, p.default is not inspect.Parameter.empty) for p in params]


def public_functions(modules):
    found = {}
    for module in modules:
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if function.__module__ == module.__name__ and not name.startswith("_"):
                found[name] = function
    found.pop("pin_provenance", None)
    return found


class StoragePortTests(unittest.TestCase):
    def check(self, protocol, modules, *, bound):
        functions = public_functions(modules)
        methods = {
            name
            for name, value in vars(protocol).items()
            if callable(value) and not name.startswith("_")
        }
        self.assertEqual(methods, set(functions), protocol.__name__)
        for name, function in functions.items():
            with self.subTest(store=protocol.__name__, method=name):
                self.assertEqual(
                    shape(inspect.signature(getattr(protocol, name)), skip=1),
                    shape(inspect.signature(function), skip=1 if bound else 0),
                )

    def test_connection_stores_match_repository(self):
        for protocol, modules in BOUND.items():
            self.check(protocol, modules, bound=True)

    def test_path_stores_match_repository(self):
        for protocol, modules in PATHED.items():
            self.check(protocol, modules, bound=False)

    def test_pin_provenance_matches_without_connection(self):
        self.assertEqual(
            shape(inspect.signature(port.Stores.pin_provenance), skip=1),
            shape(inspect.signature(provenance.pin_provenance), skip=1),
        )


if __name__ == "__main__":
    unittest.main()

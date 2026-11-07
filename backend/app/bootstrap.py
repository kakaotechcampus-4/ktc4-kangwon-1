from app.application.ports.decision import decision
from app.application.ports.demo import demo
from app.application.ports.identity import identity
from app.application.ports.llm import llm
from app.application.ports.market import market
from app.application.ports.places import places
from app.application.ports.sites import sites
from app.application.ports.storage import storage


def _storage():
    from app.infrastructure.persistence.stores import SqliteStorage

    return SqliteStorage()


def _market():
    from app.infrastructure.market_data.service import SeoulMarket

    return SeoulMarket()


def _llm():
    from app.infrastructure.llm.service import OpenAICompatibleModel

    return OpenAICompatibleModel()


def _places():
    from app.infrastructure.clients.places import PlaceServices

    return PlaceServices()


def _decision():
    from app.ai.engine import AgenticDecisions

    return AgenticDecisions()


def _sites():
    from app.infrastructure.clients.sites import PublicSites

    return PublicSites()


def _demo():
    from app.infrastructure.mock import MockDemo

    return MockDemo()


def _identity():
    from app.infrastructure.clients.identity import KakaoResendIdentity

    return KakaoResendIdentity()


PROVIDERS = (
    (storage, _storage),
    (market, _market),
    (llm, _llm),
    (places, _places),
    (decision, _decision),
    (sites, _sites),
    (demo, _demo),
    (identity, _identity),
)


def wire() -> None:
    for slot, factory in PROVIDERS:
        slot.provide(factory)


def load_all() -> None:
    for slot, _ in PROVIDERS:
        slot()


wire()

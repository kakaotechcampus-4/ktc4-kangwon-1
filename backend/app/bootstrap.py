from app.ai.engine import AgenticDecisions
from app.application.ports.decision import decision
from app.application.ports.demo import demo
from app.application.ports.identity import identity
from app.application.ports.llm import llm
from app.application.ports.market import market
from app.application.ports.places import places
from app.application.ports.sites import sites
from app.application.ports.storage import storage
from app.infrastructure.clients.identity import KakaoResendIdentity
from app.infrastructure.clients.places import PlaceServices
from app.infrastructure.clients.sites import PublicSites
from app.infrastructure.llm.service import OpenAICompatibleModel
from app.infrastructure.market_data.service import SeoulMarket
from app.infrastructure.mock import MockDemo
from app.infrastructure.persistence.stores import SqliteStorage


def wire() -> None:
    storage.configure(SqliteStorage())
    market.configure(SeoulMarket())
    llm.configure(OpenAICompatibleModel())
    places.configure(PlaceServices())
    decision.configure(AgenticDecisions())
    sites.configure(PublicSites())
    demo.configure(MockDemo())
    identity.configure(KakaoResendIdentity())


wire()

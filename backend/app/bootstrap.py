from app.application.ports.llm import llm
from app.application.ports.market import market
from app.application.ports.storage import storage
from app.infrastructure.llm.service import OpenAICompatibleModel
from app.infrastructure.market_data.service import SeoulMarket
from app.infrastructure.persistence.stores import SqliteStorage


def wire() -> None:
    storage.configure(SqliteStorage())
    market.configure(SeoulMarket())
    llm.configure(OpenAICompatibleModel())


wire()

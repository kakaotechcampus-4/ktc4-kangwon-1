from app.infrastructure.market_data.inputs import format_snapshot
from app.infrastructure.market_data.local.adapter import SOURCE_NAMES, LocalAdapter
from app.infrastructure.market_data.local.score_reference import REFERENCE_VERSION


class SeoulMarket:
    reference_version = REFERENCE_VERSION
    source_names = SOURCE_NAMES
    local_data = staticmethod(LocalAdapter)
    format_snapshot = staticmethod(format_snapshot)

import copy
import json

from app.agents.business_lifecycle import baseline as lifecycle
from app.agents.commercial_area import baseline as density
from app.agents.floating_population import baseline as floating
from backtest.baselines import FLOATING


def file_values(quarter: str = "20234") -> dict:
    values = {
        "quarter": quarter,
        "lifecycle": copy.deepcopy(lifecycle.SEOUL_INDUSTRY_LIFECYCLE_BASELINE),
        "density": copy.deepcopy(density.SEOUL_INDUSTRY_DENSITY_PERCENTILES),
        "floating": {name: copy.deepcopy(getattr(floating, name)) for name in FLOATING},
    }
    return json.loads(json.dumps(values))

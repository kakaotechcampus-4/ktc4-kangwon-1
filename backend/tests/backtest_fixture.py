import copy
import json
from pathlib import Path

from app.agents.business_lifecycle import baseline as lifecycle
from app.agents.commercial_area import baseline as density
from app.agents.commercial_area.client import CSV_FIELDS
from app.agents.floating_population import baseline as floating
from app.agents.floating_population.models import _AGE_KEYS, _DAY_KEYS, TIME_BANDS, PopulationRecord
from app.geo import to_epsg5181
from app.local_data.database import LocalDataDB
from app.schemas import Site
from backtest.baselines import FLOATING
from tests.local_data_fixture import complete_versions


def file_values(quarter: str = "20234") -> dict:
    values = {
        "quarter": quarter,
        "lifecycle": copy.deepcopy(lifecycle.SEOUL_INDUSTRY_LIFECYCLE_BASELINE),
        "density": copy.deepcopy(density.SEOUL_INDUSTRY_DENSITY_PERCENTILES),
        "floating": {name: copy.deepcopy(getattr(floating, name)) for name in FLOATING},
    }
    return json.loads(json.dumps(values))


def build_market(path: Path, quarter: str) -> Site:
    site = Site(
        input_address="서울 테스트", road_address="서울 테스트", latitude=37.5, longitude=127.0
    )
    x, y = to_epsg5181(site.latitude, site.longitude)
    store = dict.fromkeys(CSV_FIELDS.values(), "")
    store.update(
        {
            "상가업소번호": "s1",
            "상호명": "테스트",
            "상권업종대분류코드": "I2",
            "상권업종중분류코드": "I201",
            "상권업종소분류코드": "I20101",
            "시군구코드": "11680",
            "위도": 37.5,
            "경도": 127.0,
        }
    )
    ring = [
        [x - 100, y - 100],
        [x + 100, y - 100],
        [x + 100, y + 100],
        [x - 100, y + 100],
        [x - 100, y - 100],
    ]
    area = {
        "TRDAR_CD": "a",
        "TRDAR_CD_NM": "테스트 상권",
        "XCNTS_VALU": x,
        "YDNTS_VALU": y,
        "RELM_AR": 40000,
        "bbox": [x - 100, y - 100, x + 100, y + 100],
        "rings": [ring],
    }
    floating = {
        "STDR_YYQU_CD": quarter,
        "TRDAR_CD": "a",
        "TOT_FLPOP_CO": 1000,
        "ML_FLPOP_CO": 500,
        "FML_FLPOP_CO": 500,
    }
    floating.update({f"TMZON_{band}_FLPOP_CO": 100 for band in TIME_BANDS})
    floating.update({key: 100 for key in (*_AGE_KEYS.values(), *_DAY_KEYS.values())})
    life = {
        "STDR_YYQU_CD": quarter,
        "TRDAR_CD": "a",
        "SVC_INDUTY_CD": "CS100001",
        "TRDAR_SE_CD": "A",
        "TRDAR_SE_CD_NM": "골목",
        "TRDAR_CD_NM": "테스트",
        "SVC_INDUTY_CD_NM": "한식",
        "SIMILR_INDUTY_STOR_CO": 20,
        "STOR_CO": 20,
        "FRC_STOR_CO": 0,
        "OPBIZ_RT": 0,
        "OPBIZ_STOR_CO": 0,
        "CLSBIZ_RT": 0,
        "CLSBIZ_STOR_CO": 0,
    }
    raw = {"stores": store, "areas": area, "floating": floating, "lifecycle": life}
    for source, kind in (("resident", "REPOP"), ("worker", "WRC_POPLTN")):
        population = dict.fromkeys(PopulationRecord.columns(kind), 100)
        population.update(STDR_YYQU_CD=quarter, TRDAR_CD="a", TRDAR_CD_NM="테스트")
        raw[source] = population
    market = LocalDataDB(path)
    versions = []
    for source, payload in raw.items():
        versions.append(
            market.stage(
                source,
                "" if source == "areas" else quarter,
                [
                    {
                        "row_key": "s1" if source == "stores" else "a",
                        "payload": payload,
                        "area_code": "a",
                        "industry_code": "I201",
                        "district_code": "11680",
                        "latitude": 37.5,
                        "longitude": 127.0,
                    }
                ],
                source,
            )
        )
    market.activate(complete_versions(market, versions, quarter))
    return site

from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from app.agents.business_lifecycle.client import get_recent_quarters, normalize_row
from app.industries.catalog import SEOUL_TO_INDUSTRY

LAST_QUARTER = "20262"


def load_store_data(folder: Path) -> pd.DataFrame:
    paths = sorted(Path(folder).glob("점포_상권_*.csv"))
    if not paths:
        raise FileNotFoundError(f"점포_상권_*.csv가 없습니다: {folder}")
    data = pd.concat(
        [
            pd.read_csv(p, encoding="utf-8-sig", dtype={"STDR_YYQU_CD": str, "TRDAR_CD": str})
            for p in paths
        ],
        ignore_index=True,
    )
    data["INDUSTRY"] = data["SVC_INDUTY_CD"].map(SEOUL_TO_INDUSTRY)
    return data


def quarters_after(base: str, last: str = LAST_QUARTER) -> list[str]:
    year, q = int(base[:4]), int(base[4])
    result: list[str] = []
    while True:
        year, q = (year + 1, 1) if q == 4 else (year, q + 1)
        code = f"{year}{q}"
        if code > last:
            return result
        result.append(code)


def quarters_until(base: str, count: int) -> list[str]:
    return get_recent_quarters(base_quarter=base, count=count)


def api_rows(frame: pd.DataFrame, quarters: Iterable[str]) -> list[dict]:
    wanted = set(quarters)
    part = frame[frame["STDR_YYQU_CD"].isin(wanted)]
    return [normalize_row(r) for r in part.drop(columns=["INDUSTRY"]).to_dict("records")]

import math
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

MIN_STORES = 5
COLUMNS = ["SIMILR_INDUTY_STOR_CO", "CLSBIZ_STOR_CO"]


@dataclass(frozen=True)
class Verdict:
    industry: str
    kind: str
    status: str
    survival: float | None
    seoul: float | None
    area: float | None
    base_stores: float
    correct_vs_seoul: bool | None
    correct_vs_area: bool | None


def _survival_used(
    by_quarter: pd.DataFrame | None, quarters: Iterable[str]
) -> tuple[float | None, list[str]]:
    if by_quarter is None:
        return None, []
    value, used = 1.0, []
    for quarter in quarters:
        if quarter not in by_quarter.index:
            continue
        stores, closed = by_quarter.loc[quarter, COLUMNS]
        if stores <= 0:
            continue
        value *= 1 - min(closed / stores, 1.0)
        used.append(quarter)
    return (value if used else None), used


def _survival(by_quarter: pd.DataFrame | None, quarters: Iterable[str]) -> float | None:
    return _survival_used(by_quarter, quarters)[0]


def _beats(value: float, reference: float, better: bool) -> bool | None:
    if math.isclose(value, reference, rel_tol=1e-9, abs_tol=1e-12):
        return None
    return (value > reference) == better


class StoreTable:
    def __init__(self, data: pd.DataFrame):
        mapped = data.dropna(subset=["INDUSTRY"])
        self.cells = mapped.groupby(["TRDAR_CD", "INDUSTRY", "STDR_YYQU_CD"])[COLUMNS].sum()
        self.seoul = mapped.groupby(["INDUSTRY", "STDR_YYQU_CD"])[COLUMNS].sum()
        self.areas = data.groupby(["TRDAR_CD", "STDR_YYQU_CD"])[COLUMNS].sum()
        self.industries = frozenset(mapped["INDUSTRY"])

    def _cell(self, area: str, industry: str) -> pd.DataFrame | None:
        try:
            return self.cells.loc[(area, industry)]
        except KeyError:
            return None

    def survival(self, area: str, industry: str, quarters: Iterable[str]) -> float | None:
        return _survival(self._cell(area, industry), quarters)

    def seoul_survival(self, industry: str, quarters: Iterable[str]) -> float | None:
        try:
            return _survival(self.seoul.loc[industry], quarters)
        except KeyError:
            return None

    def area_survival(self, area: str, quarters: Iterable[str]) -> float | None:
        try:
            return _survival(self.areas.loc[area], quarters)
        except KeyError:
            return None

    def stores_in(self, area: str, industry: str, quarter: str) -> float:
        cell = self._cell(area, industry)
        if cell is None or quarter not in cell.index:
            return 0.0
        return float(cell.loc[quarter, "SIMILR_INDUTY_STOR_CO"])

    def stores_at(self, area: str, quarter: str) -> dict[str, float]:
        result = {}
        for industry in self.industries:
            cell = self._cell(area, industry)
            if cell is not None and quarter in cell.index:
                result[industry] = float(cell.loc[quarter, "SIMILR_INDUTY_STOR_CO"])
        return result

    def judge(
        self, area: str, industry: str, kind: str, base: str, quarters: Iterable[str]
    ) -> Verdict:
        if industry not in self.industries:
            return Verdict(industry, kind, "unscorable", None, None, None, 0.0, None, None)
        stores = self.stores_in(area, industry, base)
        if stores < MIN_STORES:
            return Verdict(industry, kind, "absent", None, None, None, stores, None, None)
        value, used = _survival_used(self._cell(area, industry), quarters)
        seoul = self.seoul_survival(industry, used)
        local = self.area_survival(area, used)
        if value is None or seoul is None or local is None:
            return Verdict(industry, kind, "pending", value, seoul, local, stores, None, None)
        better = kind == "recommended"
        return Verdict(
            industry,
            kind,
            "scored",
            value,
            seoul,
            local,
            stores,
            _beats(value, seoul, better),
            _beats(value, local, better),
        )

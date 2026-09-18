"""분석 반경과 겹치는 서울시 상권을 찾는다.

왜 필요한가 — 같은 LQ 값의 의미가 상권 유형에 따라 뒤집히기 때문이다(B2: "특화는 발달상권에서
생존 위험을 높인다"). 유형을 모르면 LQ 를 단독 근거로 쓸 수 없다.

자료는 `data/seoul_trade_areas.csv` 1,650행이다. 분기마다
`examples/fetch_seoul_trade_areas.py` 로 갱신한다. **런타임에 서울시 API 를 부르지 않는다.**

⚠️ **서울시 자료라 서울 밖에서는 빈 목록이다.** 우리 에이전트는 전국을 받는다.

## 겹침 판정이 근사인 이유

영역-상권 API 가 폴리곤을 주지 않고 중심점과 면적만 준다. 그래서 상권을 같은 면적의 원으로
근사한다(`equivalent_radius_m = sqrt(area / pi)`). 실제 상권은 길을 따라 길쭉해서 원과 다르다.

그래서 **하나로 줄이지 않고 걸린 것을 전부 낸다.** 접경지에서 한 끗 차로 유형이 뒤집히는 걸
우리가 임의로 정하지 않기 위해서다. 판단은 결정 에이전트가 한다.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.geo import to_epsg5181

from .config import PACKAGE_DIR
from .schemas import TradeArea

DATA_PATH = PACKAGE_DIR / "data" / "seoul_trade_areas.csv"
REQUIRED_COLUMNS = {"code", "name", "kind", "signgu", "x", "y", "area_m2"}

# 등가 반지름을 반경의 절반까지만 인정한다. 큰 상권이 멀리서도 걸리는 걸 막는 상한이다.
MAX_REACH_RATIO = 0.5
MAX_RESULTS = 8


@dataclass(frozen=True, slots=True)
class SeoulTradeArea:
    code: str
    name: str
    kind: str
    signgu: str
    adstrd: str
    x: float
    y: float
    area_m2: float

    @property
    def equivalent_radius_m(self) -> float:
        return math.sqrt(self.area_m2 / math.pi)


@lru_cache(maxsize=1)
def load_trade_areas(path: Path = DATA_PATH) -> tuple[SeoulTradeArea, ...]:
    """자료가 없으면 빈 튜플. 서울 밖과 같은 취급이라 분석은 그대로 나간다."""
    if not path.exists():
        return ()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            return ()
        rows = []
        for row in reader:
            try:
                area = float(row["area_m2"])
                rows.append(
                    SeoulTradeArea(
                        code=row["code"].strip(),
                        name=row["name"].strip(),
                        kind=row["kind"].strip(),
                        signgu=row.get("signgu", "").strip(),
                        adstrd=row.get("adstrd", "").strip(),
                        x=float(row["x"]),
                        y=float(row["y"]),
                        area_m2=area,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return tuple(rows)


def build_trade_areas(latitude: float, longitude: float, radius_m: int) -> list[TradeArea]:
    """분석 반경과 겹치는 상권을 가까운 순으로. 서울 밖이면 빈 목록."""
    areas = load_trade_areas()
    if not areas:
        return []

    x, y = to_epsg5181(latitude, longitude)
    reach_cap = radius_m * MAX_REACH_RATIO

    hits = []
    for area in areas:
        distance = math.hypot(area.x - x, area.y - y)
        if distance - min(area.equivalent_radius_m, reach_cap) <= radius_m:
            hits.append((distance, area))
    hits.sort(key=lambda hit: (hit[0], hit[1].code))

    return [
        TradeArea(
            code=area.code,
            name=area.name,
            kind=area.kind or None,
            signgu=area.signgu or None,
            distance_m=round(distance, 1),
            area_m2=round(area.area_m2, 1),
            equivalent_radius_m=round(area.equivalent_radius_m, 1),
        )
        for distance, area in hits[:MAX_RESULTS]
    ]

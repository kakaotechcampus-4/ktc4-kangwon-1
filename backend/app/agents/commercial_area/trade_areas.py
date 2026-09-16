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

from .config import PACKAGE_DIR
from .schemas import TradeArea

DATA_PATH = PACKAGE_DIR / "data" / "seoul_trade_areas.csv"
REQUIRED_COLUMNS = {"code", "name", "kind", "signgu", "x", "y", "area_m2"}

# 등가 반지름을 반경의 절반까지만 인정한다. 큰 상권이 멀리서도 걸리는 걸 막는 상한이다.
MAX_REACH_RATIO = 0.5
MAX_RESULTS = 8

# ── EPSG:5181 (중부원점 TM) ─────────────────────────────────
# 서울시 상권 좌표가 이 계다. 변환이 한 방향뿐이라 pyproj(26.5MB) 대신 투영식을 직접 쓴다.
# 같은 식이 floating_population/geo.py 에도 있다 — 에이전트끼리 import 하지 않기로 해서 두 벌이다.
_LAT0 = math.radians(38.0)
_LON0 = math.radians(127.0)
_FALSE_EASTING = 200000.0
_FALSE_NORTHING = 500000.0

# GRS80
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = 2 * _F - _F * _F
_EP2 = _E2 / (1 - _E2)


def _meridian_arc(phi: float) -> float:
    return _A * (
        (1 - _E2 / 4 - 3 * _E2**2 / 64 - 5 * _E2**3 / 256) * phi
        - (3 * _E2 / 8 + 3 * _E2**2 / 32 + 45 * _E2**3 / 1024) * math.sin(2 * phi)
        + (15 * _E2**2 / 256 + 45 * _E2**3 / 1024) * math.sin(4 * phi)
        - (35 * _E2**3 / 3072) * math.sin(6 * phi)
    )


_M0 = _meridian_arc(_LAT0)


def to_epsg5181(latitude: float, longitude: float) -> tuple[float, float]:
    """WGS84 위경도 → EPSG:5181 (x, y) 미터."""
    phi = math.radians(latitude)
    lam = math.radians(longitude)

    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    tan_phi = math.tan(phi)

    n = _A / math.sqrt(1 - _E2 * sin_phi**2)
    t = tan_phi**2
    c = _EP2 * cos_phi**2
    a_ = (lam - _LON0) * cos_phi

    x = _FALSE_EASTING + n * (
        a_ + (1 - t + c) * a_**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * _EP2) * a_**5 / 120
    )
    y = _FALSE_NORTHING + (
        _meridian_arc(phi)
        - _M0
        + n
        * tan_phi
        * (
            a_**2 / 2
            + (5 - 4 * t + 9 * c + 4 * c**2) * a_**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * _EP2) * a_**6 / 720
        )
    )
    return x, y


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

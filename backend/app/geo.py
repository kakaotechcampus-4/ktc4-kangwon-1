"""WGS84 위경도 → EPSG:5181 평면좌표. 세 에이전트가 함께 쓴다.

팀 계약(`app.schemas.Site`)은 위경도를 주는데, 서울시 상권영역 데이터의 좌표
(`XCNTS_VALUE`/`YDNTS_VALUE`)는 EPSG:5181(중부원점 TM, 미터)이다. 반경 판정을 하려면 둘을
같은 좌표계로 맞춰야 하고, 미터 좌표로 맞추면 거리 계산이 `math.hypot` 한 줄로 끝난다.

**pyproj 를 쓰지 않고 투영식을 직접 구현한다.** 변환이 이 한 방향 하나뿐이라 PROJ 바이너리
의존을 늘릴 값어치가 없다고 봤다. 정확도는 아래 검증으로 확인했다.

정확도 검증 (로컬 도구 `tools-local/check_tm.py`):
- 오금로 404 WGS84(37.5183291, 127.1051123) → (209292.3, 446543.6).
  이전 세션에 pyproj 로 변환해둔 값 (209292, 446544) 과 **0.5m** 차이.
- 독립 검증 — 랜드마크 위경도를 변환해 상권영역 API 실좌표와 대조:
  강동구청→`강동구청` 91m · 암사역→`암사역` 139m · 역삼역→`역삼역` 53m.
  (잔차는 랜드마크 좌표 자체의 근사치와 상권 중심점 위치 차이다)

타원체는 GRS80, 데이텀 이동 없음 — 위 검증에서 Bessel(5.4m)·데이텀 이동 적용(350m+)보다
정확했다. 서울시 데이터가 실제로 이 정의로 만들어져 있다는 뜻이다.

## 왜 에이전트 밖에 있나

같은 식이 세 에이전트에 각자 한 벌씩 있었다(`commercial_area/trade_areas.py`,
`floating_population/geo.py`, `business_lifecycle/area_resolver.py`). 에이전트끼리 import 하지
않기로 한 합의를 중복으로 지킨 것인데, 그 합의가 막는 것은 에이전트 **사이의** 의존이지 공용
모듈이 아니다. `app/schemas.py`·`app/address.py` 와 같은 자리로 올린다.

세 사본 중 y 4차항 계수가 `business_lifecycle` 만 달랐다. 여기서는 Snyder,
*Map Projections — A Working Manual* 식 (8-9) 의 `(5 - t + 9c + 4c²)` 를 쓴다. 나머지 둘은
`5 - 4t` 였고, 차이는 서울에서 1.6e-6 m, 중앙자오선에서 먼 부산에서 0.21m 다.
"""

from __future__ import annotations

import math

# EPSG:5181 — 중부원점 TM
_LAT0 = math.radians(38.0)
_LON0 = math.radians(127.0)
_K0 = 1.0
_FALSE_EASTING = 200000.0
_FALSE_NORTHING = 500000.0

# GRS80
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = 2 * _F - _F * _F
_EP2 = _E2 / (1 - _E2)


def _meridian_arc(phi: float) -> float:
    """적도에서 위도 phi 까지의 자오선 호 길이(미터)."""
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

    x = _FALSE_EASTING + _K0 * n * (
        a_ + (1 - t + c) * a_**3 / 6 + (5 - 18 * t + t**2 + 72 * c - 58 * _EP2) * a_**5 / 120
    )
    y = _FALSE_NORTHING + _K0 * (
        _meridian_arc(phi)
        - _M0
        + n
        * tan_phi
        * (
            a_**2 / 2
            + (5 - t + 9 * c + 4 * c**2) * a_**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * _EP2) * a_**6 / 720
        )
    )
    return x, y

"""WGS84 위경도 → EPSG:5181 평면좌표.

팀 계약(`app.schemas.Site`)은 위경도를 주는데, 서울시 상권영역 데이터의 좌표
(`XCNTS_VALUE`/`YDNTS_VALUE`)는 EPSG:5181(중부원점 TM, 미터)이다. 반경 판정을 하려면 둘을
같은 좌표계로 맞춰야 하고, 미터 좌표로 맞추면 거리 계산이 `math.hypot` 한 줄로 끝난다.

**pyproj 를 쓰지 않고 투영식을 직접 구현한다.** 변환이 이 한 방향 하나뿐인데 pyproj 는
26.5MB(PROJ 데이터 포함)라 비용이 맞지 않는다.

정확도 검증 (`tools-local/check_tm.py`):
- 오금로 404 WGS84(37.5183291, 127.1051123) → (209292.3, 446543.6).
  이전 세션에 pyproj 로 변환해둔 값 (209292, 446544) 과 **0.5m** 차이.
- 독립 검증 — 랜드마크 위경도를 변환해 상권영역 API 실좌표와 대조:
  강동구청→`강동구청` 91m · 암사역→`암사역` 139m · 역삼역→`역삼역` 53m.
  (잔차는 랜드마크 좌표 자체의 근사치와 상권 중심점 위치 차이다)

타원체는 GRS80, 데이텀 이동 없음 — 위 검증에서 Bessel(5.4m)·데이텀 이동 적용(350m+)보다
정확했다. 서울시 데이터가 실제로 이 정의로 만들어져 있다는 뜻이다.
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
            + (5 - 4 * t + 9 * c + 4 * c**2) * a_**4 / 24
            + (61 - 58 * t + t**2 + 600 * c - 330 * _EP2) * a_**6 / 720
        )
    )
    return x, y


def circle_overlap_ratio(distance_m: float, radius_m: float, area_radius_m: float) -> float:
    """상권 구역(면적 등가원) 중 분석 반경 안에 들어온 **면적 비율** (0~1).

    반경별 인구를 낼 때 쓴다. 상권 단위 자료는 구역 전체의 합계만 주므로, 반경으로 잘라
    "반경 300m 안의 인구" 를 구하려면 구역의 일부만 세는 수밖에 없다. 여기서는 **상권 안에서
    인구가 고르게 분포한다고 가정**하고 겹친 면적 비율만큼 인구를 안분한다. 가정이 들어가는
    자리이므로 `data.radius_profile.method` 에 그대로 적어 둔다.

    왜 이 방법이 필요한가 — 대표 점이 반경 안이면 통째로 세는 방식은 반경을 줄일수록
    쓸모없어진다(실측: 반경 100m 에서 4개 지점 중 3곳이 상권 0곳, 테헤란로는 상권 1곳이
    100% 인데 그 상권의 실제 도달 거리가 483m). 면적 안분은 반경이 줄면 값도 부드럽게 준다.

    면적이 0 인 상권(등가 반지름 0)은 점으로 보고 반경 안이면 1, 밖이면 0 을 준다.
    """
    if area_radius_m <= 0:
        return 1.0 if distance_m <= radius_m else 0.0
    if distance_m >= radius_m + area_radius_m:
        return 0.0
    if distance_m <= abs(radius_m - area_radius_m):
        # 한쪽이 다른 쪽을 완전히 품는다. 상권이 더 작으면 전부 포함(1.0),
        # 반경이 더 작으면 반경 원의 면적만큼만 포함된다.
        return 1.0 if area_radius_m <= radius_m else (radius_m / area_radius_m) ** 2

    # 두 원의 렌즈꼴 교집합 면적 (표준 공식)
    d, r1, r2 = distance_m, radius_m, area_radius_m
    a1 = math.acos(max(-1.0, min(1.0, (d**2 + r1**2 - r2**2) / (2 * d * r1))))
    a2 = math.acos(max(-1.0, min(1.0, (d**2 + r2**2 - r1**2) / (2 * d * r2))))
    lens = r1**2 * (a1 - math.sin(2 * a1) / 2) + r2**2 * (a2 - math.sin(2 * a2) / 2)
    return max(0.0, min(1.0, lens / (math.pi * r2**2)))

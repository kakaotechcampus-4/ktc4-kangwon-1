"""반경과 상권 구역의 겹침 기하.

상권영역 API 가 폴리곤을 주지 않고 중심점과 면적만 준다. 그래서 구역을 **면적 등가원**으로
근사해 반경과 겹치는지를 판정하고, 반경별 인구를 낼 때는 겹친 면적 비율만큼 안분한다.

WGS84 → EPSG:5181 변환은 `app/geo.py` 에 있다. 세 에이전트가 같이 쓰는 코드라 그쪽으로
올렸고, pyproj 를 쓰지 않는 근거와 정확도 검증 기록도 거기 있다.
"""

from __future__ import annotations

import math

from .models import TrdarArea


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


_MAX_AREA_REACH_RATIO = 0.5


def _overlapping_areas(
    areas: list[TrdarArea], x: float, y: float, radius_m: float
) -> list[tuple[TrdarArea, float]]:
    """반경과 구역이 겹치는 상권을 (상권, 대표점까지의 거리) 로 가까운 순 반환.

    상권영역 API 가 폴리곤을 주지 않아 구역을 **면적 등가원**으로 근사하고, 대표 점까지의
    거리에서 등가 반지름을 빼서 반경과 비교한다. **단 등가 반지름은 반경의 절반까지만
    인정한다**(`_MAX_AREA_REACH_RATIO`).

    상한이 왜 필요한지는 실데이터로 확인했다(2026Q2, 반경 500m 기준):

    | 기준 | 서교동 분석 | 역삼1동 최대 단일 기여 | 도달 거리 |
    | --- | --- | --- | --- |
    | 대표 점 거리만 | `서교동(홍대)` 상권 누락 | 역삼역 68.1% | 611m |
    | 등가 반지름 전부 인정 | 포함 | **강남역 37.6%** | 1,287m |
    | 등가 반지름 상한 절반 | 포함 | 역삼역 37.8% | 870m |

    - 상한이 없으면 등가 반지름이 400m 대인 발달상권이 판정 반경을 두 배로 늘린다. 실제로
      843m 떨어진 `강남역` 상권이 테헤란로 분석에 들어와 전체의 37.6% 를 차지했다.
    - 반대로 대표 점 거리만 보면 큰 상권이 통째로 빠진다(등가 반지름 중위 151m, 상위 10% 는
      255m 이상). 서교동(홍대) 분석에서 `서교동(홍대)` 상권 자체가 빠지는 결과가 나왔다.
    - 상한을 반경의 1/3 로 더 조이면 그 누락이 다시 생긴다. 절반이 두 결함을 모두 피하는
      지점이다.

    집계 범위는 여전히 반경보다 넓다(반경에 걸친 상권은 구역 전체가 들어온다). 그래서 scope
    와 warnings 에 실제 도달 거리를 적는다. 좌표계가 EPSG:5181(미터) 이라 유클리드 거리를
    그대로 쓴다.
    """
    max_reach = radius_m * _MAX_AREA_REACH_RATIO
    hits = []
    for area in areas:
        distance = math.hypot(area.x - x, area.y - y)
        if distance - min(area.equivalent_radius_m, max_reach) <= radius_m:
            hits.append((area, distance))
    return sorted(hits, key=lambda h: h[1])

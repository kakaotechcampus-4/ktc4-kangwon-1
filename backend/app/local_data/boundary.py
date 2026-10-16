"""서울 시도 경계의 수동 수집과 반경 포함 여부를 확인합니다."""

from app.agents.business_lifecycle.area_resolver import (
    polygon_contains_point,
    polygon_distance_m,
)
from app.education_zone import VWORLD_DATA_URL, EducationZoneSettings
from app.geo import to_epsg5181
from app.local_data.database import DataValidationError


async def fetch_boundary(http):
    settings = EducationZoneSettings.from_env()
    key = settings.api_key
    if not isinstance(key, str) or not key.strip():
        raise DataValidationError("V-World 키 설정 없음")
    response = await http.get(
        VWORLD_DATA_URL,
        headers={"Referer": settings.referer.strip()},
        timeout=settings.request_timeout_s,
        params={
            "service": "data",
            "request": "GetFeature",
            "version": "2.0",
            "data": "LT_C_ADSIDO_INFO",
            "key": key.strip(),
            "attrFilter": "ctp_kor_nm:=:서울특별시",
            "format": "json",
            "errorFormat": "json",
            "page": 1,
            "crs": "EPSG:4326",
            "size": 10,
            "geometry": "true",
            "attribute": "true",
        },
    )
    response.raise_for_status()
    body = response.json().get("response", {})
    if body.get("status") != "OK":
        code = body.get("error", {}).get("code", "UNKNOWN")
        raise DataValidationError(f"V-World 경계 조회 실패: {code}")
    features = body.get("result", {}).get("featureCollection", {}).get("features", [])
    if len(features) != 1 or features[0].get("properties", {}).get("ctp_kor_nm") != "서울특별시":
        raise DataValidationError("서울 시도 경계 1개가 확인되지 않았습니다.")
    geometry = features[0].get("geometry", {})
    if geometry.get("type") not in ("Polygon", "MultiPolygon") or not geometry.get("coordinates"):
        raise DataValidationError("서울 경계 폴리곤 없음")
    return [{"row_key": "11", "payload": {"geometry": geometry, "layer": "LT_C_ADSIDO_INFO"}}]


def boundary_limitations(rows, latitude, longitude, radius):
    if not rows:
        return ["서울 밖 점포 미반영", "서울 행정경계 도형 미보유: 반경 경계 교차는 미확인"]
    x, y = to_epsg5181(latitude, longitude)
    for row in rows:
        geometry = row["geometry"]
        polygons = (
            [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        )
        for polygon in polygons:
            rings = [[to_epsg5181(lat, lon) for lon, lat in ring] for ring in polygon]
            if polygon_contains_point(rings, x, y) and polygon_distance_m(rings, x, y) >= radius:
                return []
    return ["서울 밖 점포 미반영"]

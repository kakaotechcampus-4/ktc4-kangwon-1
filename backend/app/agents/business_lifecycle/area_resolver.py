"""좌표를 서울시 공식 상권영역 polygon으로 해석합니다."""

from __future__ import annotations

import math
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from app.geo import to_epsg5181
from app.schemas import Site

from .config import Settings

Point = tuple[float, float]
Ring = Sequence[Point]


@dataclass(frozen=True)
class BusinessArea:
    area_code: str
    area_name: str
    area_type_code: str | None
    area_type_name: str | None
    district_code: str | None
    district_name: str | None
    dong_code: str | None
    dong_name: str | None
    x: float
    y: float
    warning: str = ""
    selection_method: str = "포함"
    selection_distance_m: float = 0.0


@dataclass(frozen=True)
class ShapeFeature:
    attributes: Mapping[str, str | None]
    bbox: tuple[float, float, float, float]
    rings: tuple[tuple[Point, ...], ...]


@dataclass(frozen=True)
class DbfField:
    name: str
    field_type: str
    length: int


class BusinessAreaNoDataError(RuntimeError):
    """포함 상권과 300m 이내 최근접 상권이 모두 없습니다."""


class BusinessAreaResolverError(RuntimeError):
    """상권영역 SHP 파일을 읽거나 해석하지 못했습니다."""


def resolve_area(site: Site, settings: Settings | None = None) -> BusinessArea:
    """포함 상권 우선, 없으면 경계가 300m 이내인 최근접 상권을 찾습니다."""
    settings = settings or Settings.from_env()
    return resolve_features(site, load_shape_features(settings.area_shape_path))


def resolve_features(site: Site, features: Sequence[ShapeFeature]) -> BusinessArea:
    """이미 읽은 영역(로컬 DB 포함)에 기존 포함/최근접 판정을 적용합니다."""
    target_x, target_y = to_epsg5181(site.latitude, site.longitude)
    matches = [
        feature
        for feature in features
        if _bbox_contains(feature.bbox, target_x, target_y)
        and polygon_contains_point(feature.rings, target_x, target_y)
    ]

    distance = 0.0
    method = "포함"
    if matches:
        feature = min(matches, key=_feature_area)
    else:
        nearest = [
            (polygon_distance_m(f.rings, target_x, target_y), f)
            for f in features
            if _bbox_contains(
                (f.bbox[0] - 300, f.bbox[1] - 300, f.bbox[2] + 300, f.bbox[3] + 300),
                target_x,
                target_y,
            )
        ]
        nearest = [(d, f) for d, f in nearest if d <= 300]
        if not nearest:
            raise BusinessAreaNoDataError(
                "입력 좌표를 포함하거나 경계가 300m 이내인 서울시 상권이 없습니다."
            )
        distance, feature = min(
            nearest,
            key=lambda item: (
                item[0],
                _feature_area(item[1]),
                str(item[1].attributes.get("TRDAR_CD")),
            ),
        )
        method = "최근접"

    area = _feature_to_business_area(feature, target_x, target_y)
    if area is None:
        raise BusinessAreaResolverError(
            "좌표가 포함된 상권 polygon에 TRDAR_CD 또는 TRDAR_CD_NM 속성이 없습니다."
        )
    return replace(
        area,
        selection_method=method,
        selection_distance_m=round(distance, 2),
        warning=(
            " ".join(
                text
                for text in (
                    area.warning,
                    f"상권 선택={method}, 경계 거리={distance:.2f}m. "
                    "최근접 상권은 주소를 포함하지 않는 주변 상권입니다.",
                )
                if text
            )
            if method == "최근접"
            else area.warning
        ),
    )


def polygon_distance_m(rings: Sequence[Ring], x: float, y: float) -> float:
    """EPSG:5181에서 입력점과 폴리곤 경계 선분의 최소 거리(m)."""
    distances = []
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
            dx, dy = x2 - x1, y2 - y1
            length2 = dx * dx + dy * dy
            t = min(1.0, max(0.0, ((x - x1) * dx + (y - y1) * dy) / length2)) if length2 else 0.0
            distances.append(math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return min(distances, default=float("inf"))


def required_shape_paths(path: Path) -> list[Path]:
    return [
        path.with_suffix(".shp"),
        path.with_suffix(".shx"),
        path.with_suffix(".dbf"),
        path.with_suffix(".prj"),
    ]


def load_shape_features(shape_path: Path) -> tuple[ShapeFeature, ...]:
    shape_path = shape_path.resolve()
    paths = required_shape_paths(shape_path)
    missing = [path for path in paths if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise BusinessAreaResolverError(
            f"서울시 공식 상권영역 SHP 구성 파일이 없습니다. 필요한 파일: {missing_text}"
        )

    signature = tuple((stat.st_mtime_ns, stat.st_size) for stat in (path.stat() for path in paths))
    # 속성과 중첩 좌표까지 읽기 전용이므로 요청마다 복사하지 않습니다.
    return _load_cached_shapes(shape_path, signature)


@lru_cache(maxsize=4)
def _load_cached_shapes(
    shape_path: Path, signature: tuple[tuple[int, int], ...]
) -> tuple[ShapeFeature, ...]:
    """구성 파일이 변경되면 새 키로 다시 읽습니다."""

    _validate_projection(shape_path.with_suffix(".prj"))
    attributes = read_dbf(shape_path.with_suffix(".dbf"))
    polygons = read_polygon_shapes(shape_path.with_suffix(".shp"))

    if len(attributes) != len(polygons):
        raise BusinessAreaResolverError(
            "SHP polygon 수와 DBF 속성 행 수가 일치하지 않습니다. "
            f"SHP={len(polygons)}, DBF={len(attributes)}"
        )

    return tuple(
        ShapeFeature(
            attributes=MappingProxyType(dict(attribute)),
            bbox=polygon[0],
            rings=tuple(tuple(ring) for ring in polygon[1]),
        )
        for attribute, polygon in zip(attributes, polygons, strict=True)
        if attribute is not None and polygon is not None
    )


def read_polygon_shapes(
    path: Path,
) -> list[tuple[tuple[float, float, float, float], list[Ring]] | None]:
    data = path.read_bytes()
    if len(data) < 100:
        raise BusinessAreaResolverError("SHP 파일 헤더가 너무 짧습니다.")

    file_code = struct.unpack(">i", data[:4])[0]
    if file_code != 9994:
        raise BusinessAreaResolverError("SHP 파일 형식이 아닙니다.")

    offset = 100
    polygons: list[tuple[tuple[float, float, float, float], list[Ring]] | None] = []

    while offset < len(data):
        if offset + 8 > len(data):
            raise BusinessAreaResolverError("SHP 레코드 헤더가 손상되었습니다.")

        content_length_words = struct.unpack(">i", data[offset + 4 : offset + 8])[0]
        content_start = offset + 8
        content_end = content_start + content_length_words * 2
        if content_length_words < 2 or content_end > len(data):
            raise BusinessAreaResolverError("SHP 레코드 길이가 파일 크기를 초과합니다.")

        shape_type = struct.unpack("<i", data[content_start : content_start + 4])[0]
        if shape_type == 0:
            polygons.append(None)
            offset = content_end
            continue
        if shape_type not in {5, 15, 25}:
            raise BusinessAreaResolverError(f"지원하지 않는 SHP shape type입니다: {shape_type}")

        polygons.append(_read_polygon_record(data[content_start:content_end]))
        offset = content_end

    return polygons


def _read_polygon_record(data: bytes) -> tuple[tuple[float, float, float, float], list[Ring]]:
    if len(data) < 44:
        raise BusinessAreaResolverError("polygon 레코드가 너무 짧습니다.")

    xmin, ymin, xmax, ymax = struct.unpack("<4d", data[4:36])
    num_parts, num_points = struct.unpack("<2i", data[36:44])
    if num_parts <= 0 or num_points < 4:
        raise BusinessAreaResolverError("polygon 구성 수가 올바르지 않습니다.")
    parts_start = 44
    points_start = parts_start + num_parts * 4
    points_end = points_start + num_points * 16
    if points_end > len(data):
        raise BusinessAreaResolverError("polygon 좌표 배열이 손상되었습니다.")

    parts = list(struct.unpack(f"<{num_parts}i", data[parts_start:points_start]))
    if parts[0] != 0 or any(
        start < 0 or start >= num_points or (index > 0 and start <= parts[index - 1])
        for index, start in enumerate(parts)
    ):
        raise BusinessAreaResolverError("polygon part offset이 올바르지 않습니다.")
    points = [
        struct.unpack("<2d", data[points_start + index * 16 : points_start + (index + 1) * 16])
        for index in range(num_points)
    ]

    rings: list[Ring] = []
    for index, start in enumerate(parts):
        end = parts[index + 1] if index + 1 < len(parts) else num_points
        ring = [(float(x), float(y)) for x, y in points[start:end]]
        if len(ring) < 4 or ring[0] != ring[-1]:
            raise BusinessAreaResolverError("polygon ring의 좌표가 부족합니다.")
        rings.append(ring)

    return (xmin, ymin, xmax, ymax), rings


def read_dbf(path: Path) -> list[dict[str, str | None] | None]:
    data = path.read_bytes()
    if len(data) < 32:
        raise BusinessAreaResolverError("DBF 파일 헤더가 너무 짧습니다.")

    record_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]
    fields = _read_dbf_fields(data, header_length)
    records: list[dict[str, str | None] | None] = []
    offset = header_length

    for _ in range(record_count):
        record = data[offset : offset + record_length]
        offset += record_length
        if len(record) < record_length:
            raise BusinessAreaResolverError("DBF 레코드 길이가 파일 크기를 초과합니다.")
        if record[:1] == b"*":
            records.append(None)
            continue
        records.append(_read_dbf_record(record[1:], fields))

    return records


def _read_dbf_fields(data: bytes, header_length: int) -> list[DbfField]:
    fields: list[DbfField] = []
    offset = 32

    while offset + 32 <= header_length:
        descriptor = data[offset : offset + 32]
        if descriptor[0] == 0x0D:
            break
        raw_name = descriptor[:11].split(b"\x00", 1)[0]
        name = _decode_dbf_text(raw_name)
        fields.append(
            DbfField(
                name=name,
                field_type=chr(descriptor[11]),
                length=descriptor[16],
            )
        )
        offset += 32

    if not fields:
        raise BusinessAreaResolverError("DBF 속성 필드를 찾지 못했습니다.")
    return fields


def _read_dbf_record(data: bytes, fields: list[DbfField]) -> dict[str, str | None]:
    row: dict[str, str | None] = {}
    offset = 0

    for field in fields:
        raw_value = data[offset : offset + field.length]
        offset += field.length
        value = _decode_dbf_text(raw_value).strip()
        row[field.name] = value or None

    return row


def _decode_dbf_text(value: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def _validate_projection(path: Path) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    normalized = text.upper()
    if "KOREA" not in normalized and "TRANSVERSE_MERCATOR" not in normalized:
        raise BusinessAreaResolverError(
            "상권영역 PRJ 파일이 서울시 EPSG:5181 계열 좌표계로 보이지 않습니다."
        )


def polygon_contains_point(rings: Sequence[Ring], x: float, y: float) -> bool:
    inside = False

    for ring in rings:
        if _point_on_ring_boundary(ring, x, y):
            return True
        if _ring_contains_point(ring, x, y):
            inside = not inside

    return inside


def _ring_contains_point(ring: Ring, x: float, y: float) -> bool:
    inside = False
    previous_x, previous_y = ring[-1]

    for current_x, current_y in ring:
        crosses = (current_y > y) != (previous_y > y)
        if crosses:
            slope_x = (previous_x - current_x) * (y - current_y)
            intersection_x = slope_x / (previous_y - current_y) + current_x
            if x < intersection_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y

    return inside


def _point_on_ring_boundary(ring: Ring, x: float, y: float) -> bool:
    previous_x, previous_y = ring[-1]

    for current_x, current_y in ring:
        if _point_on_segment(previous_x, previous_y, current_x, current_y, x, y):
            return True
        previous_x, previous_y = current_x, current_y

    return False


def _point_on_segment(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    x: float,
    y: float,
) -> bool:
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if not math.isclose(cross, 0.0, abs_tol=1e-7):
        return False
    return min(x1, x2) - 1e-7 <= x <= max(x1, x2) + 1e-7 and (
        min(y1, y2) - 1e-7 <= y <= max(y1, y2) + 1e-7
    )


def _bbox_contains(bbox: tuple[float, float, float, float], x: float, y: float) -> bool:
    xmin, ymin, xmax, ymax = bbox
    return xmin <= x <= xmax and ymin <= y <= ymax


def _feature_area(feature: ShapeFeature) -> float:
    # SHP는 외곽이 시계 방향, 구멍이 반시계 방향입니다. 링 순서와 무관하게
    # 부호를 유지해 더해야 구멍을 빼고 독립 외곽·구멍 안의 섬을 더합니다.
    return abs(sum(_ring_area(ring) for ring in feature.rings))


def _ring_area(ring: Ring) -> float:
    total = 0.0
    previous_x, previous_y = ring[-1]
    for current_x, current_y in ring:
        total += previous_x * current_y - current_x * previous_y
        previous_x, previous_y = current_x, current_y
    return total / 2


def _feature_to_business_area(
    feature: ShapeFeature,
    target_x: float,
    target_y: float,
) -> BusinessArea | None:
    row = feature.attributes
    area_code = _clean(row, "TRDAR_CD", "TRDAR_CD_1", "상권_코드")
    area_name = _clean(row, "TRDAR_CD_NM", "TRDAR_CD_N", "TRDAR_NM", "상권_코드_명")
    if not area_code or not area_name:
        return None

    return BusinessArea(
        area_code=area_code,
        area_name=area_name,
        area_type_code=_clean(row, "TRDAR_SE_CD", "TRDAR_SE_C", "상권_구분_코드"),
        area_type_name=_clean(row, "TRDAR_SE_CD_NM", "TRDAR_SE_1", "상권_구분_코드_명"),
        district_code=_clean(row, "SIGNGU_CD", "시군구_코드"),
        district_name=_clean(row, "SIGNGU_CD_NM", "SIGNGU_CD_", "시군구_코드_명"),
        dong_code=_clean(row, "ADSTRD_CD", "행정동_코드"),
        dong_name=_clean(row, "ADSTRD_CD_NM", "ADSTRD_CD_", "행정동_코드_명"),
        x=target_x,
        y=target_y,
    )


def _clean(row: Mapping[str, str | None], *keys: str) -> str | None:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for key in keys:
        value = row.get(key) or normalized.get(_normalize_key(key))
        if value:
            text = value.strip()
            if text:
                return text
    return None


def _normalize_key(key: str) -> str:
    return key.upper().replace("_", "")

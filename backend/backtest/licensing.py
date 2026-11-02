"""공식 인허가 원문으로 폐업 점포도 포함하는 후속 검증 후보를 만듭니다."""

import calendar
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from app.agents.business_lifecycle.area_resolver import polygon_contains_point
from app.db.connection import readonly

# 두 업종이 섞인 호프/통닭, 기타, 횟집 등은 추측해서 공통 업종에 배정하지 않습니다.
RESTAURANT_TYPES = {
    "한식": "I201",
    "중국식": "I202",
    "일식": "I203",
    "경양식": "I204",
    "외국음식전문점(인도,태국등)": "I204",
    "분식": "I210",
    "김밥(도시락)": "I210",
    "통닭(치킨)": "I210",
    "정종/대포집/소주방": "I211",
}
REQUIRED = {
    "mgtno",
    "apvpermymd",
    "dcbymd",
    "trdstategbn",
    "uptaenm",
    "x",
    "y",
    "sitewhladdr",
    "rdnwhladdr",
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_download(path: Path, manifest: Path) -> tuple[list[dict], dict]:
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    if sha256(path) != meta["sha256"] or path.stat().st_size != meta["bytes"]:
        raise ValueError("인허가 원문이 다운로드 기록과 다릅니다.")
    if meta["form"]["infId"] != "OA-16094":
        raise ValueError("일반음식점 인허가 원문이 아닙니다.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = data.get("DATA")
    if not isinstance(rows, list) or not rows:
        raise ValueError("인허가 원문에 행이 없습니다.")
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not REQUIRED <= row.keys():
            raise ValueError("인허가 필수 필드가 없습니다.")
        key = text(row, "mgtno")
        if not key or key in seen:
            raise ValueError("인허가 관리번호가 비었거나 중복됩니다.")
        seen.add(key)
    return rows, meta


def text(row: dict, key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value).strip()


def parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    if len(value) == 8 and value.isdigit():
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    # 잘못된 값의 앞 열 글자만 잘라 정상 날짜처럼 취급하지 않습니다.
    return date.fromisoformat(value)


def anniversary(start: date) -> date:
    year = start.year + 1
    return date(year, start.month, min(start.day, calendar.monthrange(year, start.month)[1]))


def outcome(row: dict, snapshot: date) -> dict:
    """12개월 내 '기록된 폐업'을 구분합니다. 연속 영업·사업 성공 여부와 다릅니다."""
    try:
        start = parse_date(text(row, "apvpermymd"))
        closed = parse_date(text(row, "dcbymd"))
    except ValueError:
        return {"status": "unknown", "reason": "invalid_date"}
    if start is None or start > snapshot:
        return {"status": "unknown", "reason": "invalid_permit_date"}
    end = anniversary(start)
    state = text(row, "trdstategbn")
    if closed and (closed < start or closed > snapshot):
        return {"status": "unknown", "reason": "contradictory_closure_date"}
    if closed and state != "03":
        return {"status": "unknown", "reason": "closure_status_conflict"}
    if closed and closed <= end:
        # 관찰기간이 덜 찼어도 이미 발생한 폐업은 관측됩니다.
        value = 1
    elif snapshot < end:
        return {"status": "unknown", "reason": "right_censored"}
    elif closed or state == "01":
        value = 0
    else:
        return {"status": "unknown", "reason": "unresolved_status_or_closure_date"}
    return {
        "status": "observed",
        "recorded_closure_within_12_months": value,
        "followup_end": end.isoformat(),
        "interpretation": "인허가일부터 12개월 내 기록된 폐업. 실제 개점일·연속 영업 보장 아님",
    }


def risk_window_outcome(row: dict, snapshot: date, start: date, end: date) -> dict:
    """예측일에 이미 허가된 점포의 고정 관찰기간 내 폐업 신고를 구분합니다."""
    if start > end:
        raise ValueError("관찰기간의 시작과 끝이 바뀌었습니다.")
    try:
        permitted = parse_date(text(row, "apvpermymd"))
        closed = parse_date(text(row, "dcbymd"))
    except ValueError:
        return {"status": "unknown", "reason": "invalid_date"}
    if permitted is None or permitted > snapshot:
        return {"status": "unknown", "reason": "invalid_permit_date"}
    if closed and (closed < permitted or closed > snapshot):
        return {"status": "unknown", "reason": "contradictory_closure_date"}
    state = text(row, "trdstategbn")
    if closed and state != "03":
        return {"status": "unknown", "reason": "closure_status_conflict"}
    if permitted >= start:
        return {"status": "not_at_risk", "reason": "not_permitted_before_prediction"}
    if closed and closed < start:
        return {"status": "not_at_risk", "reason": "closed_before_prediction"}
    if closed and closed <= end:
        value = 1
    elif snapshot < end:
        return {"status": "unknown", "reason": "right_censored"}
    elif closed or state == "01":
        value = 0
    else:
        return {"status": "unknown", "reason": "unresolved_status_or_closure_date"}
    return {
        "status": "observed",
        "recorded_closure_within_12_months": value,
        "followup_start": start.isoformat(),
        "followup_end": end.isoformat(),
        "interpretation": "기존 인허가 점포의 관찰기간 내 폐업 기록. 신규 개점 생존율 아님",
    }


class PermitCoordinates:
    def __init__(self):
        try:
            from pyproj import Transformer, network
        except ImportError as exc:
            raise RuntimeError(
                "좌표 검증은 pip install -e '.[backtest]' 설치가 필요합니다."
            ) from exc

        # 좌표 변환 도중 외부 보정 자료를 내려받지 않습니다.
        network.set_network_enabled(False)
        self.transformer = Transformer.from_crs(
            "EPSG:5174", "EPSG:5181", always_xy=True, allow_ballpark=False, only_best=True
        )
        self.geographic = Transformer.from_crs("EPSG:5181", "EPSG:4326", always_xy=True)

    def __call__(self, row: dict) -> tuple[float, float]:
        from pyproj.exceptions import ProjError

        x, y = float(text(row, "x")), float(text(row, "y"))
        if not all(math.isfinite(v) and v > 0 for v in (x, y)):
            raise ValueError("인허가 좌표가 비었거나 유효하지 않습니다.")
        try:
            x, y = self.transformer.transform(x, y, errcheck=True)
            lon, lat = self.geographic.transform(x, y, errcheck=True)
        except ProjError as exc:
            raise ValueError("인허가 좌표를 변환할 수 없습니다.") from exc
        if not (37.35 <= lat <= 37.8 and 126.7 <= lon <= 127.3):
            raise ValueError("서울 범위를 벗어난 인허가 좌표입니다.")
        return x, y


def load_polygons(data: Path, version: dict) -> dict:
    columns = json.loads(version["columns_json"])
    with readonly(data) as db:
        return {
            code: dict(zip(columns, json.loads(payload), strict=True))["rings"]
            for code, payload in db.execute(
                "SELECT area_code,payload FROM areas WHERE version_id=?", (version["version_id"],)
            )
        }


def select_candidates(
    rows: list[dict],
    areas: dict,
    polygons: dict,
    allowed: set[str],
    coordinates,
    *,
    permit_start: date,
    permit_end: date,
    features_available: date,
    assessment_date: date | None = None,
) -> dict:
    if permit_start > permit_end:
        raise ValueError("인허가 표본 기간이 바뀌었습니다.")
    if assessment_date is None:
        if not features_available < permit_start:
            raise ValueError("자료 이용 가능일 이후 인허가 표본만 선정해야 합니다.")
    elif not (features_available < assessment_date and permit_end < assessment_date):
        raise ValueError("기존 점포의 인허가와 자료 이용 가능일은 예측일보다 앞서야 합니다.")
    cases, exclusions = [], []
    for row in rows:
        key = text(row, "mgtno")
        try:
            start = parse_date(text(row, "apvpermymd"))
        except ValueError:
            start = None
        reason = None
        code = RESTAURANT_TYPES.get(text(row, "uptaenm"))
        if start is None or not permit_start <= start <= permit_end:
            reason = "outside_permit_window_or_invalid_date"
        elif code is None:
            reason = "ambiguous_or_unmapped_restaurant_type"
        else:
            try:
                x, y = coordinates(row)
            except (ValueError, OverflowError):
                reason = "missing_or_invalid_source_coordinate"
            else:
                # 어느 상권인지 고르는 데 폐업일·현재 영업상태를 사용하지 않습니다.
                matches = [
                    a
                    for a, info in areas.items()
                    if info["kind"] == "A"
                    and info["bbox"][0] <= x <= info["bbox"][2]
                    and info["bbox"][1] <= y <= info["bbox"][3]
                    and polygon_contains_point(polygons[a], x, y)
                ]
                reason = (
                    "outside_or_ambiguous_neighborhood_polygon"
                    if len(matches) != 1
                    else "previous_or_buffered_or_seen_area"
                    if matches[0] not in allowed
                    else None
                )
        if reason:
            exclusions.append({"id": key, "reason": reason})
            continue
        area = matches[0]
        cases.append(
            {
                "id": key,
                "permit_date": start.isoformat(),
                "industry": code,
                "area": area,
                "district": areas[area]["district"],
                "point_epsg5181": [x, y],
            }
        )
    return {
        "cases": cases,
        "exclusions": exclusions,
        "input_n": len(rows),
        "selection_uses_closure_or_current_status": False,
        "exclusion_counts": dict(Counter(v["reason"] for v in exclusions)),
    }


def population_inventory(path: Path, expected_period: str) -> dict:
    with path.open(encoding="cp949", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    keys = ("기준_년분기_코드", "상권_코드", "상권_구분_코드")
    if not rows or not set(keys) <= set(reader.fieldnames or []):
        raise ValueError("과거 인구 자료의 필수 필드가 없습니다.")
    seen = set()
    for row in rows:
        key = (row[keys[0]], row[keys[1]])
        if key in seen or key[0] != expected_period:
            raise ValueError("과거 인구 자료에 중복이나 다른 분기가 섞였습니다.")
        seen.add(key)
        for field in reader.fieldnames[5:]:
            number = float(row[field])
            if not math.isfinite(number) or number < 0 or not number.is_integer():
                raise ValueError("인구 자료의 관측 건수가 올바르지 않습니다.")
    return {
        "file": str(path.resolve()),
        "sha256": sha256(path),
        "period": expected_period,
        "row_n": len(rows),
        "area_kinds": dict(Counter(r[keys[2]] for r in rows)),
        "missing_rows_filled": 0,
        "historical_publication_vintage_verified": False,
    }

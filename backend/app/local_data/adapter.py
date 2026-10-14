"""고정 자료 버전에서 기존 formatter 입력을 만드는 읽기 전용 어댑터입니다."""

import json
import math
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

from app.agents.agentic.formatter import format_inputs
from app.agents.business_lifecycle.area_resolver import (
    BusinessAreaNoDataError,
    ShapeFeature,
    resolve_features,
)
from app.agents.commercial_area.agent import _nearest_district
from app.agents.commercial_area.client import CSV_FIELDS, to_store
from app.agents.commercial_area.industries import map_stores
from app.agents.commercial_area.metrics import haversine_m
from app.local_data.database import DataValidationError, default_path

SOURCE_NAMES = {
    "stores": "commercial_area",
    "lifecycle": "business_lifecycle",
    "floating": "floating_population",
    "resident": "resident_population",
    "worker": "worker_population",
    "areas": "areas",
}


class LocalAdapter:
    def __init__(self, path: Path | None = None, versions: list[dict] | None = None):
        self.path = (path or default_path()).resolve()
        with self.connection() as db:
            self.versions = (
                versions
                if versions is not None
                else [
                    dict(row)
                    for row in db.execute(
                        "SELECT v.* FROM data_versions v JOIN release_versions r USING(version_id) "
                        "WHERE r.release_id=(SELECT MAX(release_id) FROM data_releases)"
                    )
                ]
            )
            if not self.versions:
                raise DataValidationError("DATA_NOT_READY: 활성 자료가 없습니다.")
            for version in self.versions:
                row = db.execute(
                    "SELECT file_hash FROM data_versions WHERE version_id=?",
                    (version["version_id"],),
                ).fetchone()
                if row is None or row[0] != version["file_hash"]:
                    raise DataValidationError("SOURCE_UNAVAILABLE: 고정 자료 버전이 없거나 변경됨")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def rows(self, source: str, *, area_codes=None, bounds=None) -> list[dict]:
        if source not in SOURCE_NAMES:
            raise DataValidationError("허용되지 않은 원천")
        versions = [v for v in self.versions if v["source"] == source]
        if not versions:
            return []
        with self.connection() as db:
            output: list[dict] = []
            for version in versions:
                vid = version["version_id"]
                fields = db.execute(
                    "SELECT columns_json FROM source_fields WHERE version_id=?", (vid,)
                ).fetchone()
                if fields is None:
                    raise DataValidationError("SOURCE_UNAVAILABLE: 자료 버전 삭제됨")
                columns = json.loads(fields[0])
                sql = f"SELECT payload FROM {source} WHERE version_id=?"
                params = [vid]
                if area_codes is not None:
                    if not area_codes:
                        continue
                    sql += " AND area_code IN (" + ",".join("?" for _ in area_codes) + ")"
                    params.extend(area_codes)
                if bounds:
                    sql += " AND latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?"
                    params.extend(bounds)
                output.extend(
                    dict(zip(columns, json.loads(r[0]), strict=True))
                    for r in db.execute(sql, params)
                )
        return output

    def stores(self, site, radius):
        dy = radius / 110000
        dx = dy / math.cos(math.radians(site.latitude))
        rows = self.rows(
            "stores",
            bounds=(
                site.latitude - dy,
                site.latitude + dy,
                site.longitude - dx,
                site.longitude + dx,
            ),
        )
        return [
            {key: row.get(column) for key, column in CSV_FIELDS.items()}
            for row in rows
            if haversine_m(site.latitude, site.longitude, float(row["위도"]), float(row["경도"]))
            <= radius
        ]

    def analyze(self, task):
        if set(SOURCE_NAMES) - {v["source"] for v in self.versions}:
            raise DataValidationError("DATA_NOT_READY: 기본 6원천 묶음이 필요합니다.")
        areas = self.rows("areas")
        features = [
            ShapeFeature(
                {k: v for k, v in r.items() if k not in ("rings", "bbox", "crs")},
                tuple(r["bbox"]),
                tuple(tuple(tuple(p) for p in ring) for ring in r["rings"]),
            )
            for r in areas
        ]
        try:
            selected = resolve_features(task.site, features)
            area_codes = [selected.area_code]
            selection = {
                "area_code": selected.area_code,
                "method": selected.selection_method,
                "distance_m": selected.selection_distance_m,
            }
        except BusinessAreaNoDataError:
            area_codes, selection = [], {"method": "미선택", "distance_m": None}
        raw = defaultdict(list)
        responses = []

        def wrap(row, args=None):
            return {"row": row, "args": args or {}, "group_key": "local", "raw_row_id": None}

        from app.agents.commercial_area.config import Settings

        settings = Settings.from_env()
        comparisons = [r for r in settings.lq_radius_candidates if r > task.radius_m]
        for radius in (task.radius_m, *comparisons[:1]):
            args = {
                "query": {
                    "radius": radius,
                    "cx": round(task.site.longitude, 6),
                    "cy": round(task.site.latitude, 6),
                }
            }
            rows = self.stores(task.site, radius)
            if radius == task.radius_m:
                nearby = [s for r in rows if (s := to_store(r)) is not None]
            raw["commercial_area"].extend(wrap(row, args) for row in rows)
            # formatter의 기존 수집 검증은 빈 envelope로 통과시키며 실제 완전성은 LD2에서 검증됨.
            responses.append(
                {
                    "source": "commercial_area",
                    "request_args_json": json.dumps(args),
                    "response_json": json.dumps({"body": {"items": []}}),
                }
            )
        for area in areas:
            row = dict(area)
            for original, target in (
                ("XCNTS_VALU", "XCNTS_VALUE"),
                ("YDNTS_VALU", "YDNTS_VALUE"),
                ("TRDAR_CD_N", "TRDAR_CD_NM"),
            ):
                row[target] = row.get(target, row.get(original))
            raw["floating_population"].append(wrap(row))
        from app.agents.floating_population.geo import _overlapping_areas
        from app.agents.floating_population.models import TrdarArea
        from app.geo import to_epsg5181

        hits = _overlapping_areas(
            [TrdarArea.from_api_row(r["row"]) for r in raw["floating_population"]],
            *to_epsg5181(task.site.latitude, task.site.longitude),
            task.radius_m,
        )
        population_codes = [a.trdar_cd for a, _ in hits]
        for source in ("floating", "resident", "worker", "lifecycle"):
            codes = (
                population_codes
                if source == "floating"
                else area_codes
                if source == "lifecycle"
                else None
            )
            raw[SOURCE_NAMES[source]].extend(
                wrap(row) for row in self.rows(source, area_codes=codes)
            )
        for version in self.versions:
            if version["source"] == "lifecycle":
                responses.append(
                    {
                        "source": "business_lifecycle",
                        "request_args_json": json.dumps({"extra": version["quarter"]}),
                    }
                )
        district, _ = _nearest_district(map_stores(nearby), task.site.latitude, task.site.longitude)
        store_version = next(v["version_id"] for v in self.versions if v["source"] == "stores")
        with self.connection() as db:
            counts = dict(
                db.execute(
                    "SELECT industry_code,count FROM district_counts "
                    "WHERE version_id=? AND district_code=?",
                    (store_version, district),
                )
            )
        periods = {
            source: max(v["quarter"] for v in self.versions if v["source"] == source)
            for source in ("floating", "lifecycle")
        }
        data, _, _ = format_inputs(
            task, raw, responses, set(), district_counts=counts, periods=periods
        )
        data["comparison_radius_m"] = comparisons[0] if comparisons else None
        data["district_code"] = district

        data["area_selection"] = selection
        data["limitations"] = [
            "서울 밖 점포 미반영",
            "서울 행정경계 도형 미보유: 반경 경계 교차는 미확인",
        ]
        from app.agents.commercial_area.franchise import build_franchise, load_cached_brands
        from app.agents.commercial_area.schemas import MiddleCategory

        brands = load_cached_brands(settings)
        data["franchise_status"] = "observed" if brands else "unknown"
        data["commercial_area"]["franchise"] = (
            build_franchise(
                map_stores(nearby),
                brands,
                [MiddleCategory.model_validate(r) for r in data["commercial_area"]["by_middle"]],
                settings.ftc_year,
            ).model_dump(mode="json")
            if brands
            else None
        )

        data["source_versions"] = [v["version_id"] for v in self.versions]
        return data

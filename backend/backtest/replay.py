import calendar
import math
import random
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd

from app.agents.business_lifecycle import preprocess
from app.agents.business_lifecycle.area_resolver import read_dbf
from app.agents.business_lifecycle.config import Settings as LifecycleSettings
from app.agents.commercial_area.schemas import (
    CommercialAreaData,
    Diversity,
    LqBaseline,
    MajorCategory,
    MiddleCategory,
    RestaurantDensity,
)
from app.geo import from_epsg5181
from app.industries import TAXONOMY, lookup
from app.schemas import AgentAnalysis, Scope, Site
from backtest.data import api_rows, quarters_until

UNCOMPUTED = ("diff_type_count", "jacobian", "major_cluster_count", "major_cluster_diversity")
RESTAURANT_MAJOR = "I2"


@dataclass(frozen=True)
class AreaInfo:
    code: str
    name: str
    kind: str
    district: str
    x: float
    y: float
    area_m2: float


def load_areas(dbf: Path | None = None) -> dict[str, AreaInfo]:
    path = dbf or LifecycleSettings().area_shape_path.with_suffix(".dbf")
    areas = {}
    for record in read_dbf(path):
        if record is None:
            continue
        info = AreaInfo(
            code=str(record["TRDAR_CD"]),
            name=str(record["TRDAR_CD_N"]),
            kind=str(record["TRDAR_SE_1"]),
            district=str(record["SIGNGU_CD_"]),
            x=float(record["XCNTS_VALU"] or 0),
            y=float(record["YDNTS_VALU"] or 0),
            area_m2=float(record["RELM_AR"] or 0),
        )
        areas[info.code] = info
    return areas


def sample_areas(areas: dict[str, AreaInfo], n: int = 40, seed: int = 20261005) -> list[AreaInfo]:
    groups: dict[str, list[AreaInfo]] = {}
    for info in sorted(areas.values(), key=lambda a: a.code):
        groups.setdefault(info.kind, []).append(info)
    total = sum(len(g) for g in groups.values())
    exact = {kind: n * len(g) / total for kind, g in groups.items()}
    quota = {kind: int(v) for kind, v in exact.items()}
    by_remainder = sorted(exact, key=lambda k: exact[k] - quota[k], reverse=True)
    for kind in by_remainder[: n - sum(quota.values())]:
        quota[kind] += 1
    for kind in quota:
        if quota[kind] == 0:
            largest = max(quota, key=lambda k: quota[k])
            quota[largest] -= 1
            quota[kind] = 1
    rng = random.Random(seed)
    return [info for kind in sorted(groups) for info in rng.sample(groups[kind], quota[kind])]


def site_for(info: AreaInfo) -> Site:
    latitude, longitude = from_epsg5181(info.x, info.y)
    return Site(
        input_address=info.name,
        road_address=info.name,
        latitude=latitude,
        longitude=longitude,
    )


def quarter_end(base: str) -> date:
    year, month = int(base[:4]), int(base[4]) * 3
    return date(year, month, calendar.monthrange(year, month)[1])


@contextmanager
def replay_store_rows(data: pd.DataFrame, base: str):
    by_area = dict(tuple(data.groupby("TRDAR_CD")))

    async def fetch(area_code, base_quarter, quarter_count=12, *, settings=None):
        quarters = [q for q in quarters_until(base_quarter, quarter_count) if q <= base]
        frame = by_area.get(area_code)
        return [] if frame is None else api_rows(frame, quarters)

    with patch.object(preprocess, "fetch_recent_store_data", fetch):
        yield


def commercial_substitute(
    data: pd.DataFrame, info: AreaInfo, base: str, request_id: str
) -> AgentAnalysis:
    now = data[(data["STDR_YYQU_CD"] == base) & data["INDUSTRY"].notna()]
    seoul = now.groupby("INDUSTRY")["SIMILR_INDUTY_STOR_CO"].sum()
    local = now[now["TRDAR_CD"] == info.code].groupby("INDUSTRY")["SIMILR_INDUTY_STOR_CO"].sum()
    total = float(local.sum())
    seoul_total = float(seoul.sum())
    km2 = info.area_m2 / 1e6
    radius = max(1, round(math.sqrt(info.area_m2 / math.pi)))
    majors: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for code in sorted(seoul.index):
        industry = lookup.get(code)
        count = int(local.get(code, 0))
        majors[industry.major_code] += count
        share = count / total if total else 0.0
        lq = share / (float(seoul[code]) / seoul_total) if total and seoul[code] else None
        citable = {name: False for name in UNCOMPUTED}
        if count < 5:
            citable.update(lq=False, lq_district=False)
        rows.append(
            {"industry": industry, "count": count, "share": share, "lq": lq, "citable": citable}
        )
    middle = [
        MiddleCategory(
            code=r["industry"].code,
            name=r["industry"].name,
            major_code=r["industry"].major_code,
            major_name=r["industry"].major_name,
            count=r["count"],
            share=round(r["share"], 4),
            density_per_km2=round(r["count"] / km2, 4) if km2 else 0.0,
            lq=round(r["lq"], 4) if r["lq"] is not None else None,
            lq_district=None,
            diff_type_count=0,
            jacobian=0.0,
            major_cluster_count=majors[r["industry"].major_code],
            major_cluster_diversity=0.0,
            citable=r["citable"],
        )
        for r in sorted(rows, key=lambda r: (-r["count"], r["industry"].code))
    ]
    major_names = {r["industry"].major_code: r["industry"].major_name for r in rows}
    by_major = [
        MajorCategory(
            code=code,
            name=major_names[code],
            count=count,
            share=round(count / total, 4) if total else 0.0,
            density_per_km2=round(count / km2, 4) if km2 else 0.0,
        )
        for code, count in sorted(majors.items())
    ]
    hhi_middle = sum(m.share**2 for m in middle)
    restaurants = majors[RESTAURANT_MAJOR]
    payload = CommercialAreaData(
        description=(
            f"{base[:4]}년 {base[4]}분기 서울시 상권분석서비스 점포 수"
            f"(상권 '{info.name}' 경계 안, 반경 집계 아님). "
            "서울시 생활밀접업종과 연결되는 업종만 있고 "
            "diff_type_count·jacobian·major_cluster 지표는 계산하지 않아 인용할 수 없습니다. "
            "lq는 서울 1,650개 상권 전체의 업종 비중과 비교한 값입니다."
        ),
        radius_m=radius,
        store_total=int(total),
        by_major=by_major,
        by_middle=middle,
        diversity=Diversity(
            hhi_major=round(sum((m.share) ** 2 for m in by_major), 4),
            hhi_middle=round(hhi_middle, 4),
            effective_categories=round(1 / hhi_middle, 4) if hhi_middle else 0.0,
        ),
        restaurant_density=RestaurantDensity(
            value=round(restaurants / km2, 4) if km2 else 0.0,
            unit="stores_per_km2",
            store_count=restaurants,
        ),
        lq_baseline=LqBaseline(requested_radius_m=radius),
        citable={"summary": False, "summary_text": False, "restaurant_density": False},
        taxonomy=dict(TAXONOMY),
    )
    return AgentAnalysis(
        request_id=request_id,
        agent_id="commercial_area",
        status="ok",
        scope=Scope(area=f"{info.name} 상권", period=f"{base[:4]}년 {base[4]}분기"),
        data=payload.model_dump(),
    )

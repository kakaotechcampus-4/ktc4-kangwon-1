"""반경별 점포 구성과 집적·특화 지표를 계산합니다."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Sequence

from .config import RESTAURANT_MAJOR_NAMES, Settings
from .schemas import (
    CategoryRank,
    Diversity,
    MajorCategory,
    MiddleCategory,
    MiddleCode,
    RadiusSlice,
    RestaurantDensity,
    SliceExplanations,
    SpecializationRank,
    Store,
)

EARTH_RADIUS_M = 6_371_000.0


def area_km2(radius_m: int) -> float:
    return math.pi * (radius_m**2) / 1_000_000


def _share(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return count / total


def _density(count: int, radius_m: int) -> float:
    area = area_km2(radius_m)
    if area <= 0:
        return 0.0
    return count / area


def hhi(counts: Iterable[int]) -> float:
    values = [c for c in counts if c > 0]
    total = sum(values)
    if total <= 0:
        return 0.0
    return sum((c / total) ** 2 for c in values)


def effective_categories(index: float) -> float:
    if index <= 0:
        return 0.0
    return 1 / index


def count_by_middle(stores: Sequence[Store]) -> Counter[str]:
    return Counter(s.middle_code for s in stores if s.middle_code)


def count_by_major(stores: Sequence[Store]) -> Counter[str]:
    return Counter(s.major_code for s in stores if s.major_code)


def major_names(stores: Sequence[Store]) -> dict[str, str]:
    return {s.major_code: s.major_name for s in stores if s.major_code}


def build_major_rows(
    stores: Sequence[Store],
    radius_m: int,
    master: Sequence[MiddleCode],
) -> list[MajorCategory]:
    counts = count_by_major(stores)
    names = {m.major_code: m.major_name for m in master}
    names.update(major_names(stores))
    total = len(stores)
    rows = [
        MajorCategory(
            code=code,
            name=names.get(code, code),
            count=counts.get(code, 0),
            share=round(_share(counts.get(code, 0), total), 6),
            density_per_km2=round(_density(counts.get(code, 0), radius_m), 4),
        )
        for code in sorted(names)
    ]
    return sorted(rows, key=lambda r: (-r.count, r.code))


def build_middle_rows(
    stores: Sequence[Store],
    radius_m: int,
    master: Sequence[MiddleCode],
    baseline_counts: dict[str, int] | None = None,
    district_counts: dict[str, int] | None = None,
) -> list[MiddleCategory]:
    counts = count_by_middle(stores)
    total = len(stores)
    baseline_total = sum(baseline_counts.values()) if baseline_counts else 0
    district_total = sum(district_counts.values()) if district_counts else 0

    known = {m.code: m for m in master}
    for store in stores:
        if store.middle_code and store.middle_code not in known:
            known[store.middle_code] = MiddleCode(
                code=store.middle_code,
                name=store.middle_name or store.middle_code,
                major_code=store.major_code,
                major_name=store.major_name,
            )

    rows: list[MiddleCategory] = []
    for code in sorted(known):
        entry = known[code]
        count = counts.get(code, 0)
        diff_count = total - count
        other_counts = [c for k, c in counts.items() if k != code and c > 0]

        lq = _ratio_against(count, total, baseline_counts, baseline_total, code)
        lq_district = _ratio_against(count, total, district_counts, district_total, code)

        density = _density(count, radius_m)
        rows.append(
            MiddleCategory(
                code=code,
                name=entry.name,
                major_code=entry.major_code,
                major_name=entry.major_name,
                count=count,
                share=round(_share(count, total), 6),
                density_per_km2=round(density, 4),
                density_sq=round(density**2, 4),
                lq=lq,
                lq_district=lq_district,
                same_type_count=count,
                diff_type_count=diff_count,
                marshallian=round(density, 4),
                jacobian=round(effective_categories(hhi(other_counts)), 4),
            )
        )
    return sorted(rows, key=lambda r: (-r.count, r.code))


def _ratio_against(
    count: int,
    total: int,
    baseline_counts: dict[str, int] | None,
    baseline_total: int,
    code: str,
) -> float | None:
    if not baseline_counts or baseline_total <= 0:
        return None
    baseline_share = _share(baseline_counts.get(code, 0), baseline_total)
    if baseline_share <= 0:
        return None
    return round(_share(count, total) / baseline_share, 4)


def build_district_specialization(
    rows: Sequence[MiddleCategory],
    settings: Settings,
    district_name: str,
) -> list[SpecializationRank]:
    threshold = settings.min_count_for_specialization
    picked = sorted(
        [r for r in rows if r.lq_district is not None and r.count >= threshold],
        key=lambda r: (-(r.lq_district or 0.0), r.name),
    )[: settings.rank_size]

    ranks = []
    for index, row in enumerate(picked, 1):
        times = row.lq_district or 0.0
        if 0.95 <= times <= 1.05:
            note = f"{district_name} 전체와 비슷한 수준입니다"
        elif times > 1.05:
            note = f"{district_name} 전체보다 {times:.1f}배 많습니다"
        else:
            note = f"{district_name} 전체의 {times:.1f}배에 그칩니다"
        ranks.append(
            SpecializationRank(
                rank=index,
                code=row.code,
                name=row.name,
                count=row.count,
                times_vs_surroundings=times,
                note=note,
            )
        )
    return ranks


def build_diversity(
    major_rows: Sequence[MajorCategory],
    middle_rows: Sequence[MiddleCategory],
) -> Diversity:
    hhi_major = hhi(r.count for r in major_rows)
    hhi_middle = hhi(r.count for r in middle_rows)
    return Diversity(
        hhi_major=round(hhi_major, 6),
        hhi_middle=round(hhi_middle, 6),
        effective_categories=round(effective_categories(hhi_middle), 4),
    )


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def stores_within(
    stores: Sequence[Store],
    center_lat: float,
    center_lon: float,
    radius_m: int,
) -> list[Store]:
    inside = []
    for store in stores:
        if store.latitude is None or store.longitude is None:
            continue
        if haversine_m(center_lat, center_lon, store.latitude, store.longitude) <= radius_m:
            inside.append(store)
    return inside


def _count_rank(row: MiddleCategory, index: int, total: int) -> CategoryRank:
    if row.count == 0:
        note = "이 반경 안에는 없습니다"
    else:
        share = row.count / total if total else 0.0
        note = f"{row.count:,}개 · 이 반경 점포의 {share:.1%}"
    return CategoryRank(
        rank=index,
        code=row.code,
        name=row.name,
        count=row.count,
        density_per_km2=row.density_per_km2,
        note=note,
    )


def _concentration_rank(row: MiddleCategory, index: int) -> CategoryRank:
    return CategoryRank(
        rank=index,
        code=row.code,
        name=row.name,
        count=row.count,
        density_per_km2=row.density_per_km2,
        note=f"1km²당 {row.density_per_km2:,.0f}개꼴로 모여 있습니다",
    )


def _specialization_rank(
    row: MiddleCategory, index: int, baseline_radius_m: int
) -> SpecializationRank:
    times = row.lq or 0.0
    if 0.95 <= times <= 1.05:
        note = f"주변 {baseline_radius_m:,}m와 비슷한 수준입니다"
    elif times > 1.05:
        note = f"주변 {baseline_radius_m:,}m 평균보다 {times:.1f}배 많습니다"
    else:
        note = f"주변 {baseline_radius_m:,}m 평균의 {times:.1f}배에 그칩니다"
    return SpecializationRank(
        rank=index,
        code=row.code,
        name=row.name,
        count=row.count,
        times_vs_surroundings=times,
        note=note,
    )


def _names(rows: Sequence[CategoryRank | SpecializationRank], limit: int = 3) -> str:
    return ", ".join(f"{r.name}({r.count:,}개)" for r in rows[:limit])


def subject_particle(name: str) -> str:
    if not name:
        return "이"
    last = name[-1]
    if not ("가" <= last <= "힣"):
        return "이"
    return "이" if (ord(last) - 0xAC00) % 28 else "가"


def _build_explanations(
    radius_m: int,
    total: int,
    absent_count: int,
    top: Sequence[CategoryRank],
    bottom: Sequence[CategoryRank],
    concentration: Sequence[CategoryRank],
    specialization: Sequence[SpecializationRank],
    baseline_radius_m: int | None,
    threshold_note: int,
) -> SliceExplanations:
    store_total = f"반경 {radius_m:,}m 안에 점포가 {total:,}개 있습니다."

    top_text = f"가장 많은 업종은 {_names(top)} 순입니다." if top else "집계된 업종이 없습니다."

    least = [r for r in bottom if r.count > 0]
    if absent_count and least:
        bottom_text = (
            f"가장 적은 업종은 {_names(least)}이고, "
            f"이 반경에 아예 없는 업종이 {absent_count}개입니다."
        )
    elif absent_count:
        bottom_text = f"이 반경에 아예 없는 업종이 {absent_count}개입니다."
    elif least:
        bottom_text = f"가장 적은 업종은 {_names(least)}입니다. 없는 업종은 없습니다."
    else:
        bottom_text = "집계된 업종이 없습니다."

    if concentration:
        head = concentration[0]
        concentration_text = (
            "집적도는 같은 면적에 얼마나 빽빽하게 모여 있는지를 뜻합니다. "
            f"여기서는 {head.name}{subject_particle(head.name)} "
            f"1km²당 {head.density_per_km2:,.0f}개로 가장 빽빽합니다. "
            "같은 업종이 몰려 있으면 손님을 서로 뺏기도 하지만, "
            "그 동네를 찾는 이유가 되기도 합니다."
        )
    else:
        concentration_text = "집적도를 계산할 점포가 없습니다."

    if specialization:
        top_special = specialization[0]
        specialization_text = (
            f"특화도는 주변 {baseline_radius_m:,}m와 비교해 "
            "이 자리에 유난히 많은 업종이 무엇인지를 뜻합니다. "
            f"{top_special.name}{subject_particle(top_special.name)} 주변보다 "
            f"{top_special.times_vs_surroundings:.1f}배 많아 가장 두드러집니다. "
            f"점포가 {threshold_note}개 미만인 업종은 숫자가 튀어 제외했습니다."
        )
    else:
        specialization_text = "비교할 주변 자료가 없어 특화도를 계산하지 못했습니다."

    return SliceExplanations(
        store_total=store_total,
        top=top_text,
        bottom=bottom_text,
        concentration=concentration_text,
        specialization=specialization_text,
    )


def build_radius_slices(
    stores: Sequence[Store],
    center_lat: float,
    center_lon: float,
    master: Sequence[MiddleCode],
    settings: Settings,
    baseline_counts: dict[str, int] | None = None,
    baseline_radius_m: int | None = None,
) -> list[RadiusSlice]:
    radii = sorted(
        {r for r in settings.breakdown_radii if r <= settings.analysis_radius_m}
        | {settings.analysis_radius_m}
    )
    size = settings.rank_size
    slices: list[RadiusSlice] = []

    for radius_m in radii:
        subset = stores_within(stores, center_lat, center_lon, radius_m)
        rows = build_middle_rows(subset, radius_m, master, baseline_counts)
        total = len(subset)
        absent_count = sum(1 for r in rows if r.count == 0)

        top_rows = sorted(rows, key=lambda r: (-r.count, r.name))[:size]
        bottom_rows = sorted(rows, key=lambda r: (r.count, r.name))[:size]
        concentration_rows = sorted(rows, key=lambda r: (-r.density_per_km2, r.name))[:size]
        threshold = settings.min_count_for_specialization
        specialization_rows = sorted(
            [r for r in rows if r.lq is not None and r.count >= threshold],
            key=lambda r: (-(r.lq or 0.0), r.name),
        )[:size]

        top = [_count_rank(r, i, total) for i, r in enumerate(top_rows, 1)]
        bottom = [_count_rank(r, i, total) for i, r in enumerate(bottom_rows, 1)]
        concentration = [_concentration_rank(r, i) for i, r in enumerate(concentration_rows, 1)]
        specialization = [
            _specialization_rank(r, i, baseline_radius_m or 0)
            for i, r in enumerate(specialization_rows, 1)
        ]

        slices.append(
            RadiusSlice(
                radius_m=radius_m,
                store_total=total,
                category_count=len(rows) - absent_count,
                absent_category_count=absent_count,
                top_by_count=top,
                bottom_by_count=bottom,
                top_by_concentration=concentration,
                top_by_specialization=specialization,
                explanations=_build_explanations(
                    radius_m,
                    total,
                    absent_count,
                    top,
                    bottom,
                    concentration,
                    specialization,
                    baseline_radius_m,
                    threshold,
                ),
            )
        )
    return slices


def build_restaurant_density(
    stores: Sequence[Store],
    radius_m: int,
    settings: Settings,
) -> RestaurantDensity:
    count = sum(1 for s in stores if s.major_name in RESTAURANT_MAJOR_NAMES)
    density = _density(count, radius_m)
    return RestaurantDensity(
        value=round(density, 4),
        squared=round(density**2, 4),
        unit="stores_per_km2",
        store_count=count,
    )

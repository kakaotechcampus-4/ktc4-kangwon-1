"""반경 안의 점포 구성을 계산해 상권 경쟁 분석 결과를 반환합니다."""

from __future__ import annotations

from datetime import date

from app.schemas import AgentAnalysis, AgentError, AnalysisTask, Scope

from .client import SbizApiError, StoreClient
from .config import Settings, load_dotenv_if_present
from .franchise import build_franchise, load_brands
from .llm import render_summary_text, summarize
from .metrics import (
    build_diversity,
    build_major_rows,
    build_middle_rows,
    build_radius_slices,
    build_restaurant_density,
    count_by_middle,
)
from .schemas import CommercialAreaData, LqBaseline, Summary
from .upjong import load_middle_master, master_from_stores

AGENT_ID = "commercial_area"


def analyze(
    task: AnalysisTask | dict,
    settings: Settings | None = None,
    store_client: StoreClient | None = None,
) -> AgentAnalysis:
    load_dotenv_if_present()
    task = AnalysisTask.model_validate(task)
    settings = settings or Settings.from_env()
    radius = settings.analysis_radius_m
    site = task.site
    scope_area = f"{site.input_address} 반경 {radius}m"

    warnings: list[str] = []
    degraded = False

    owns_client = store_client is None
    client = store_client or StoreClient(settings)

    try:
        try:
            stores, meta = client.stores_in_radius(site.latitude, site.longitude, radius)
        except SbizApiError as exc:
            return AgentAnalysis(
                request_id=task.request_id,
                agent_id=AGENT_ID,
                status="error",
                error=AgentError(code=exc.code, message=exc.message),
                warnings=warnings,
            )

        period = meta.get("reference_date") or f"{date.today().isoformat()} 조회"

        if not stores:
            return AgentAnalysis(
                request_id=task.request_id,
                agent_id=AGENT_ID,
                status="no_data",
                scope=Scope(area=scope_area, period=period),
                warnings=warnings + ["반경 내 조회된 점포가 없습니다."],
            )

        if meta.get("truncated"):
            degraded = True
            warnings.append(
                f"점포 {meta.get('total_count')}건 중 {meta.get('fetched')}건만 조회했습니다. "
                "페이지 상한에 걸려 집계가 일부 누락됐습니다."
            )

        master = load_middle_master(settings)
        if not master:
            master = master_from_stores(stores)
            degraded = True
            warnings.append(
                "업종 코드 마스터 파일이 없어 조회된 업종만 집계했습니다. "
                "점포가 0건인 업종은 결과에 포함되지 않습니다."
            )

        baseline_counts = None
        baseline = LqBaseline(requested_radius_m=settings.lq_radius_candidates[0])
        try:
            baseline_stores, baseline_meta = client.stores_in_radius_with_fallback(
                site.latitude,
                site.longitude,
                settings.lq_radius_candidates,
                grid_m=settings.lq_cache_grid_m,
            )
            baseline_counts = dict(count_by_middle(baseline_stores))
            baseline = LqBaseline(
                requested_radius_m=settings.lq_radius_candidates[0],
                applied_radius_m=baseline_meta.get("radius_m"),
                store_total=len(baseline_stores),
            )
            if baseline_meta.get("radius_m") != settings.lq_radius_candidates[0]:
                warnings.append(
                    f"LQ 기준 반경이 {settings.lq_radius_candidates[0]}m에서 "
                    f"{baseline_meta.get('radius_m')}m로 축소됐습니다."
                )
            if baseline_meta.get("truncated"):
                degraded = True
                warnings.append("LQ 기준 반경 조회가 페이지 상한에 걸려 LQ가 과대추정될 수 있습니다.")
        except SbizApiError as exc:
            degraded = True
            warnings.append(f"LQ 기준 반경 조회 실패로 LQ를 계산하지 못했습니다: {exc.message}")

        major_rows = build_major_rows(stores, radius, master)
        middle_rows = build_middle_rows(stores, radius, master, baseline_counts)

        franchise = None
        brands = load_brands(settings)
        if brands:
            franchise = build_franchise(stores, brands, middle_rows)
            warnings.append(
                "프랜차이즈 판정은 공정위 브랜드명과 상호명을 문자열로 대조한 결과라 "
                "누락과 오탐이 있을 수 있습니다."
            )
        else:
            degraded = True
            warnings.append(
                "공정위 브랜드 목록을 확보하지 못해 프랜차이즈 비율을 계산하지 못했습니다."
            )

        radius_slices = build_radius_slices(
            stores,
            site.latitude,
            site.longitude,
            master,
            settings,
            baseline_counts,
            baseline.applied_radius_m,
        )

        payload = CommercialAreaData(
            radius_m=radius,
            store_total=len(stores),
            data_reference_date=period,
            by_major=major_rows,
            by_middle=middle_rows,
            by_radius=radius_slices,
            diversity=build_diversity(major_rows, middle_rows),
            restaurant_density=build_restaurant_density(stores, radius, settings),
            franchise=franchise,
            lq_baseline=baseline,
        )

        data = payload.model_dump()
        summary, summary_warning = summarize(data, settings)
        if summary_warning:
            warnings.append(summary_warning)
        if summary:
            data["summary"] = Summary.model_validate(summary).model_dump()
            data["summary_text"] = render_summary_text(summary)

        return AgentAnalysis(
            request_id=task.request_id,
            agent_id=AGENT_ID,
            status="partial" if degraded else "ok",
            scope=Scope(area=scope_area, period=period),
            data=data,
            warnings=warnings,
        )
    finally:
        if owns_client:
            client.close()

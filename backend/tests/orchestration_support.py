"""외부 연결 없이 그래프와 저장 서비스를 실행하는 테스트 보조 함수입니다."""

import tempfile
from dataclasses import replace
from pathlib import Path

from app.agents.commercial_area.schemas import CategoryRank, RadiusSlice, SliceExplanations
from app.agents.orchestration.graph import RunHooks, run_graph
from app.industries import lookup
from app.mocks import mock_commercial_area_data
from app.services.analysis import execute_analysis
from app.services.settings import ExecutionSettings


async def run_flow(address, **kwargs):
    hooks = RunHooks(
        **{name: kwargs.pop(name) for name in RunHooks.__dataclass_fields__ if name in kwargs}
    )
    kwargs.setdefault("request_id", "graph-test")
    kwargs.setdefault("radius_m", 500)
    return await run_graph(address, hooks=hooks, **kwargs)


async def run_service(address, *, site=None, settings=None, **kwargs):
    """이전 저장 없는 통합 시험을 임시 DB 기반 서비스 시험으로 옮깁니다."""
    with tempfile.TemporaryDirectory() as directory:
        config = ExecutionSettings(db_path=Path(directory) / "test.sqlite3")
        if settings is not None:
            config = (
                replace(settings, db_path=config.db_path)
                if isinstance(settings, ExecutionSettings)
                else replace(config, commercial=settings)
            )
        if site is not None:

            async def resolve(_):
                return site

            kwargs["resolve"] = resolve
        return await execute_analysis(address, settings=config, **kwargs)


def lq_supplement(baseline_store_total=9000):
    return {
        "analysis_radius_m": 500,
        "baseline_radius_m": 2000,
        "baseline_store_total": baseline_store_total,
        "checked_at": "2026-10-03T00:00:00+00:00",
        "industries": [
            {"industry_id": row["code"], "citable": {"lq": True}, "lq": row["lq"]}
            for row in mock_commercial_area_data()["by_middle"]
        ],
        "note": "시험 보완",
    }


def radius_slice(code="SV020", count=7, radius_m=100):
    return RadiusSlice(
        radius_m=radius_m,
        store_total=40,
        category_count=10,
        absent_category_count=65,
        top_by_count=[
            CategoryRank(
                rank=1,
                code=code,
                name=lookup.get(code).name,
                count=count,
                density_per_km2=222.8,
                note="반경 안 최다",
            )
        ],
        explanations=SliceExplanations(
            store_total="점포",
            top="최다",
            bottom="최소",
            concentration="집중",
            specialization="특화",
        ),
    ).model_dump()

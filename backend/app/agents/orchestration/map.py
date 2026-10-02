"""지도 외부 실패는 관측으로 수집하고 계약·저장 오류는 전파합니다."""

import asyncio

from app.agents.map_analysis.agent import failed_observation
from app.llm.budget import BudgetStorageError
from app.schemas import AnalysisTask, MapLookupPlan, MapObservation

from .tools import MapLookup


async def execute_map_lookup(
    task: AnalysisTask, plan: MapLookupPlan, lookup: MapLookup, operation_timeout: float
) -> MapObservation:
    try:
        async with asyncio.timeout(operation_timeout):
            return await lookup(task.model_copy(deep=True), plan.model_copy(deep=True))
    except (BudgetStorageError, ValueError, TypeError):
        raise
    except TimeoutError:
        return failed_observation(task, plan, "MAP_TIMEOUT")
    except Exception:
        return failed_observation(task, plan, "MAP_FAILED")

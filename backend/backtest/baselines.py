import importlib
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

from app.industries.catalog import INDUSTRIES

FLOATING = (
    "AGE_SHARE_AVG",
    "TIME_PER_HOUR_SHARE_AVG",
    "WEEKEND_TO_WEEKDAY_AVG",
    "TIME_BAND_DAILY_PERCENTILES",
    "PATTERN_DAILY_PERCENTILES",
    "DAILY_TOTAL_PERCENTILES",
    "PATTERN_TIME_PER_HOUR_SHARE_AVG",
    "SCALE_PERCENTILES",
)
LIFECYCLE = "SEOUL_INDUSTRY_LIFECYCLE_BASELINE"
FLOATING_MODULE = "app.agents.floating_population.baseline"
TARGETS: dict[str, dict[str, tuple[str, ...]]] = {
    "app.agentic.scoring": {
        "BASELINE_BASE_QUARTER": ("quarter",),
        "SEOUL_INDUSTRY_LIFECYCLE_BASELINE": ("lifecycle",),
        "SEOUL_INDUSTRY_DENSITY_PERCENTILES": ("density",),
    },
    "app.agents.business_lifecycle.baseline": {
        "BASELINE_BASE_QUARTER": ("quarter",),
        "SEOUL_INDUSTRY_LIFECYCLE_BASELINE": ("lifecycle",),
    },
    "app.agents.commercial_area.baseline": {
        "SEOUL_INDUSTRY_DENSITY_PERCENTILES": ("density",),
    },
    "app.agents.floating_population.baseline": {name: ("floating", name) for name in FLOATING},
}


class BaselineMismatch(ValueError):
    pass


def _number(value: Any) -> bool:
    return value is None or (isinstance(value, int | float) and not isinstance(value, bool))


def conform(template: Any, value: Any, where: str, allow_missing: bool = False) -> Any:
    if isinstance(template, dict):
        if not isinstance(value, dict):
            raise BaselineMismatch(f"{where}: 사전이어야 합니다.")
        numeric = bool(template) and all(type(key) is int for key in template)
        try:
            keyed = {int(key) if numeric else key: item for key, item in value.items()}
        except (TypeError, ValueError):
            raise BaselineMismatch(f"{where}: 분위 키가 정수가 아닙니다.") from None
        if allow_missing and not numeric and set(template) <= set(INDUSTRIES):
            extra = set(keyed) - set(template)
            if extra:
                raise BaselineMismatch(f"{where}: 원래 없는 업종 {sorted(extra)}")
        elif set(keyed) != set(template):
            raise BaselineMismatch(f"{where}: 키가 원래와 다릅니다.")
        return {key: conform(template[key], item, f"{where}.{key}") for key, item in keyed.items()}
    if _number(template):
        if _number(value):
            return value
        raise BaselineMismatch(f"{where}: 숫자여야 합니다.")
    if type(value) is not type(template):
        raise BaselineMismatch(f"{where}: 자료형이 원래와 다릅니다.")
    return value


def _section(values: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = values
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise BaselineMismatch(f"기준선 파일에 {'.'.join(path)} 항목이 없습니다.")
        current = current[key]
    return current


def _plan(values: dict[str, Any]) -> list[tuple[Any, str, Any]]:
    steps = []
    for module_name, names in TARGETS.items():
        module = importlib.import_module(module_name)
        for name, path in names.items():
            if not hasattr(module, name):
                raise BaselineMismatch(f"{module_name}.{name}가 서비스 코드에 없습니다.")
            where = f"{module_name}.{name}"
            allow_missing = name == LIFECYCLE
            steps.append(
                (
                    module,
                    name,
                    conform(getattr(module, name), _section(values, path), where, allow_missing),
                )
            )
    quarter = str(values["quarter"])
    label = f"서울 전체 상권 평균 ({quarter[:4]}년 {quarter[4]}분기)"
    steps.append((importlib.import_module(FLOATING_MODULE), "BASELINE_LABEL", label))
    return steps


@contextmanager
def swapped(values: dict[str, Any]) -> Iterator[None]:
    steps = _plan(values)
    with ExitStack() as stack:
        for module, name, value in steps:
            stack.enter_context(patch.object(module, name, value))
        yield

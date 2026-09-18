import math
from typing import Any

import pandas as pd

from app.industries.catalog import (
    EXCLUDED_SEOUL_INDUSTRIES,
    INDUSTRY_TO_SEOUL,
)
from app.industries.catalog import (
    INDUSTRIES as SERVICE_INDUSTRIES,
)
from app.industries.catalog import (
    INDUSTRIES_WITHOUT_SEOUL as UNSUPPORTED_SERVICE_INDUSTRIES,
)
from app.industries.catalog import (
    SEOUL_TO_INDUSTRY as SEOUL_TO_SERVICE,
)

from .client import fetch_recent_store_data, get_recent_quarters
from .config import Settings


def calculate_rate(numerator: float, denominator: float) -> float | None:
    """결측 분자와 분모 0은 관측된 비율 0과 구분합니다."""
    if pd.isna(numerator) or pd.isna(denominator) or denominator <= 0:
        return None
    return round(numerator / denominator * 100, 2)


def _number(value: Any, *, count: bool) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, bool):
        raise ValueError("개폐업 숫자에 bool을 사용할 수 없습니다.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("개폐업 숫자 형식이 올바르지 않습니다.") from exc
    if not math.isfinite(number) or number < 0 or (count and not number.is_integer()):
        raise ValueError("개폐업 숫자 범위가 올바르지 않습니다.")
    return number


def preprocess_business_lifecycle_data(
    area_code: str,
    base_quarter: str,
    quarter_count: int = 12,
    *,
    settings: Settings | None = None,
) -> pd.DataFrame:
    """원본 건수를 공통 업종으로 합산한 뒤 분자·분모에서 비율을 재계산합니다."""
    quarters = get_recent_quarters(base_quarter=base_quarter, count=quarter_count)
    rows = fetch_recent_store_data(
        area_code=area_code,
        base_quarter=base_quarter,
        quarter_count=quarter_count,
        settings=settings,
    )
    if not rows:
        raise ValueError("서울시 Open API에서 조회된 데이터가 없습니다.")

    # 같은 원천키의 값이 다르면 어느 행이 맞는지 추정하지 않습니다.
    unique: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("stdr_yyqu_cd")),
            str(row.get("trdar_cd")),
            str(row.get("svc_induty_cd")),
        )
        if key[0] not in quarters or key[1] != str(area_code):
            raise ValueError("요청 범위 밖 분기 또는 상권 데이터가 섞였습니다.")
        if key in unique and row != unique[key]:
            raise ValueError("같은 분기·상권·원본업종에 상충하는 중복 데이터가 있습니다.")
        unique[key] = row

    numeric = (
        "similr_induty_stor_co",
        "stor_co",
        "frc_stor_co",
        "opbiz_stor_co",
        "clsbiz_stor_co",
        "opbiz_rt",
        "clsbiz_rt",
    )
    groups: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for (quarter, _, source), raw in unique.items():
        if source in EXCLUDED_SEOUL_INDUSTRIES:
            continue
        if source not in SEOUL_TO_SERVICE:
            raise ValueError(f"공통 카탈로그에 없는 서울시 업종입니다: {source}")
        row = dict(raw)
        for field in numeric:
            row[field] = _number(raw.get(field), count=field.endswith("_co"))
        groups.setdefault(SEOUL_TO_SERVICE[source], {}).setdefault(quarter, {})[source] = row

    results = []
    for code, name in SERVICE_INDUSTRIES.items():
        observed = groups.get(code, {})
        sources = INDUSTRY_TO_SEOUL.get(code, ())
        quarterly: dict[str, dict[str, float]] = {}
        for quarter in quarters:
            source_rows = observed.get(quarter, {})
            # 일부 원천이 빠지면 업종 전체 합계라고 주장할 수 없습니다.
            complete_sources = set(source_rows) == set(sources) and bool(sources)
            quarterly[quarter] = {
                field: (
                    sum(row[field] for row in source_rows.values())
                    if complete_sources
                    else float("nan")
                )
                for field in ("similr_induty_stor_co", "opbiz_stor_co", "clsbiz_stor_co")
            }

        def total(
            field: str,
            period: list[str],
            values: dict[str, dict[str, float]] = quarterly,
        ) -> float:
            # sum은 NaN을 전파하므로 일부 결측을 0으로 보충하지 않습니다.
            return sum(values[q][field] for q in period)

        exposure = total("similr_induty_stor_co", quarters)
        opened = total("opbiz_stor_co", quarters)
        closed = total("clsbiz_stor_co", quarters)
        recent = quarters[-4:]
        recent_exposure = total("similr_induty_stor_co", recent)
        recent_opened = total("opbiz_stor_co", recent)
        recent_closed = total("clsbiz_stor_co", recent)
        recent_rate = calculate_rate(recent_closed, recent_exposure)
        oldest_rate = calculate_rate(
            total("clsbiz_stor_co", quarters[:4]),
            total("similr_induty_stor_co", quarters[:4]),
        )
        complete = all(pd.notna(v) for values in quarterly.values() for v in values.values())
        if code in UNSUPPORTED_SERVICE_INDUSTRIES:
            status, reason = "unsupported", "서울시 생활밀접업종 데이터에 직접 대응 업종 없음"
        elif not observed:
            status, reason = (
                "missing",
                f"최근 {quarter_count}개 분기에 대응 서울시 업종 데이터 없음",
            )
        elif not complete:
            status, reason = (
                "incomplete",
                "요청 분기·원본업종 또는 건수 일부 누락으로 완전 집계 불가",
            )
        else:
            status, reason = "observed", None
        results.append(
            {
                "service_id": code,
                "service_name": name,
                "data_available": bool(observed),
                "data_status": status,
                "data_complete": complete,
                "observed_quarters": len(observed),
                "expected_source_count": len(sources),
                "observed_source_rows": sum(len(values) for values in observed.values()),
                "expected_source_rows": len(sources) * quarter_count,
                "latest_store_count": quarterly[base_quarter]["similr_induty_stor_co"],
                "avg_store_count": exposure / quarter_count,
                "period_open_count": opened,
                "period_close_count": closed,
                "period_net_change": opened - closed,
                "avg_open_rate": calculate_rate(opened, exposure),
                "avg_close_rate": calculate_rate(closed, exposure),
                "net_change_rate": calculate_rate(opened - closed, exposure),
                "turnover_rate": calculate_rate(opened + closed, exposure),
                "recent_year_open_count": recent_opened,
                "recent_year_close_count": recent_closed,
                "recent_year_net_change": recent_opened - recent_closed,
                "recent_year_close_rate": recent_rate,
                "recent_year_net_change_rate": calculate_rate(
                    recent_opened - recent_closed, recent_exposure
                ),
                "oldest_year_close_rate": oldest_rate,
                "close_rate_trend": (
                    round(recent_rate - oldest_rate, 2)
                    if recent_rate is not None and oldest_rate is not None
                    else None
                ),
                "source_industry_count": len({s for values in observed.values() for s in values}),
                "source_industries": " | ".join(
                    sorted(
                        {
                            str(row.get("svc_induty_cd_nm") or source)
                            for values in observed.values()
                            for source, row in values.items()
                        }
                    )
                ),
                "missing_reason": reason,
            }
        )
    return pd.DataFrame(results)

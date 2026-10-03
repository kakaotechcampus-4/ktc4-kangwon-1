"""계산된 인구 자료에서 최종판단에 전달할 블록을 고릅니다."""

import json
from collections.abc import Awaitable, Callable

from .schemas import FloatingPopulationData, Selection

SelectBlocks = Callable[[str], Awaitable[tuple[list[str], str]]]
SELECTABLE = ("trade_areas", "population_raw", "radius_profile", "trend")


class SelectionUnavailable(RuntimeError):
    """선별 불가 시 전체 자료를 유지합니다."""


def _selection_digest(data: FloatingPopulationData) -> str:
    """선별 모델에게 보낼 요약. **`data` 전체를 보내지 않는다.**

    전체를 보내면 줄이려던 토큰을 선별하느라 그대로 쓰게 된다. 블록마다 "읽을 게 있는지" 를
    판단할 최소 정보만 추린다 — 개수, 값의 폭, 0 이 몇 개인지 같은 것들.
    """
    rp = data.radius_profile
    tr = data.trend
    digest = {
        "지역": data.description[:120],
        "유형": data.type.label,
        "신뢰도": data.reliability.level,
        "trade_areas": {
            "개수": len(data.trade_areas or []),
            "이름": [t.name for t in (data.trade_areas or [])][:12],
            "행정동": sorted({t.adstrd for t in (data.trade_areas or []) if t.adstrd}),
        },
        "population_raw": {
            "설명": "연령·시간대·요일 원값(분기 합계). 같은 내용의 비중이 따로 있음",
            "비중_이미_있음": True,
        },
        "radius_profile": {
            "단계": [p.radius_m for p in (rp.points if rp else [])],
            "일평균": [round(p.daily_avg) for p in (rp.points if rp else [])],
            "값이_0인_단계수": sum(1 for p in (rp.points if rp else []) if p.daily_avg <= 0),
        },
        "trend": {
            "분기수": len(tr.quarters) if tr else 0,
            "방향": tr.direction if tr else None,
            "전분기_변화율": tr.qoq_change if tr else None,
            "전년동기_변화율": tr.yoy_change if tr else None,
            "일평균_추이": [round(q.daily_avg) for q in (tr.quarters if tr else [])],
        },
    }
    return json.dumps(digest, ensure_ascii=False)


async def _select(
    data: FloatingPopulationData,
    select: SelectBlocks | None,
) -> tuple[Selection, str | None]:
    """블록을 고른다. 실패하면 전부 싣고 그 사실을 경고로 돌려준다."""
    selectable = list(SELECTABLE)
    if select is None:
        included = []
        if data.trade_areas:
            included.append("trade_areas")
        if data.radius_profile and data.radius_profile.points:
            included.append("radius_profile")
        if data.trend and len(data.trend.quarters) >= 2:
            included.append("trend")
        return Selection(
            applied=True,
            selectable=selectable,
            included=included,
            dropped=[name for name in selectable if name not in included],
            reason="중복 원값과 비어 있거나 비교 분기가 부족한 자료를 제외했습니다.",
        ), None
    try:
        included, reason = await select(_selection_digest(data))
    except SelectionUnavailable:
        return (
            Selection(
                applied=False,
                selectable=selectable,
                included=selectable,
                dropped=[],
                unavailable_reason="자료 선별 기능을 사용할 수 없습니다.",
            ),
            None,  # 키가 없어 못 한 경우까지 경고로 띄우면 시끄럽다
        )
    except (RuntimeError, ValueError):
        return (
            Selection(
                applied=False,
                selectable=selectable,
                included=selectable,
                dropped=[],
                unavailable_reason="자료 선별 중 오류가 발생했습니다.",
            ),
            "자료 선별에 실패해 전부 실었습니다.",
        )

    dropped = [b for b in selectable if b not in included]
    return (
        Selection(
            applied=True,
            selectable=selectable,
            included=included,
            dropped=dropped,
            reason=(reason or None) if dropped else None,
        ),
        None,
    )

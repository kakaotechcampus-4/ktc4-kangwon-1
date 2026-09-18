"""넘길 블록을 고르는 LLM 호출 (엘리스 OpenAI 호환 API).

**숫자는 절대 모델이 만들지 않는다.** 모델이 하는 일은 이미 계산된 선택 가능 블록 넷 중
무엇을 실을지 고르는 것뿐이고, 고른 결과도 허용 목록 안인지 코드가 다시 확인한다
(`AGENTS.md` 4번 — 모델 응답을 그대로 믿지 않는다).

왜 고르는가: `data` 가 결정 에이전트 프롬프트에 통째로 실린다. 실측(길동, 2026Q2)으로
`data` 6,944자 중 결정이 판단에 쓰는 `benchmark`·`type`·`reliability` 는 995자(14%)뿐이고
나머지는 리포트용 차트 시리즈다. 분석 에이전트가 셋이라 그대로 두면 판단 지표가 묻힌다.

**실패하면 전부 싣는다.** 선별은 최적화지 기능이 아니다 — 키가 없거나 모델이 죽어도 분석은
그대로 나가야 한다. 그래서 여기서 나가는 예외는 `agent.py` 가 잡아 경고로만 남긴다.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.llm import client
from app.llm.config import LLMSettings

from .schemas import FloatingPopulationData, Selection

SelectBlocks = Callable[[str], Awaitable[tuple[list[str], str]]]

PACKAGE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = PACKAGE_DIR / "prompt.md"

# 모델이 고를 수 있는 블록. 이 밖의 이름이 오면 응답 전체를 버린다.
SELECTABLE = ("trade_areas", "population_raw", "radius_profile", "trend")


class SelectionUnavailable(RuntimeError):
    """선별을 못 했다(키 없음·모델 오류·형식 불량). 전부 싣는 것으로 되돌린다."""


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def parse_selection(content: str) -> tuple[list[str], str]:
    """모델 응답 → (실을 블록, 뺀 이유). 조금이라도 어긋나면 예외를 낸다.

    모델이 `population` 처럼 **항상 실리는 블록**을 골라 보내는 일이 있다. 그건 선택 대상이
    아니므로 허용 목록 밖으로 보고 응답을 버린다 — 조용히 무시하면 모델이 뭘 고른 건지
    추적할 수 없다.
    """
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SelectionUnavailable(f"모델 응답이 JSON 이 아닙니다: {exc}") from exc
    if not isinstance(parsed, dict):
        raise SelectionUnavailable("모델 응답이 JSON 객체가 아닙니다.")

    include = parsed.get("include")
    if not isinstance(include, list) or not all(isinstance(x, str) for x in include):
        raise SelectionUnavailable("include 는 문자열 배열이어야 합니다.")
    unknown = [x for x in include if x not in SELECTABLE]
    if unknown:
        raise SelectionUnavailable(f"고를 수 없는 블록을 인용했습니다: {', '.join(unknown)}")

    reason = parsed.get("dropped_reason", "")
    if not isinstance(reason, str):
        raise SelectionUnavailable("dropped_reason 은 문자열이어야 합니다.")
    # 중복 제거하되 순서는 SELECTABLE 기준으로 고정한다 — 같은 선택이면 항상 같은 순서여야
    # 리포트가 흔들리지 않는다.
    return [b for b in SELECTABLE if b in include], reason.strip()


async def select_blocks(payload: str, settings: LLMSettings | None = None) -> tuple[list[str], str]:
    """선별 실패는 분석 단계에서 모든 계산 블록을 유지하는 경고로 바뀝니다."""
    try:
        result = await client.complete_json(
            load_prompt(), payload, settings or LLMSettings.from_env("FLOATING_POPULATION")
        )
        return parse_selection(json.dumps(result, ensure_ascii=False))
    except (RuntimeError, ValueError):
        raise SelectionUnavailable(
            "모델 선별을 완료하지 못했습니다. 설정과 응답을 확인해 주세요."
        ) from None


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
    try:
        included, reason = await (select or select_blocks)(_selection_digest(data))
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
    except Exception:  # 모델 쪽 어떤 실패도 분석을 막지 않는다
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

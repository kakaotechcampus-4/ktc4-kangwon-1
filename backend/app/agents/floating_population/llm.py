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
import math
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = PACKAGE_DIR / "prompt.md"

# 모델이 고를 수 있는 블록. 이 밖의 이름이 오면 응답 전체를 버린다.
SELECTABLE = ("trade_areas", "population_raw", "radius_profile", "trend")


class SelectionUnavailable(RuntimeError):
    """선별을 못 했다(키 없음·모델 오류·형식 불량). 전부 싣는 것으로 되돌린다."""


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _env() -> tuple[str, str, str, int, float]:
    model = os.getenv("ELICE_MODEL", "").strip()
    api_key = os.getenv("ELICE_API_KEY", "").strip()
    base_url = os.getenv("ELICE_BASE_URL", "").strip()
    if not (model and api_key and base_url):
        raise SelectionUnavailable(
            "ELICE_MODEL·ELICE_API_KEY·ELICE_BASE_URL 이 있어야 블록 선별을 합니다."
        )
    try:
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "8192"))
        timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    except ValueError as exc:
        raise SelectionUnavailable("응답 길이와 대기 시간은 양수여야 합니다.") from exc
    if max_tokens <= 0 or not math.isfinite(timeout) or timeout <= 0:
        raise SelectionUnavailable("응답 길이와 대기 시간은 양수여야 합니다.")
    return model, api_key, base_url, max_tokens, timeout


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


async def select_blocks(payload: str) -> tuple[list[str], str]:
    """`payload`(선별용 요약 JSON)를 보고 실을 블록을 고른다."""
    model, api_key, base_url, max_tokens, timeout = _env()
    try:
        from openai import APIError, AsyncOpenAI
    except ImportError as exc:
        raise SelectionUnavailable("openai 패키지가 없습니다.") from exc

    try:
        async with AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1
        ) as client:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": load_prompt()},
                    {"role": "user", "content": payload},
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=max_tokens,
            )
    except APIError as exc:
        raise SelectionUnavailable(f"모델 요청에 실패했습니다: {exc}") from exc

    if not response.choices:
        raise SelectionUnavailable("모델이 응답을 내지 못했습니다.")
    choice = response.choices[0]
    if choice.finish_reason != "stop" or not choice.message.content:
        raise SelectionUnavailable("모델이 응답을 끝맺지 못했습니다(길이 제한 또는 거절).")
    return parse_selection(choice.message.content)

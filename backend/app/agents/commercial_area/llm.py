"""엘리스 클라우드의 OpenAI 호환 API로 분석 결과를 문장으로 풀어냅니다."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from .config import PACKAGE_DIR, Settings

PROMPT_PATH = PACKAGE_DIR / "prompt.md"
MAX_SUMMARY_CHARS = 900
MAX_NOTE_CHARS = 200
MAX_ATTEMPTS = 2
RETRY_DELAY_S = 1.0


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        return ""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_user_message(data: dict[str, Any]) -> str:
    slices = data.get("by_radius", [])
    trimmed = {
        "radius_m": data.get("radius_m"),
        "store_total": data.get("store_total"),
        "반경별_점포수": [
            {
                "반경m": s["radius_m"],
                "점포수": s["store_total"],
                "없는업종수": s["absent_category_count"],
            }
            for s in slices
        ],
        "반경별_요약": [
            {
                "반경m": s["radius_m"],
                "많은업종": [
                    {"업종": r["name"], "개수": r["count"]} for r in s["top_by_count"][:5]
                ],
                "특화업종": [
                    {"업종": r["name"], "주변대비배수": round(r["times_vs_surroundings"], 2)}
                    for r in s["top_by_specialization"][:5]
                ],
            }
            for s in slices
        ],
        "자치구_이름": (data.get("district_baseline") or {}).get("signgu_name"),
        "자치구_전체_대비_특화업종": [
            {
                "업종": r["name"],
                "개수": r["count"],
                "자치구대비배수": round(r["times_vs_surroundings"], 2),
            }
            for r in data.get("district_specialization", [])[:5]
        ],
        "by_major": [
            {"name": row["name"], "count": row["count"]} for row in data.get("by_major", [])
        ],
        "diversity": data.get("diversity"),
        "restaurant_density": data.get("restaurant_density"),
        "franchise": {
            "count": (data.get("franchise") or {}).get("count"),
            "ratio": (data.get("franchise") or {}).get("ratio"),
        }
        if data.get("franchise")
        else None,
    }
    return json.dumps(trimmed, ensure_ascii=False)


async def summarize(
    data: dict[str, Any], settings: Settings
) -> tuple[dict[str, Any] | None, str | None]:
    if not settings.llm_model:
        return None, "ELICE_MODEL이 설정되지 않아 요약을 생략했습니다."
    if not settings.llm_api_key:
        return None, "ELICE_API_KEY가 설정되지 않아 요약을 생략했습니다."
    if not settings.llm_base_url:
        return None, "ELICE_BASE_URL이 설정되지 않아 요약을 생략했습니다."

    system_prompt = load_prompt()
    user_message = build_user_message(data)

    last_problem = "모델이 빈 응답을 반환했습니다."
    for attempt in range(MAX_ATTEMPTS):
        try:
            text = await _complete(system_prompt, user_message, settings)
        except Exception as exc:
            last_problem = f"요약 실패: {type(exc).__name__}"
            text = None
        if text and text.strip():
            summary = parse_summary(text)
            if summary["radius_notes"] or summary["overall"]:
                return summary, None
            last_problem = "모델 응답에서 요약 내용을 찾지 못했습니다."
        if attempt < MAX_ATTEMPTS - 1:
            await asyncio.sleep(RETRY_DELAY_S)
    return None, last_problem


async def _complete(system_prompt: str, user_message: str, settings: Settings) -> str:
    from openai import AsyncOpenAI

    model = settings.llm_model
    if not model:
        raise ValueError("ELICE_MODEL이 설정되지 않았습니다.")

    async with AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_s,
        max_retries=1,
    ) as client:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=settings.llm_max_tokens,
        )
    if not response.choices:
        return ""
    return response.choices[0].message.content or ""


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_summary(text: str) -> dict[str, Any]:
    cleaned = strip_code_fence(text)
    payload: Any = None
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                payload = None

    if not isinstance(payload, dict):
        return {"radius_notes": [], "overall": cleaned[:MAX_SUMMARY_CHARS], "concentration": None}

    notes = []
    for row in payload.get("radius_notes") or []:
        if not isinstance(row, dict):
            continue
        try:
            raw_radius: Any = row.get("radius_m")
            radius = int(raw_radius)
        except (TypeError, ValueError):
            continue
        note = str(row.get("text") or "").strip()
        if note:
            notes.append({"radius_m": radius, "text": note[:MAX_NOTE_CHARS]})

    def field(name: str) -> str | None:
        value = payload.get(name)
        value = str(value).strip() if value else ""
        return value[:MAX_SUMMARY_CHARS] or None

    return {
        "radius_notes": sorted(notes, key=lambda r: r["radius_m"]),
        "overall": field("overall"),
        "concentration": field("concentration"),
    }


def render_summary_text(summary: dict[str, Any]) -> str | None:
    parts = [f"{n['radius_m']}m: {n['text']}" for n in summary.get("radius_notes") or []]
    if summary.get("overall"):
        parts.append(f"종합 평가: {summary['overall']}")
    if summary.get("concentration"):
        parts.append(f"집적도·특화도 평가: {summary['concentration']}")
    return "\n".join(parts) or None

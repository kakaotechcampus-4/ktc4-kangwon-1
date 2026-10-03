"""계산된 요약을 표시용 문장으로 변환합니다."""

from typing import Any


def render_summary_text(summary: dict[str, Any]) -> str | None:
    parts = [f"{n['radius_m']}m: {n['text']}" for n in summary.get("radius_notes") or []]
    if summary.get("overall"):
        parts.append(f"종합 평가: {summary['overall']}")
    if summary.get("concentration"):
        parts.append(f"집적도·특화도 평가: {summary['concentration']}")
    parts += [f"{n['label']}: {n['text']}" for n in summary.get("index_notes") or []]
    return "\n".join(parts) or None

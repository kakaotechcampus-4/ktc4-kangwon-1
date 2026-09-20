"""요약이 prompt.md 의 규칙을 지켰는지 검사합니다."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .trade_areas import MAX_RESULTS as TRADE_AREA_CAP

PATH_SPEC: tuple[tuple[str, str], ...] = (
    ("/by_middle", "주변보다 많은 업종"),
    ("/diversity/effective_categories", "업종 다양성"),
    ("/store_total", "같은 업종과 다른 업종"),
    ("/restaurant_density/value", "음식점 밀집도"),
    ("/franchise/independent_ratio", "프랜차이즈와 개인가게"),
    ("/trade_areas", "상권 유형"),
    ("/by_major", "같은 성격 가게의 군집"),
)

FORBIDDEN_TERMS: tuple[str, ...] = (
    "LQ",
    "입지계수",
    "자치구 대비 배수",
    "특화도",
    "집적도",
    "밀도",
    "HHI",
    "허핀달",
    "마샬리안",
    "제이코비안",
    "중분류",
    "업종코드",
)

JUDGEMENT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("유리", r"유리(하|합|했|한|해)"),
    ("불리", r"불리(하|합|했|한|해)"),
    ("좋은 상권", r"좋은\s*상권"),
    ("나쁜 상권", r"나쁜\s*상권"),
    ("유망", r"유망"),
)

RECOMMENDATION_WORDS: tuple[str, ...] = ("추천", "창업", "권합니다", "권장")

SEOUL_DISTRICTS: tuple[str, ...] = (
    "종로구",
    "중구",
    "용산구",
    "성동구",
    "광진구",
    "동대문구",
    "중랑구",
    "성북구",
    "강북구",
    "도봉구",
    "노원구",
    "은평구",
    "서대문구",
    "마포구",
    "양천구",
    "강서구",
    "구로구",
    "금천구",
    "영등포구",
    "동작구",
    "관악구",
    "서초구",
    "강남구",
    "송파구",
    "강동구",
)

EMPTY_STORE_OVERALL = "반경 안에 조회된 점포가 없습니다."

MAX_RADIUS_NOTE_CHARS = 100
MAX_INDEX_NOTE_CHARS = 120
PAYLOAD_WARN_CHARS = 48_000
PAYLOAD_ERROR_CHARS = 50_000
PERCENTILE_TOLERANCE = 3.0

COUNT_PATTERN = re.compile(r"(\d+)\s*곳")
PERCENTILE_PATTERN = re.compile(r"상위\s*약?\s*(\d+(?:\.\d+)?)\s*%")
MULTIPLE_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*배")
RADIUS_BASELINE_PATTERN = re.compile(r"반경|주변")
DISTRICT_BASELINE_PATTERN = re.compile(r"자치구|구\s*전체")


@dataclass(frozen=True)
class Violation:
    code: str
    severity: str
    message: str


def _index_notes(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in (summary.get("index_notes") or []) if isinstance(n, dict)]


def _radius_notes(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in (summary.get("radius_notes") or []) if isinstance(n, dict)]


def _radius_sequence(rows: list[dict[str, Any]]) -> list[int]:
    found: list[int] = []
    for row in rows:
        try:
            found.append(int(row["radius_m"]))
        except (KeyError, TypeError, ValueError):
            continue
    return found


def _radii(rows: list[dict[str, Any]]) -> set[int]:
    return set(_radius_sequence(rows))


def _note_by_path(summary: dict[str, Any], path: str) -> dict[str, Any] | None:
    for note in _index_notes(summary):
        if note.get("path") == path:
            return note
    return None


def _all_texts(summary: dict[str, Any]) -> list[str]:
    texts = [str(n.get("text") or "") for n in _radius_notes(summary)]
    texts += [str(summary.get(key) or "") for key in ("overall", "concentration")]
    texts += [str(n.get("text") or "") for n in _index_notes(summary)]
    return [t for t in texts if t]


def _proper_nouns(data: dict[str, Any]) -> tuple[str, ...]:
    names = [str(t.get("name") or "") for t in (data.get("trade_areas") or [])]
    names += [str(r.get("name") or "") for r in (data.get("by_middle") or [])]
    names += [str(r.get("name") or "") for r in (data.get("by_major") or [])]
    return tuple(sorted({n for n in names if n}, key=len, reverse=True))


def _mask(text: str, nouns: tuple[str, ...]) -> str:
    for noun in nouns:
        text = text.replace(noun, " ")
    return text


def _has_source(data: dict[str, Any], path: str) -> bool:
    by_middle = data.get("by_middle") or []
    if path in ("/by_middle", "/store_total"):
        return bool(by_middle)
    if path == "/diversity/effective_categories":
        return data.get("diversity") is not None
    if path == "/restaurant_density/value":
        return data.get("restaurant_density") is not None
    if path == "/franchise/independent_ratio":
        return data.get("franchise") is not None
    if path == "/trade_areas":
        return bool(data.get("trade_areas"))
    if path == "/by_major":
        return any(row.get("major_cluster_count") for row in by_middle)
    return False


def _check_index_notes(summary: dict[str, Any], data: dict[str, Any]) -> list[Violation]:
    allowed = dict(PATH_SPEC)
    order = {path: index for index, (path, _) in enumerate(PATH_SPEC)}
    found: list[Violation] = []
    positions: list[int] = []
    seen: list[str] = []
    for note in _index_notes(summary):
        path = str(note.get("path") or "")
        if path not in allowed:
            found.append(Violation("PATH_UNKNOWN", "error", f"허용되지 않은 경로입니다: {path}"))
            continue
        if path in seen:
            found.append(Violation("DUPLICATE_NOTE", "error", f"{path} 를 두 번 설명했습니다."))
            continue
        seen.append(path)
        positions.append(order[path])
        label = str(note.get("label") or "")
        if label != allowed[path]:
            found.append(
                Violation(
                    "LABEL_MISMATCH",
                    "error",
                    f"{path} 의 이름표가 {label} 입니다. 표에는 {allowed[path]} 입니다.",
                )
            )
        if not _has_source(data, path):
            found.append(
                Violation("NULL_NOTE", "error", f"입력에 값이 없는데 {path} 를 설명했습니다.")
            )
        if len(str(note.get("text") or "")) > MAX_INDEX_NOTE_CHARS:
            found.append(
                Violation(
                    "LEN_INDEX_NOTE",
                    "warn",
                    f"{path} 설명이 {MAX_INDEX_NOTE_CHARS}자를 넘습니다.",
                )
            )
    if data.get("store_total") != 0:
        for path, _ in PATH_SPEC:
            if path not in seen and _has_source(data, path):
                found.append(
                    Violation(
                        "MISSING_NOTE",
                        "error",
                        f"입력에 값이 있는데 {path} 를 설명하지 않았습니다.",
                    )
                )
    if positions != sorted(positions):
        found.append(Violation("NOTE_ORDER", "warn", "지표 풀이가 표 순서와 다릅니다."))
    return found


def _check_radius_notes(summary: dict[str, Any], data: dict[str, Any]) -> list[Violation]:
    found: list[Violation] = []
    notes = _radius_notes(summary)
    if data.get("store_total") == 0:
        if notes:
            found.append(
                Violation("EMPTY_STORE", "error", "점포가 0개인데 반경별 설명을 넣었습니다.")
            )
        if str(summary.get("overall") or "").strip() != EMPTY_STORE_OVERALL:
            found.append(
                Violation(
                    "EMPTY_STORE_TEXT",
                    "error",
                    f"점포가 0개면 종합 평가는 '{EMPTY_STORE_OVERALL}' 여야 합니다.",
                )
            )
        return found
    expected = _radii(data.get("by_radius") or [])
    sequence = _radius_sequence(notes)
    actual = set(sequence)
    if actual != expected:
        found.append(
            Violation(
                "RADIUS_SET",
                "error",
                f"반경이 {sorted(actual)} 인데 입력은 {sorted(expected)} 입니다.",
            )
        )
    if sequence != sorted(sequence):
        found.append(
            Violation("RADIUS_ORDER", "warn", "반경별 설명이 좁은 것부터 순서가 아닙니다.")
        )
    for note in notes:
        if len(str(note.get("text") or "")) > MAX_RADIUS_NOTE_CHARS:
            found.append(
                Violation(
                    "LEN_RADIUS_NOTE",
                    "warn",
                    f"{note.get('radius_m')}m 설명이 {MAX_RADIUS_NOTE_CHARS}자를 넘습니다.",
                )
            )
    return found


def _check_summary_fields(summary: dict[str, Any], data: dict[str, Any]) -> list[Violation]:
    if data.get("store_total") == 0:
        return []
    found: list[Violation] = []
    if not str(summary.get("overall") or "").strip():
        found.append(Violation("MISSING_OVERALL", "error", "종합 평가가 비었습니다."))
    if not str(summary.get("concentration") or "").strip():
        found.append(Violation("MISSING_CONCENTRATION", "error", "집적도 평가가 비었습니다."))
    return found


def _check_wording(summary: dict[str, Any], data: dict[str, Any]) -> list[Violation]:
    found: list[Violation] = []
    nouns = _proper_nouns(data)
    for text in _all_texts(summary):
        masked = _mask(text, nouns).lower()
        for term in FORBIDDEN_TERMS:
            plain = term.lower()
            if plain in masked or plain.replace(" ", "") in masked:
                found.append(Violation("FORBIDDEN_TERM", "error", f"전문용어를 썼습니다: {term}"))
        for word in RECOMMENDATION_WORDS:
            if word in masked:
                found.append(
                    Violation("RECOMMENDATION", "warn", f"권유로 읽힐 수 있습니다: {word}")
                )
    for note in _index_notes(summary):
        masked = _mask(str(note.get("text") or ""), nouns)
        for label, pattern in JUDGEMENT_PATTERNS:
            if re.search(pattern, masked):
                found.append(
                    Violation("JUDGEMENT_WORD", "warn", f"좋고 나쁨을 말했습니다: {label}")
                )
    return found


def _check_district(summary: dict[str, Any], data: dict[str, Any]) -> list[Violation]:
    name = (data.get("district_baseline") or {}).get("signgu_name")
    nouns = _proper_nouns(data)
    mentioned = {
        district
        for text in _all_texts(summary)
        for district in SEOUL_DISTRICTS
        if district in _mask(text, nouns)
    }
    if not name:
        if mentioned:
            return [
                Violation(
                    "DISTRICT_NAME",
                    "error",
                    f"자치구 이름이 입력에 없는데 {sorted(mentioned)} 를 썼습니다.",
                )
            ]
        return []
    wrong = sorted(mentioned - {name})
    if wrong:
        return [Violation("DISTRICT_NAME", "error", f"자치구가 {name} 인데 {wrong} 를 썼습니다.")]
    return []


def _check_baselines(summary: dict[str, Any], data: dict[str, Any]) -> list[Violation]:
    found: list[Violation] = []
    name = (data.get("district_baseline") or {}).get("signgu_name")
    note = _note_by_path(summary, "/by_middle")
    if note is not None:
        text = str(note.get("text") or "")
        if MULTIPLE_PATTERN.search(text):
            if not RADIUS_BASELINE_PATTERN.search(text):
                found.append(
                    Violation(
                        "BASELINE_MISSING",
                        "error",
                        "주변보다 많은 업종에서 반경 기준을 밝히지 않았습니다.",
                    )
                )
            if name and name not in text:
                found.append(
                    Violation(
                        "BASELINE_MISSING",
                        "error",
                        f"주변보다 많은 업종에서 {name} 기준을 함께 밝히지 않았습니다.",
                    )
                )
    if not name:
        for text in _all_texts(summary):
            if MULTIPLE_PATTERN.search(text) and DISTRICT_BASELINE_PATTERN.search(text):
                found.append(
                    Violation(
                        "DISTRICT_BASELINE",
                        "error",
                        "자치구 이름이 입력에 없는데 자치구 기준 배수를 말했습니다.",
                    )
                )
                break
    return found


def _check_trade_areas(summary: dict[str, Any], data: dict[str, Any]) -> list[Violation]:
    found: list[Violation] = []
    total = len(data.get("trade_areas") or [])
    if total >= TRADE_AREA_CAP:
        found.append(
            Violation(
                "TRADE_AREA_CAPPED",
                "warn",
                f"상권 목록이 상한 {TRADE_AREA_CAP}곳에 걸려 실제 개수를 확인할 수 없습니다.",
            )
        )
    note = _note_by_path(summary, "/trade_areas")
    if note is None:
        return found
    said = [int(value) for value in COUNT_PATTERN.findall(str(note.get("text") or ""))]
    if not said:
        return found
    if total not in said:
        spoken = ", ".join(f"{value}곳" for value in said)
        found.append(
            Violation("TRADE_AREA_COUNT", "error", f"상권이 {total}곳인데 {spoken} 이라 했습니다.")
        )
    return found


def _check_percentile(summary: dict[str, Any], data: dict[str, Any]) -> list[Violation]:
    note = _note_by_path(summary, "/restaurant_density/value")
    if note is None:
        return []
    match = PERCENTILE_PATTERN.search(str(note.get("text") or ""))
    percentile = (data.get("restaurant_density") or {}).get("seoul_percentile")
    if percentile is None:
        if match:
            return [
                Violation("PERCENTILE_FLIP", "error", "서울 백분위가 없는데 순위를 말했습니다.")
            ]
        return []
    if match is None:
        return []
    said = float(match.group(1))
    expected = 100.0 - float(percentile)
    if abs(said - expected) > PERCENTILE_TOLERANCE:
        return [
            Violation(
                "PERCENTILE_FLIP",
                "error",
                f"백분위 {percentile} 이면 상위 약 {expected:.0f}% 인데 {said:g}% 라 했습니다.",
            )
        ]
    return []


def check_payload_size(data: dict[str, Any]) -> list[Violation]:
    size = len(json.dumps(data, ensure_ascii=False))
    if size >= PAYLOAD_ERROR_CHARS:
        return [
            Violation("PAYLOAD_SIZE", "error", f"data 가 {size:,}자로 결정 단계 예산을 넘습니다.")
        ]
    if size >= PAYLOAD_WARN_CHARS:
        return [Violation("PAYLOAD_SIZE", "warn", f"data 가 {size:,}자로 예산에 근접했습니다.")]
    return []


def check(data: dict[str, Any], summary: dict[str, Any]) -> list[Violation]:
    found = _check_radius_notes(summary, data)
    found += _check_index_notes(summary, data)
    found += _check_summary_fields(summary, data)
    found += _check_wording(summary, data)
    found += _check_district(summary, data)
    found += _check_baselines(summary, data)
    found += _check_trade_areas(summary, data)
    found += _check_percentile(summary, data)
    found += check_payload_size(data)
    return list(dict.fromkeys(found))


def errors(violations: list[Violation]) -> list[Violation]:
    return [v for v in violations if v.severity == "error"]

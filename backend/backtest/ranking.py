from typing import Any

from app.agentic.scoring import adjusted_lower, regulation
from app.industries.catalog import INDUSTRIES, INDUSTRIES_WITHOUT_SEOUL

ITEMS = ("D1", "D2", "D3", "D4", "C1", "C4", "S1", "S2", "S3", "S4", "L")
DOMAINS = {"D": ("D1", "D2", "D3", "D4"), "C": ("C1", "C4"), "S": ("S1", "S2", "S3", "S4")}
G_PROBE = {"status": "ok", "zones": [{"name": "상대보호구역"}]}
G_INDUSTRIES = frozenset(code for code in INDUSTRIES if regulation(code, G_PROBE) != "해당 없음")


def _order(row: dict) -> tuple[bool, float, float]:
    blocked = row["regulation"] == "금지" or row.get("space", {}).get("excluded", False)
    return (blocked, -adjusted_lower(row), -(row["coverage"] or 0))


def rank_rows(rows: list[dict]) -> list[dict]:
    ordered = sorted(rows, key=lambda row: (*_order(row), row["code"]))
    ranked: list[dict] = []
    previous: tuple[bool, float, float] | None = None
    rank = 0
    for index, row in enumerate(ordered, 1):
        key = _order(row)
        if key != previous:
            rank, previous = index, key
        ranked.append({**row, "rank": rank})
    return ranked


def count_ranks(counts: dict[str, int], codes: list[str]) -> dict[str, int]:
    values = {code: counts.get(code, 0) for code in codes}
    ranks: dict[str, int] = {}
    previous: int | None = None
    rank = 0
    for index, code in enumerate(sorted(values, key=lambda c: (-values[c], c)), 1):
        if values[code] != previous:
            rank, previous = index, values[code]
        ranks[code] = rank
    return ranks


def _points(row: dict, items: tuple[str, ...]) -> float:
    return sum(row["items"][name]["points"] or 0 for name in items)


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def target_summary(ranked: list[dict], target: str, counts: dict[str, int]) -> dict[str, Any]:
    row = next(r for r in ranked if r["code"] == target)
    others = [r for r in ranked if r["code"] != target]
    mean_lower = sum(r["lower"] for r in ranked) / len(ranked)
    store_ranks = count_ranks(counts, [r["code"] for r in ranked])
    summary: dict[str, Any] = {
        "순위": row["rank"],
        "업종 수": len(ranked),
        "상위5 업종 수": sum(r["rank"] <= 5 for r in ranked),
        "하한": round(row["lower"], 2),
        "coverage": _round(row["coverage"], 3),
        "배지": row["badge"],
        "규제": row["regulation"],
        "주소 평균 하한": round(mean_lower, 2),
        "평균 대비": round(row["lower"] - mean_lower, 2),
        "점포 수": counts.get(target, 0),
        "점포 수 순위": store_ranks[target],
        "서울 자료 없음": target in INDUSTRIES_WITHOUT_SEOUL,
        "현재 시점 C4": row["items"]["C4"]["status"] != "n.a.",
        "현재 시점 G": target in G_INDUSTRIES,
    }
    for domain, items in DOMAINS.items():
        rest = sum(_points(r, items) for r in others) / len(others) if others else 0.0
        summary[f"{domain} 차이"] = round(_points(row, items) - rest, 2)
    return summary


def score_rows(key: str, ranked: list[dict]) -> list[dict[str, Any]]:
    rows = []
    for row in ranked:
        cells = {
            name: row["items"][name]["points"]
            if row["items"][name]["status"] == "observed"
            else row["items"][name]["status"]
            for name in ITEMS
        }
        rows.append(
            {
                "행": key,
                "업종 코드": row["code"],
                "업종": row["name"],
                "순위": row["rank"],
                "하한": round(row["lower"], 2),
                "상한": round(row["upper"], 2),
                "coverage": _round(row["coverage"], 3),
                "배지": row["badge"],
                "규제": row["regulation"],
                **cells,
            }
        )
    return rows

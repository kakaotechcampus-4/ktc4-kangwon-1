"""시점 분리 전진 검증의 지표를 계산합니다. 파일·DB를 읽지 않는 순수 함수만 둡니다.

상권 기록 하나는 다음 형태입니다.
    {"area": 상권 코드, "district": 자치구 코드,
     "orders": {방식: 추천 순서대로 나열한 업종 코드},
     "badges": {업종: 배지},
     "outcomes": {업종: {"closed": 폐업 수, "opened": 개업 수, "exposure": 분기 점포 수 합계,
                        "expected": 서울 같은 업종 폐업률로 본 기대 폐업 수}}}
outcomes에는 이후 성과를 측정할 수 있는 업종만 들어 있습니다.

업종·상권마다 점포가 적어 1년 폐업이 0~2건인 칸이 많습니다. 칸별 비율을 평균하면 잡음이 커서
실제 폐업 합 / 기대 폐업 합(표준화 폐업비)으로 묶어 계산합니다. 1보다 작으면 서울 같은 업종보다
덜 닫았다는 뜻입니다.
"""

import random
from collections import Counter, defaultdict

TOP_N = 5
RANK_BANDS = ((1, 5), (6, 10), (11, 20), (21, 51))
FIELDS = ("closed", "expected", "opened", "exposure")


def empty() -> dict[str, float]:
    return dict.fromkeys(FIELDS, 0.0)


def add(target: dict, outcome: dict) -> None:
    for field in FIELDS:
        target[field] += outcome[field]


def ratio(sums: dict) -> float | None:
    return sums["closed"] / sums["expected"] if sums["expected"] > 0 else None


def rates(sums: dict) -> dict:
    exposure = sums["exposure"]
    return {
        "scr": ratio(sums),
        "close_rate": 100 * sums["closed"] / exposure if exposure else None,
        "net_change_rate": 100 * (sums["opened"] - sums["closed"]) / exposure if exposure else None,
        "closed": sums["closed"],
        "expected": sums["expected"],
        "exposure": exposure,
    }


def group_of(rank: int) -> str:
    return "top5" if rank <= TOP_N else "rest"


def band_of(rank: int) -> str:
    low, high = next(b for b in RANK_BANDS if b[0] <= rank <= b[1])
    return f"{low}~{high}위"


def district_sums(records: list[dict], method: str, grouping) -> dict[str, dict[str, dict]]:
    """자치구·구간별 건수 합계입니다. 재표본은 자치구 단위로 합니다."""
    sums: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(empty))
    for record in records:
        for rank, code in enumerate(record["orders"][method], 1):
            outcome = record["outcomes"].get(code)
            if outcome is not None:
                add(sums[record["district"]][grouping(rank)], outcome)
    return sums


def total(sums: dict[str, dict[str, dict]], keys, group: str) -> dict:
    out = empty()
    for key in keys:
        if group in sums[key]:
            add(out, sums[key][group])
    return out


def bootstrap(stat, keys: list[str], *, rounds: int, seed: int) -> tuple[float, float] | None:
    """같은 자치구 상권은 서로 닮았으므로 자치구 단위로 재표본해 95% 구간을 냅니다."""
    if len(keys) < 2:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(rounds):
        value = stat(rng.choices(keys, k=len(keys)))
        if value is not None:
            values.append(value)
    if len(values) < rounds * 0.9:
        return None
    values.sort()
    return values[int(0.025 * len(values))], values[int(0.975 * len(values)) - 1]


def top_vs_rest(records: list[dict], method: str, *, rounds: int, seed: int) -> dict:
    sums = district_sums(records, method, group_of)
    keys = sorted(sums)

    def relative(selected):
        top, rest = ratio(total(sums, selected, "top5")), ratio(total(sums, selected, "rest"))
        return top / rest if top is not None and rest else None

    def gap(selected):
        top = rates(total(sums, selected, "top5"))["net_change_rate"]
        rest = rates(total(sums, selected, "rest"))["net_change_rate"]
        return top - rest if top is not None and rest is not None else None

    return {
        "top5": rates(total(sums, keys, "top5")),
        "rest": rates(total(sums, keys, "rest")),
        "scr_ratio_top5_over_rest": relative(keys),
        "scr_ratio_ci95": bootstrap(relative, keys, rounds=rounds, seed=seed),
        "net_change_gap": gap(keys),
        "net_change_gap_ci95": bootstrap(gap, keys, rounds=rounds, seed=seed),
        "district_n": len(keys),
    }


def area_wins(records: list[dict], method: str) -> dict:
    """상권마다 추천 5개의 표준화 폐업비가 나머지보다 낮은지 셉니다."""
    wins = compared = 0
    for record in records:
        top, rest = empty(), empty()
        for rank, code in enumerate(record["orders"][method], 1):
            outcome = record["outcomes"].get(code)
            if outcome is not None:
                add(top if rank <= TOP_N else rest, outcome)
        a, b = ratio(top), ratio(rest)
        if a is None or b is None:
            continue
        compared += 1
        wins += a < b
    return {"compared_areas": compared, "top5_lower_share": wins / compared if compared else None}


def paired(records: list[dict], method: str, reference: str, *, rounds: int, seed: int) -> dict:
    """두 방식의 추천 5개 표준화 폐업비 비율(방식 / 기준)입니다. 자치구 표본을 함께 뽑습니다."""
    a = district_sums(records, method, group_of)
    b = district_sums(records, reference, group_of)
    keys = sorted(set(a) | set(b))

    def relative(selected):
        x, y = ratio(total(a, selected, "top5")), ratio(total(b, selected, "top5"))
        return x / y if x is not None and y else None

    return {
        "scr_ratio": relative(keys),
        "ci95": bootstrap(relative, keys, rounds=rounds, seed=seed),
    }


def bands(records: list[dict], method: str) -> list[dict]:
    sums = district_sums(records, method, band_of)
    keys = sorted(sums)
    out = []
    for low, high in RANK_BANDS:
        label = f"{low}~{high}위"
        n = sum(
            1
            for r in records
            for rank, code in enumerate(r["orders"][method], 1)
            if low <= rank <= high and code in r["outcomes"]
        )
        out.append({"ranks": label, "pairs": n, **rates(total(sums, keys, label))})
    return out


def measured_share(records: list[dict], method: str) -> float | None:
    picks = [(r, code) for r in records for code in r["orders"][method][:TOP_N]]
    return sum(code in r["outcomes"] for r, code in picks) / len(picks) if picks else None


def badge_rates(records: list[dict]) -> dict:
    groups: dict[str, dict] = defaultdict(empty)
    counts: Counter = Counter()
    for record in records:
        for code, outcome in record["outcomes"].items():
            badge = record["badges"].get(code)
            if badge is not None:
                add(groups[badge], outcome)
                counts[badge] += 1
    return {b: {"pairs": counts[b], **rates(groups[b])} for b in sorted(groups)}


def concentration(records: list[dict], method: str) -> dict:
    counts = Counter(code for r in records for code in r["orders"][method][:TOP_N])
    picks = sum(counts.values())
    return {
        "distinct_industries": len(counts),
        "top10_share": sum(n for _, n in counts.most_common(10)) / picks if picks else None,
        "most_common": counts.most_common(10),
    }


def evaluate(
    records: list[dict], methods: list[str], *, reference="service", rounds=2000, seed=20261026
) -> dict:
    out: dict = {"area_n": len(records), "methods": {}, "paired_vs_reference": {}}
    for method in methods:
        out["methods"][method] = {
            "top_vs_rest": top_vs_rest(records, method, rounds=rounds, seed=seed),
            "area_wins": area_wins(records, method),
            "rank_bands": bands(records, method),
            "top5_measured_share": measured_share(records, method),
            "concentration": concentration(records, method),
        }
        if method != reference:
            out["paired_vs_reference"][method] = paired(
                records, method, reference, rounds=rounds, seed=seed
            )
    out["badges"] = badge_rates(records)
    return out

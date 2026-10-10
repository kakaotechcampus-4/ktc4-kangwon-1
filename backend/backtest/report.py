import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from backtest.mock import MOCK_MODEL

LIMITATIONS = [
    '기존 가게와 새 가게가 섞인 폐업률이다. "T에 새로 열었다면 버텼을까"의 근사치다.',
    "인과가 아니라 상관이다. 창업자는 자리를 스스로 고른다.",
    "상권 입력은 반경 기준이 아니라 상권 점포 수로 대체했다.",
    "같은 원천(개폐업 에이전트 입력과 같은 API)이다. "
    "시점을 나눴고 관성 기준선으로 이 효과를 걸러야 한다.",
    "2단계는 같은 상가를 반복 실행하지 않아 모델 응답의 흔들림을 재지 않는다.",
    "모델의 학습 자료가 관찰 기간(2024~2026년)을 포함할 수 있어, 입력에서 T 이후 자료를 "
    "가려도 모델이 아는 사후 지식이 판단에 섞일 수 있다.",
    "채점 업종은 T 시점에 점포가 5개 이상 있던 업종이다. "
    "그 뒤에 줄거나 사라진 업종도 채점에 넣는다.",
    "T 시점에 점포가 없거나 적은 업종은 생존율을 잴 수 없어 '관찰 불가'로 따로 센다. "
    "상권에 아직 없는 업종을 추천하거나 비추천하면 그 판단은 채점되지 않는다.",
]

STOPPED = {
    "call_limit": "호출 상한",
    "agent_error": "에이전트 오류",
    "repeated_error": "같은 오류 반복",
    "incomplete": "중간에 끊김",
}

SIGNAL_NAMES = {
    "lifecycle": "개폐업 에이전트",
    "seoul_average": "기준선① 서울 업종 평균",
    "popularity": "기준선② 기존 점포 많은 순",
    "persistence": "기준선③ 관성",
}

RATIO_ROWS = [
    ("recommended_correct_vs_seoul", "추천 업종이 서울 평균보다 오래 버틴 비율"),
    ("recommended_correct_vs_area", "추천 업종이 상권 평균보다 오래 버틴 비율"),
    ("not_recommended_correct_vs_seoul", "비추천 업종이 서울 평균보다 덜 버틴 비율"),
    ("not_recommended_correct_vs_area", "비추천 업종이 상권 평균보다 덜 버틴 비율"),
]
BASE_KEYS = {
    "recommended_correct_vs_seoul": ("seoul_longer", False),
    "recommended_correct_vs_area": ("area_longer", False),
    "not_recommended_correct_vs_seoul": ("seoul_longer", True),
    "not_recommended_correct_vs_area": ("area_longer", True),
}


BASELINE_KEYS = ("seoul_average", "popularity", "persistence")
MIN_N = 10
TOO_FEW = "표본이 너무 적어 판단할 수 없다"


def span(low: float, high: float) -> str:
    return f"{low:.3f} ~ {high:.3f}"


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def stage1_section(stage1: dict) -> list[str]:
    errors = stage1.get("errors") or {}
    error_text = ", ".join(f"{name} {count}건" for name, count in errors.items()) or "없음"
    signals = stage1.get("signals") or {}
    versus = stage1.get("lifecycle_vs") or {}
    coverage = stage1.get("coverage_mean")
    compared = (
        ""
        if coverage is None
        else "네 점수가 모두 값을 가진 업종만 비교했다"
        f"(개폐업 점수가 채점 가능 업종의 평균 {coverage:.0%}를 덮음). "
    )
    lines = [
        "## 1단계 — 서울 전체 상권, 모델 없이",
        "",
        f"채점한 상권·시점 짝 {stage1.get('pairs', 0)}개, 상권 {stage1.get('areas', 0)}곳. "
        f"구간은 상권을 다시 뽑아 냈다. {compared}오류: {error_text}.",
        "",
        "| 점수 | 평균 일치율 | 95% 구간 |",
        "| --- | --- | --- |",
    ]
    for key, name in SIGNAL_NAMES.items():
        signal = signals.get(key)
        if signal:
            lines.append(
                f"| {name} | {signal['mean']:.3f} | {span(signal['low'], signal['high'])} |"
            )
    lines += ["", "일치율 0.5는 동전 던지기와 같다.", ""]
    lines += ["| 비교 | 차이 평균 | 95% 구간 | 결과 |", "| --- | --- | --- | --- |"]
    unbeaten = []
    for key in BASELINE_KEYS:
        value = versus.get(key)
        name = SIGNAL_NAMES[key]
        if not value:
            unbeaten.append(f"{name}(비교 없음)")
            lines.append(f"| 개폐업 − {name} | - | - | 비교 없음 |")
            continue
        low, high = round(value["low"], 3), round(value["high"], 3)
        if low > 0:
            result = "이김"
        elif high < 0:
            result = "짐"
        else:
            result = "구분 안 됨"
        if result != "이김":
            unbeaten.append(f"{name}({result})")
        lines.append(
            f"| 개폐업 − {name} | {value['mean']:+.3f} "
            f"| {span(value['low'], value['high'])} | {result} |"
        )
    lines.append("")
    if unbeaten:
        lines.append(f"개폐업 점수는 {', '.join(unbeaten)}을(를) 이기지 못했다.")
    else:
        lines.append("개폐업 점수는 기준선 셋을 모두 이겼다. 정보가 있다.")
    return [*lines, ""]


def ratio_reading(low: float, high: float, n: int | None, base: float | None = None) -> str:
    low, high = round(low * 100, 1), round(high * 100, 1)
    if (n is not None and n < MIN_N) or low == high:
        return TOO_FEW
    if base is None:
        if low > 50:
            return "50%보다 높다"
        if high < 50:
            return "50%보다 낮다"
        return "동전 던지기(50%)와 구분할 수 없다"
    reference = round(base * 100, 1)
    if low > reference:
        return "기준 비율보다 높다"
    if high < reference:
        return "기준 비율보다 낮다"
    return "아무 업종이나 고른 기준 비율과 구분할 수 없다"


def base_rate(rates: dict | None, key: str) -> float | None:
    name, flip = BASE_KEYS[key]
    value = (rates or {}).get(name)
    if value is None:
        return None
    return 1 - value if flip else value


def gap_reading(low: float, high: float, n: int | None) -> str:
    low, high = round(low * 100, 1), round(high * 100, 1)
    if (n is not None and n < MIN_N) or low == high:
        return TOO_FEW
    if low > 0:
        return "추천 업종이 더 오래 버텼다"
    if high < 0:
        return "비추천 업종이 더 오래 버텼다"
    return "추천과 비추천의 차이가 있다고 말할 수 없다"


def verdict_text(item: dict) -> str:
    verdict = item["verdict"]
    if verdict["status"] == "absent":
        return f"관찰 불가(T 시점 점포 {verdict['base_stores']:.0f}개)"
    if verdict["status"] == "pending":
        if "base_stores" in verdict:
            return "판단 보류(이후 자료 없음)"
        return f"판단 보류(점포 {verdict['mean_stores']:.1f}개)"
    if verdict["status"] != "scored":
        return "채점 불가"
    parts = []
    for ref, name in (("seoul", "서울"), ("area", "상권")):
        if verdict.get(ref) is None or verdict.get(f"correct_vs_{ref}") is None:
            continue
        gap = f"{(verdict['survival'] - verdict[ref]) * 100:+.1f}%p"
        side = "오래 버팀" if verdict["survival"] > verdict[ref] else "덜 버팀"
        mark = "맞음" if verdict[f"correct_vs_{ref}"] else "틀림"
        parts.append(f"{mark} ({name} 평균보다 {side} {gap})")
    return " / ".join(parts) or "채점 불가"


def status_text(record: dict) -> str:
    status = str(record.get("status"))
    return {
        "ok": "성공",
        "area_mismatch": "상권 불일치",
        "waiting": "대기",
        "call_limit": "호출 상한 도달",
        "error": f"오류: {record.get('error', '')}",
    }.get(status, status)


def kind_table(records: list[dict]) -> list[str]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for record in records:
        row = counts[record["area"]["kind"]]
        row[0] += 1
        if record.get("status") != "ok":
            continue
        row[1] += 1
        for item in record["items"]:
            verdict = item["verdict"]
            if (
                item["kind"] == "recommended"
                and verdict["status"] == "scored"
                and verdict.get("correct_vs_seoul") is not None
            ):
                row[2] += 1
                row[3] += bool(verdict["correct_vs_seoul"])
    lines = [
        "| 종류 | 전체 표본 | 성공 | 채점된 추천 | 서울 평균보다 오래 버틴 추천 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for kind, (samples, ok, scored, longer) in counts.items():
        ratio = f"{longer}개 ({percent(longer / scored)})" if scored else "-"
        lines.append(f"| {kind} | {samples} | {ok} | {scored} | {ratio} |")
    return lines


def status_counts(counts: dict) -> str:
    return ", ".join(f"{status} {n}" for status, n in counts.items())


def area_table(records: list[dict]) -> list[str]:
    lines = [
        "| 상권 | 종류 | 상태 | 추천(판정) | 비추천(판정) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        area = record["area"]
        cells: dict[str, list[str]] = {"recommended": [], "not_recommended": []}
        if record.get("status") == "ok":
            for item in record["items"]:
                cells[item["kind"]].append(f"{item['name']} {verdict_text(item)}")
        rec = "; ".join(cells["recommended"]) or "-"
        non = "; ".join(cells["not_recommended"]) or "-"
        lines.append(f"| {area['name']} | {area['kind']} | {status_text(record)} | {rec} | {non} |")
    return lines


def sample_counts(records: list[dict]) -> dict[str, int]:
    counts = {key: 0 for key, _ in RATIO_ROWS}
    counts["recommended_minus_not"] = 0
    for record in records:
        if record.get("status") != "ok":
            continue
        scored = {"recommended": 0, "not_recommended": 0}
        for item in record["items"]:
            verdict = item["verdict"]
            if verdict["status"] != "scored":
                continue
            scored[item["kind"]] += 1
            for ref in ("seoul", "area"):
                if verdict.get(f"correct_vs_{ref}") is not None:
                    counts[f"{item['kind']}_correct_vs_{ref}"] += 1
        if scored["recommended"] and scored["not_recommended"]:
            counts["recommended_minus_not"] += 1
    return counts


def stage2_section(stage2: dict | None, records: list[dict] | None, mock: bool) -> list[str]:
    if stage2 is None:
        return ["## 2단계 — 상가", "", "2단계 결과 없음."]
    title = f"## 2단계 — 상가 {stage2.get('samples', 0)}곳" + (" (대역 모델)" if mock else "")
    lines = [title, ""]
    if mock:
        lines += [
            "대역 모델 결과다. 추천 품질이 아니라 실행 경로 점검용이므로 "
            "수치를 성능으로 읽으면 안 된다.",
            "",
        ]
    mismatch = "-" if records is None else sum(r.get("status") == "area_mismatch" for r in records)
    counts = None if records is None else sample_counts(records)
    types = ", ".join(f"{name} {count}건" for name, count in stage2.get("error_types", {}).items())
    errors = f"{stage2.get('errors', 0)}건" + (f" ({types})" if types else "")
    status = ""
    if stage2.get("agent_status"):
        agents = ", ".join(
            f"{agent}({status_counts(counts)})" for agent, counts in stage2["agent_status"].items()
        )
        status += f" 에이전트 상태: {agents}."
    if stage2.get("decision_status"):
        status += f" 판정 상태: {status_counts(stage2['decision_status'])}."
    stopped = stage2.get("stopped")
    reason = STOPPED.get(stopped, stopped) if stopped else "없음"
    unit = (
        " 비율 구간은 상가를 다시 뽑아 냈다."
        if stage2.get("interval_unit") == "site"
        else " 비율 구간은 항목을 다시 뽑아 냈다(같은 상가 항목을 따로 세어 실제보다 좁게 나온다)."
    )
    lines += [
        f"성공 {stage2.get('ok', 0)}곳, 상권 불일치 제외 {mismatch}곳, 오류 {errors}, "
        f"중단 사유 {reason}, 모델 호출 {stage2.get('calls')}회." + status + unit,
        "",
        "| 항목 | 값 | 표본 수 | 95% 구간 | 기준 비율 | 해석 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rates = stage2.get("base_rates")
    for key, name in RATIO_ROWS:
        n = None if counts is None else counts[key]
        shown = "-" if n is None else str(n)
        base = base_rate(rates, key)
        reference = percent(0.5 if base is None else base)
        value = stage2.get(key)
        if value is None:
            lines.append(f"| {name} | 채점된 항목 없음 | {shown} | - | {reference} | - |")
            continue
        mean, low, high = value
        lines.append(
            f"| {name} | {percent(mean)} | {shown} | {percent(low)} ~ {percent(high)} "
            f"| {reference} | {ratio_reading(low, high, n, base)} |"
        )
    gap = stage2.get("recommended_minus_not")
    gap_name = "추천 − 비추천 평균 생존율"
    n = None if counts is None else counts["recommended_minus_not"]
    shown = "-" if n is None else str(n)
    if gap is None:
        lines.append(f"| {gap_name} | 채점된 항목 없음 | {shown} | - | - | - |")
    else:
        mean, low, high = gap
        lines.append(
            f"| {gap_name} | {mean * 100:+.1f}%p | {shown} "
            f"| {low * 100:+.1f} ~ {high * 100:+.1f}%p | - | {gap_reading(low, high, n)} |"
        )
    absent = ""
    if "absent_ratio" in stage2:
        by_kind = stage2.get("absent_ratio_by_kind") or {}
        absent = (
            f" 관찰 불가 비율 {percent(stage2.get('absent_ratio'))} "
            f"(추천 {percent(by_kind.get('recommended'))}, "
            f"비추천 {percent(by_kind.get('not_recommended'))})."
        )
    lines += [
        "",
        f"판단 보류 비율 {percent(stage2.get('pending_ratio'))}, "
        f"채점 불가 비율 {percent(stage2.get('unscorable_ratio'))}." + absent,
    ]
    if records is None:
        lines += ["", "상가별 기록 없음"]
    else:
        lines += ["", "### 상권 종류별", "", *kind_table(records)]
        lines += ["", "### 상가별", "", *area_table(records)]
    return lines


def build_report(
    stage1: dict, stage2: dict | None, records: list[dict] | None, *, mock: bool
) -> str:
    lines = [
        "# 백테스트 결과 — 과거 시점 추천이 실제로 맞았나",
        "",
        f"작성일: {stage1.get('created', '-')}",
        "",
        "## 먼저 읽을 한계",
        "",
        *[f"- {line}" for line in LIMITATIONS],
        "",
        *stage1_section(stage1),
        *stage2_section(stage2, records, mock),
    ]
    return "\n".join(lines) + "\n"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stage2", type=Path)
    args = parser.parse_args(argv)
    stage1 = load(args.out / "stage1_summary.json")
    stage2, records, mock = None, None, False
    folders = [args.stage2] if args.stage2 else [args.out / "real", args.out / "mock"]
    for folder in folders:
        if (folder / "stage2_summary.json").exists():
            stage2 = load(folder / "stage2_summary.json")
            records_path = folder / "stage2_records.json"
            records = load(records_path) if records_path.exists() else None
            mock = folder.name == "mock" or stage2.get("model") == MOCK_MODEL
            break
    report = build_report(stage1, stage2, records, mock=mock)
    (args.stage2 or args.out).joinpath("백테스트_보고서.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

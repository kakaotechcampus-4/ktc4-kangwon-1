"""심사위원 시험 결과를 채점하고 요약 보고를 씁니다."""

import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from examiner_eval.cases import Case, Seed
from examiner_eval.runner import CaseResult, submit_rejections

SCOPE_KINDS = ("missing_evidence", "scope_mismatch", "factual_error")
OTHER_KINDS = ("action_condition", "duplicate_score")
REAL_CAP = 4
REPORT_FILES = ("요약.md", "요약.csv", "사례별.csv")
NO_RECORD = "기록 없음"
SEED_KINDS = ("E1", "E2", "E3")


@dataclass
class CaseScore:
    case_id: str
    variant: str
    repeat: int
    split: str
    source: str
    found: dict[str, bool]
    exact: dict[str, bool]
    false_positives: int
    other_issues: int
    first_rejected: bool
    failed: bool
    denominator: int = 0
    error_code: str | None = None
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: int = 0
    packet_chars: int = 0
    omitted_fact_ids: int = 0
    model: str | None = field(default=None, compare=False)


def _candidates(issue: dict, candidate_facts: dict[str, set[str]]) -> set[str]:
    if issue.get("industry_code"):
        return {issue["industry_code"]}
    facts = set(issue.get("fact_ids") or [])
    return {code for code, ids in candidate_facts.items() if ids & facts}


def _matches(seed: Seed, issue: dict, candidate_facts: dict[str, set[str]]) -> bool:
    return issue.get("kind") == seed.expected_kind and seed.industry_code in _candidates(
        issue, candidate_facts
    )


def _is_exact(seed: Seed, matched: list[dict]) -> bool:
    for issue in matched:
        facts = set(issue.get("fact_ids") or [])
        if seed.kind == "E1" and facts & set(seed.support_fact_ids):
            return True
        if seed.kind != "E1" and seed.wrong_fact_id in facts:
            return True
    return False


def _unsupported_candidates(draft: dict) -> list[str]:
    codes = []
    for candidate in draft.get("top5") or []:
        for name in ("reasons_segments", "risks_segments"):
            kinds = [segment.get("type") for segment in candidate.get(name) or []]
            if "text" in kinds and "fact" not in kinds:
                codes.append(candidate["industry_code"])
                break
    return codes


def score_case(case: Case, result: CaseResult, candidate_facts: dict[str, set[str]]) -> CaseScore:
    issues = result.issues
    found: dict[str, bool] = {}
    exact: dict[str, bool] = {}
    false_positives = 0
    denominator = 0
    scope_issues = [i for i in issues if i.get("kind") in SCOPE_KINDS]
    if case.source == "seeded":
        denominator = len(case.seeds)
        for seed in case.seeds:
            matched = [i for i in issues if _matches(seed, i, candidate_facts)]
            found[seed.kind] = bool(matched)
            exact[seed.kind] = _is_exact(seed, matched)
        false_positives = sum(
            1
            for issue in scope_issues
            if not any(_matches(seed, issue, candidate_facts) for seed in case.seeds)
        )
    elif case.source == "clean":
        false_positives = len(scope_issues)
    else:
        eligible = _unsupported_candidates(case.draft)
        denominator = min(REAL_CAP, len(eligible))
        implicit = [
            Seed("E1", code, "reasons_segments", "missing_evidence", (), None) for code in eligible
        ]
        for seed in implicit:
            found[f"E1:{seed.industry_code}"] = any(
                _matches(seed, issue, candidate_facts) for issue in issues
            )
    return CaseScore(
        case_id=case.case_id,
        variant=result.variant,
        repeat=result.repeat,
        split=case.split,
        source=case.source,
        found=found,
        exact=exact,
        false_positives=false_positives,
        other_issues=sum(1 for i in issues if i.get("kind") in OTHER_KINDS),
        first_rejected=(result.end_event or {}).get("rejections", 0) >= 1,
        failed=result.status == "failed",
        denominator=denominator,
        error_code=result.error_code if result.status == "failed" else None,
        calls=result.calls,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        elapsed_ms=result.elapsed_ms,
        packet_chars=result.packet_chars,
        omitted_fact_ids=result.omitted_fact_ids,
        model=result.model,
    )


def _kind_value(kind: str, attr: str) -> Callable[[CaseScore], float | None]:
    def value(score: CaseScore) -> float | None:
        if score.source != "seeded" or kind not in getattr(score, attr):
            return None
        return float(getattr(score, attr)[kind])

    return value


def _real_recall(score: CaseScore) -> float | None:
    if score.source != "real" or score.denominator == 0:
        return None
    return min(sum(score.found.values()), score.denominator) / score.denominator


def _only(source: str, attr: str) -> Callable[[CaseScore], float | None]:
    return lambda score: float(getattr(score, attr)) if score.source == source else None


def _done(source: str, attr: str) -> Callable[[CaseScore], float | None]:
    def value(score: CaseScore) -> float | None:
        if score.source != source or score.failed:
            return None
        return float(getattr(score, attr))

    return value


def _all(attr: str) -> Callable[[CaseScore], float | None]:
    return lambda score: float(getattr(score, attr))


METRICS: dict[str, Callable[[CaseScore], float | None]] = {
    **{f"{k}_found": _kind_value(k, "found") for k in SEED_KINDS},
    **{f"{k}_exact": _kind_value(k, "exact") for k in SEED_KINDS},
    "real_recall": _real_recall,
    "clean_false_positives": _only("clean", "false_positives"),
    "clean_false_positives_done": _done("clean", "false_positives"),
    "seeded_false_positives": _only("seeded", "false_positives"),
    "other_issues": _all("other_issues"),
    "first_rejected": _all("first_rejected"),
    "failed": _all("failed"),
    "calls": _all("calls"),
    "input_tokens": _all("input_tokens"),
    "output_tokens": _all("output_tokens"),
    "elapsed_ms": _all("elapsed_ms"),
    "packet_chars": _all("packet_chars"),
    "omitted_fact_ids": _all("omitted_fact_ids"),
}
RATES = {
    "E1_found",
    "E2_found",
    "E3_found",
    "E1_exact",
    "E2_exact",
    "E3_exact",
    "real_recall",
    "first_rejected",
    "failed",
}


def summarize(scores: list[CaseScore]) -> list[dict]:
    groups: dict[tuple[str, str], list[CaseScore]] = defaultdict(list)
    for score in scores:
        groups[(score.variant, score.split)].append(score)
    rows = []
    for (variant, split), members in sorted(groups.items()):
        for metric, extract in METRICS.items():
            values = [(s.repeat, s.case_id, extract(s)) for s in members]
            values = [v for v in values if v[2] is not None]
            if not values:
                continue
            by_repeat: dict[int, list[float]] = defaultdict(list)
            for repeat, _, value in values:
                by_repeat[repeat].append(value)
            means = [sum(v) / len(v) for v in by_repeat.values()]
            rows.append(
                {
                    "variant": variant,
                    "split": split,
                    "metric": metric,
                    "mean": sum(v[2] for v in values) / len(values),
                    "min": min(means),
                    "max": max(means),
                    "n": len({v[1] for v in values}),
                }
            )
    return rows


def _recording_name(case_id: str, variant: str, repeat: int) -> str:
    return re.sub(r"[^0-9A-Za-z_-]", "_", case_id) + f"__{variant}__{repeat}.json"


def rejection_reasons(run_dir: Path, results: list[CaseResult], splits: dict[str, str]):
    calls = Path(run_dir) / "calls"
    counters: dict[tuple[str, str], Counter | None] = {}
    for result in results:
        key = (result.variant, splits[result.case_id])
        counters.setdefault(key, None)
        if result.rejected_reasons is not None:
            counter = counters[key] if counters[key] is not None else Counter()
            counters[key] = counter
            counter.update(result.rejected_reasons)
            continue
        path = calls / _recording_name(result.case_id, result.variant, result.repeat)
        if not path.exists():
            continue
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        counter = counters[key] if counters[key] is not None else Counter()
        counters[key] = counter
        seen = set()
        for entry in entries if isinstance(entries, list) else []:
            for message in entry.get("messages") or []:
                if not isinstance(message, dict) or message.get("role") != "tool":
                    continue
                mark = (message.get("tool_call_id"), message.get("content"))
                if mark in seen:
                    continue
                seen.add(mark)
                counter.update(submit_rejections(message.get("content")))
    return counters


def _format(metric: str, mean: float, low: float, high: float) -> str:
    if metric in RATES:
        return f"{mean * 100:.1f}% ({low * 100:.1f}%–{high * 100:.1f}%)"
    digits = 0 if metric in {"elapsed_ms", "input_tokens", "output_tokens", "packet_chars"} else 2
    return f"{mean:.{digits}f} ({low:.{digits}f}–{high:.{digits}f})"


EXPLAIN = {
    "E1_found": "E1 찾은 비율: 근거를 뺀 문장을 같은 후보·같은 종류로 지적한 비율",
    "E2_found": "E2 찾은 비율: 다른 자료를 붙인 문장을 같은 후보·같은 종류로 지적한 비율",
    "E3_found": "E3 찾은 비율: 위험 문장에 엉뚱한 자료를 붙인 곳을 같은 후보·같은 종류로 지적",
    "E1_exact": "E1 정확히 찾은 비율: 지적 근거에 원래 뒷받침하던 자료가 들어 있는 비율",
    "E2_exact": "E2 정확히 찾은 비율: 지적 근거에 잘못 붙인 자료가 들어 있는 비율",
    "E3_exact": "E3 정확히 찾은 비율: 지적 근거에 잘못 붙인 자료가 들어 있는 비율",
    "real_recall": "실제 초안 찾은 비율: 근거 없는 문장이 있는 후보 중 지적된 비율(최대 4개 기준)",
    "clean_false_positives": "깨끗한 초안 오지적: 오류 없는 초안에서 나온 근거·범위·사실 지적 평균",
    "clean_false_positives_done": "깨끗한 초안 오지적(완료만): 실패한 사례를 빼고 낸 평균",
    "seeded_false_positives": "오류 심은 초안 오지적: 심은 오류가 아닌 곳을 지적한 평균 개수",
    "other_issues": "기타 지적: 행동 조건·점수 중복 지적의 사례당 평균 개수(오지적으로 세지 않음)",
    "first_rejected": "첫 제출 거절 비율: 첫 제출이 형식 검사에서 거절된 사례 비율",
    "failed": "실패 비율: 심사가 끝나지 못한 사례 비율(찾은 것으로 세지 않음)",
    "calls": "호출 수: 사례당 평균 모델 호출 횟수",
    "input_tokens": "입력 토큰: 사례당 평균",
    "output_tokens": "출력 토큰: 사례당 평균",
    "elapsed_ms": "걸린 시간: 사례당 평균 밀리초",
    "packet_chars": "패킷 글자 수: 심사위원에게 준 자료의 평균 글자 수",
    "omitted_fact_ids": "빠진 근거 수: 패킷에서 생략된 근거 ID의 평균 개수",
}


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def _markdown(results, scores, summary, rejections) -> str:
    variants = sorted({s.variant for s in scores})
    splits = sorted({s.split for s in scores})
    repeats = sorted({s.repeat for s in scores})
    models = sorted({r.model for r in results if r.model})
    lines = [
        "# 심사위원 시험 요약",
        "",
        f"- 날짜: {date.today().isoformat()}",
        f"- 버전: {', '.join(variants)}",
        f"- 구분(split): {', '.join(splits)}",
        f"- 회차: {', '.join(map(str, repeats))}",
        f"- 모델: {', '.join(models) or '없음'}",
        "- 표기: 평균 (회차별 평균의 최소–최대). 실제 초안은 오지적을 세지 않습니다. "
        "어느 문장이 괜찮은지 알 수 없기 때문입니다.",
        "",
    ]
    index = {(r["variant"], r["split"], r["metric"]): r for r in summary}
    for split in splits:
        lines += [f"## {split}", ""]
        rows = []
        for metric in METRICS:
            cells = []
            for variant in variants:
                row = index.get((variant, split, metric))
                cells.append(
                    _format(metric, row["mean"], row["min"], row["max"]) + f" n={row['n']}"
                    if row
                    else "-"
                )
            if any(c != "-" for c in cells):
                rows.append([metric, *cells])
        lines += _table(["항목", *variants], rows) + [""]
    keys = [
        (v, s)
        for s in splits
        for v in variants
        if any(x.variant == v and x.split == s for x in scores)
    ]
    lines += ["## 실패 사유", ""]
    codes = sorted({s.error_code or "(없음)" for s in scores if s.failed})
    if codes:
        rows = [
            [code]
            + [
                str(
                    sum(
                        1
                        for s in scores
                        if s.failed
                        and (s.error_code or "(없음)") == code
                        and (s.variant, s.split) == key
                    )
                )
                for key in keys
            ]
            for code in codes
        ]
        lines += _table(["사유", *[f"{v}/{s}" for v, s in keys]], rows) + [""]
    else:
        lines += ["실패한 사례가 없습니다.", ""]
    lines += ["## 제출 거절 사유", ""]
    known = {k: c for k, c in (rejections or {}).items() if c is not None}
    if not known:
        lines += [NO_RECORD, ""]
    else:
        reasons = sorted({reason for c in known.values() for reason in c})
        if reasons:
            rows = [
                [reason.replace("|", "/")]
                + [str(known[key][reason]) if key in known else NO_RECORD for key in keys]
                for reason in reasons
            ]
            lines += _table(["사유", *[f"{v}/{s}" for v, s in keys]], rows) + [""]
        else:
            lines += ["거절된 제출이 없습니다.", ""]
        missing = [f"{v}/{s}" for v, s in keys if (v, s) not in known]
        if missing:
            lines += [f"{NO_RECORD}: {', '.join(missing)}", ""]
    lines += ["## 읽는 법", ""]
    lines += [f"- {text}" for text in EXPLAIN.values()]
    lines += ["- n: 그 항목을 센 사례 수(회차는 합치지 않음)"]
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_report(
    results: list[CaseResult],
    scores: list[CaseScore],
    out_dir: Path,
    rejections: dict | None = None,
) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = [name for name in REPORT_FILES if (out_dir / name).exists()]
    if existing:
        raise FileExistsError(", ".join(existing))
    summary = summarize(scores)
    columns = ["variant", "split", "metric", "mean", "min", "max", "n"]
    _write_csv(out_dir / "요약.csv", columns, [[r[c] for c in columns] for r in summary])
    case_columns = [
        "case_id",
        "variant",
        "repeat",
        "split",
        "source",
        *[f"{k}_{a}" for a in ("found", "exact") for k in SEED_KINDS],
        "real_found",
        "denominator",
        "false_positives",
        "other_issues",
        "first_rejected",
        "failed",
        "error_code",
        "calls",
        "input_tokens",
        "output_tokens",
        "elapsed_ms",
        "packet_chars",
        "omitted_fact_ids",
    ]
    rows = []
    for s in scores:
        flags = [
            "" if k not in getattr(s, a) else int(getattr(s, a)[k])
            for a in ("found", "exact")
            for k in SEED_KINDS
        ]
        real = sum(s.found.values()) if s.source == "real" else ""
        rows.append(
            [s.case_id, s.variant, s.repeat, s.split, s.source, *flags, real, s.denominator]
            + [s.false_positives, s.other_issues, int(s.first_rejected), int(s.failed)]
            + [s.error_code or "", s.calls, s.input_tokens, s.output_tokens, s.elapsed_ms]
            + [s.packet_chars, s.omitted_fact_ids]
        )
    _write_csv(out_dir / "사례별.csv", case_columns, rows)
    with (out_dir / "요약.md").open("x", encoding="utf-8") as handle:
        handle.write(_markdown(results, scores, summary, rejections))

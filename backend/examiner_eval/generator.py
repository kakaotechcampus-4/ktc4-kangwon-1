"""근거가 붙은 시험용 초안을 만들고 알려진 오류를 심습니다."""

import copy
import random

from examiner_eval.cases import Case, Seed, split_requests
from examiner_eval.store import RequestContext

PHRASES: dict[str, tuple[str, ...]] = {
    "store_count": (
        "반경 안의 점포 수는 {fact}로 확인되어 상권의 규모를 가늠할 수 있습니다.",
        "주변에 자리한 점포 수는 {fact}로 집계되어 이미 형성된 상권으로 볼 수 있습니다.",
        "이 업종의 점포 수는 {fact}로 조사되어 수요가 이어지는 지역으로 해석됩니다.",
    ),
    "pattern_fit_index": (
        "유동인구가 움직이는 양상이 이 업종과 맞는 정도는 {fact}로 나타났습니다.",
        "시간대별 유동인구 흐름이 업종 특성과 어울리는 정도는 {fact}로 계산되었습니다.",
        "지나는 사람들의 움직임이 업종과 들어맞는 정도를 보면 {fact}로 확인됩니다.",
    ),
    "recent_year_close_rate": (
        "최근 한 해의 폐업률은 {fact}로 집계되어 운영 부담을 함께 살펴야 합니다.",
        "관측 기간 가운데 최근 한 해의 폐업률은 {fact}로 나타나 주의가 필요합니다.",
        "최근 한 해 기준으로 이 업종의 폐업률은 {fact}로 확인되어 위험 요인으로 볼 수 있습니다.",
    ),
    "oldest_year_close_rate": (
        "관측 기간 가운데 가장 이른 해의 폐업률은 {fact}로 기록되어 있습니다.",
        "가장 이른 해 기준으로 이 업종의 폐업률은 {fact}로 집계되었습니다.",
        "가장 이른 해의 폐업률은 {fact}로 나타나 과거 흐름을 보여 줍니다.",
    ),
}

SOURCES = {
    "store_count": "commercial_area",
    "pattern_fit_index": "floating_population",
    "recent_year_close_rate": "business_lifecycle",
    "oldest_year_close_rate": "business_lifecycle",
}

PLAN = (
    ("reasons_segments", "store_count"),
    ("reasons_segments", "pattern_fit_index"),
    ("risks_segments", "recent_year_close_rate"),
)


def _fact_id(ctx, code, metric):
    return ctx.facts.get((code, SOURCES[metric], metric))


def _sentence(phrase, fact_id):
    before, after = phrase.split("{fact}")
    segments = []
    if before:
        segments.append({"type": "text", "text": before})
    segments.append({"type": "fact", "fact_id": fact_id, "format": "text"})
    if after:
        segments.append({"type": "text", "text": after})
    return segments


def _refresh_fact_ids(candidate):
    ids = []
    for field in ("reasons_segments", "risks_segments", "confirmation_conditions_segments"):
        for seg in candidate[field]:
            if seg["type"] == "fact" and seg["fact_id"] not in ids:
                ids.append(seg["fact_id"])
    candidate["fact_ids"] = ids


def _build(ctx, rng, suffix):
    draft = copy.deepcopy(ctx.stored_draft)
    draft["report_id"] = f"{ctx.stored_draft['report_id']}:{suffix}"
    for candidate in draft["top5"]:
        code = candidate["industry_code"]
        candidate["reasons_segments"] = []
        candidate["risks_segments"] = []
        candidate["confirmation_conditions_segments"] = []
        for field, metric in PLAN:
            fact_id = _fact_id(ctx, code, metric)
            if fact_id is None:
                continue
            phrase = rng.choice(PHRASES[metric])
            candidate[field].extend(_sentence(phrase, fact_id))
        _refresh_fact_ids(candidate)
    return draft


def clean_draft(ctx: RequestContext, rng: random.Random) -> dict:
    return _build(ctx, rng, "clean")


def _slot_positions(candidate, field, fact_id):
    return [
        index
        for index, seg in enumerate(candidate[field])
        if seg["type"] == "fact" and seg["fact_id"] == fact_id
    ]


def _e3_target(ctx, code):
    recent = _fact_id(ctx, code, "recent_year_close_rate")
    oldest = _fact_id(ctx, code, "oldest_year_close_rate")
    if recent and oldest:
        return recent, oldest
    return None


def _e2_target(ctx, code):
    original = _fact_id(ctx, code, "store_count")
    if original is None:
        return None
    for metric in ("pattern_fit_index", "recent_year_close_rate", "oldest_year_close_rate"):
        replacement = _fact_id(ctx, code, metric)
        if replacement is not None:
            return original, replacement
    return None


def _e1_target(candidate):
    options = []
    for field in ("reasons_segments", "risks_segments"):
        for seg in candidate[field]:
            if seg["type"] == "fact":
                options.append((field, seg["fact_id"]))
    return options or None


def seeded_draft(ctx: RequestContext, rng: random.Random) -> tuple[dict, tuple[Seed, ...]]:
    draft = _build(ctx, rng, "seeded")
    candidates = {c["industry_code"]: c for c in draft["top5"]}
    order = list(candidates)
    rng.shuffle(order)
    used = set()
    seeds = []

    def pick(eligible):
        for code in order:
            if code not in used and eligible(code):
                used.add(code)
                return code
        return None

    code = pick(lambda c: _e3_target(ctx, c) is not None)
    if code is not None:
        recent, oldest = _e3_target(ctx, code)
        for index in _slot_positions(candidates[code], "risks_segments", recent):
            candidates[code]["risks_segments"][index]["fact_id"] = oldest
        seeds.append(Seed("E3", code, "risks_segments", "scope_mismatch", (recent,), oldest))

    code = pick(
        lambda c: (
            _e2_target(ctx, c) is not None
            and _slot_positions(candidates[c], "reasons_segments", _e2_target(ctx, c)[0])
        )
    )
    if code is not None:
        original, replacement = _e2_target(ctx, code)
        for index in _slot_positions(candidates[code], "reasons_segments", original):
            candidates[code]["reasons_segments"][index]["fact_id"] = replacement
        seeds.append(
            Seed("E2", code, "reasons_segments", "scope_mismatch", (original,), replacement)
        )

    code = pick(lambda c: _e1_target(candidates[c]) is not None)
    if code is not None:
        field, fact_id = rng.choice(_e1_target(candidates[code]))
        candidates[code][field] = [
            seg
            for seg in candidates[code][field]
            if not (seg["type"] == "fact" and seg["fact_id"] == fact_id)
        ]
        seeds.append(Seed("E1", code, field, "missing_evidence", (fact_id,), None))

    for candidate in draft["top5"]:
        _refresh_fact_ids(candidate)
    return draft, tuple(seeds)


def _has_segments(stored_draft):
    for candidate in stored_draft.get("top5", []):
        for field in ("reasons_segments", "risks_segments", "confirmation_conditions_segments"):
            if candidate.get(field):
                return True
    return False


def build_cases(contexts: list[RequestContext], seed: int = 20261023) -> list[Case]:
    splits = split_requests([ctx.request_id for ctx in contexts], seed)
    cases = []
    for ctx in sorted(contexts, key=lambda c: c.request_id):
        rng = random.Random(f"{seed}:{ctx.request_id}")
        split = splits[ctx.request_id]
        cases.append(
            Case(
                f"{ctx.request_id}:clean", ctx.request_id, split, "clean", clean_draft(ctx, rng), ()
            )
        )
        draft, seeds = seeded_draft(ctx, rng)
        cases.append(
            Case(f"{ctx.request_id}:seeded", ctx.request_id, split, "seeded", draft, seeds)
        )
        if _has_segments(ctx.stored_draft):
            cases.append(
                Case(
                    f"{ctx.request_id}:real",
                    ctx.request_id,
                    split,
                    "real",
                    copy.deepcopy(ctx.stored_draft),
                    (),
                )
            )
    return cases

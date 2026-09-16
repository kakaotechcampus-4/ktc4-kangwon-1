"""서울시 생활밀접업종 100종을 소상공인 **소분류**를 거쳐 중분류로 붙인다.

중분류 이름끼리 비교하면 "제과점 → 인쇄 및 제품 제작업" 같은 게 나온다.
이름의 층위가 다르기 때문이다.
소분류(1,255종)에는 '슈퍼마켓', '네일숍', '노래방', '빵/도넛'처럼 서울시와 같은 층위의 이름이 있다.
그래서 **소분류에서 찾고, 중분류는 거기서 따라오게** 한다. 이러면 중분류를 사람이 고르지 않는다.

3단계로 좁힌다.

    1  정확  서울시 업종명 == 소분류 이름(또는 '/'로 나눈 조각)   예: 슈퍼마켓, 네일숍, 고시원
    2  부분  한쪽이 다른 쪽에 들어감                          예: 문구 ⊂ 문구/회화용품 소매업
    3  모델  위로 안 걸리면 모델이 **소분류 목록에서** 고른다      예: 제과점 → 빵/도넛

3단계도 고르는 건 소분류라, 중분류는 어느 경우든 원천이 정한 값이다.

사용:
    python examples/match_upjong_by_small.py
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.commercial_area.config import Settings, load_dotenv_if_present  # noqa: E402
from app.agents.commercial_area.upjong import load_middle_master  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "schema_compare"
OUT_PATH = OUT_DIR / "업종매칭_소분류근거.csv"
BATCH = 8

COLUMNS = [
    "(서울시)업종명",
    "(서울시)코드명",
    "top1 (공공데이터포털)업종명",
    "top1 (공공데이터포털)코드명",
    "top2 (공공데이터포털)업종명",
    "top2 (공공데이터포털)코드명",
    "top3 (공공데이터포털)업종명",
    "top3 (공공데이터포털)코드명",
    "판정방식",
    "근거 소분류",
]

TAIL = re.compile(r"(소매업|판매업|운영업|서비스업|전문점|판매|소매|업소|업|점)$")
SPACE = re.compile(r"[\s\-]")

SYSTEM = """당신은 한국 상권 업종 분류 전문가입니다.

소상공인시장진흥공단 상권업종 '소분류' 목록을 드립니다.
서울시 생활밀접업종 각각에 대해, 그 가게가 실제로 어느 소분류로 집계될지 고르세요.

규칙
- 반드시 주어진 소분류 코드만 쓰세요. 없는 코드를 지어내지 마세요.
- 글자가 겹치는지가 아니라 업태가 같은지로 판단하세요.
- 가장 그럴듯한 것부터 최대 3개. 마땅한 게 없으면 빈 배열로 두세요.

출력은 JSON만. 형식:
{"matches":[{"seoul_code":"CS100005","small_codes":["I21003","I21001"]}]}"""


def read_csv(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise RuntimeError(f"{path.name}: 인코딩을 못 읽었습니다.")
    return [row for row in csv.DictReader(io.StringIO(text)) if any(row.values())]


def normalize(name: str) -> str:
    text = SPACE.sub("", name or "")
    for _ in range(2):
        text = TAIL.sub("", text)
    return text


def tokens(name: str) -> set[str]:
    """'기숙사/고시원' 처럼 여러 이름을 빗금으로 묶어 둔 소분류가 많다."""
    parts = [normalize(p) for p in re.split(r"[/,·]", name or "")]
    return {p for p in parts if len(p) >= 2}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv_if_present()
    settings = Settings.from_env()

    middle = {m.code: m for m in load_middle_master(settings)}
    seoul = sorted(read_csv(OUT_DIR / "seoul_industries.csv"), key=lambda r: r["SVC_INDUTY_CD"])

    # 소분류 두 곳에서 모은다. 공식 목록은 2023-02-28판이고, 실제 응답에는 최신 이름이 온다.
    small: dict[str, tuple[str, str]] = {}
    for row in read_csv(OUT_DIR / "upjong_small_official.csv"):
        if row["indsMclsCd"] in middle:
            small[row["indsSclsCd"]] = (row["indsSclsNm"], row["indsMclsCd"])
    before = len(small)
    for row in read_csv(OUT_DIR / "sbiz_stores_raw.csv"):
        code, name, mid = row.get("indsSclsCd"), row.get("indsSclsNm"), row.get("indsMclsCd")
        if code and name and mid in middle:
            small.setdefault(code, (name, mid))
    print(
        f"소분류 {len(small)}종 (공식 {before} + 실제 응답 {len(small) - before})"
        f" · 중분류 {len(middle)}종"
    )

    index: dict[str, list[str]] = defaultdict(list)
    for code, (name, _) in small.items():
        for token in tokens(name):
            index[token].append(code)

    picks: dict[str, tuple[list[str], str]] = {}
    hints: dict[str, list[str]] = {}
    for entry in seoul:
        target = normalize(entry["SVC_INDUTY_CD_NM"])
        if not target:
            continue
        if target in index:
            picks[entry["SVC_INDUTY_CD"]] = (index[target], "정확")
            continue
        # 부분 일치는 판정에 쓰지 않는다. '커피-음료'가 '음료 소매업'에, '일반의류'가
        # '의류/이불 수선업'에 걸리는 식으로, 흔한 낱말이 엉뚱한 소분류를 잡는다.
        # 모델에게 참고용으로만 건넨다.
        hints[entry["SVC_INDUTY_CD"]] = [
            code
            for code, (name, _) in small.items()
            if any((target in t or t in target) and len(t) >= 2 for t in tokens(name))
        ]

    print(f"  이름이 그대로 있는 것 {len(picks)}종")

    pending = [r for r in seoul if r["SVC_INDUTY_CD"] not in picks]
    if pending and settings.llm_model and settings.llm_api_key and settings.llm_base_url:
        print(f"  모델에게 물을 것 {len(pending)}종")
        asyncio.run(fill_with_model(settings, small, pending, picks, hints))

    rows = []
    unresolved = []
    for entry in seoul:
        code = entry["SVC_INDUTY_CD"]
        found, how = picks.get(code, ([], ""))
        ranked: list[str] = []
        evidence: list[str] = []
        for small_code in found:
            name, mid = small[small_code]
            if mid not in ranked:
                ranked.append(mid)
            if len(evidence) < 4 and name not in evidence:
                evidence.append(name)
        row = {
            "(서울시)업종명": entry["SVC_INDUTY_CD_NM"],
            "(서울시)코드명": code,
            "판정방식": how,
            "근거 소분류": " / ".join(evidence),
        }
        for rank in (1, 2, 3):
            pick = ranked[rank - 1] if len(ranked) >= rank else None
            row[f"top{rank} (공공데이터포털)업종명"] = middle[pick].name if pick else ""
            row[f"top{rank} (공공데이터포털)코드명"] = pick or ""
        if not ranked:
            unresolved.append(f"{code} {entry['SVC_INDUTY_CD_NM']}")
        rows.append(row)

    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n{len(rows)}행 → {OUT_PATH.name}")
    for how in ("정확", "모델"):
        print(f"  {how} {sum(1 for r in rows if r['판정방식'] == how)}종")
    if unresolved:
        print(f"  ⚠️ 못 붙인 것 {len(unresolved)}종: {unresolved}")
    return 0


async def fill_with_model(settings, small, pending, picks, hints) -> None:
    from openai import AsyncOpenAI

    listing = "\n".join(f"{c}\t{n}\t{m}" for c, (n, m) in sorted(small.items()))

    def describe(row) -> str:
        line = f"{row['SVC_INDUTY_CD']}\t{row['SVC_INDUTY_CD_NM']}"
        shortlist = [small[c][0] for c in hints.get(row["SVC_INDUTY_CD"], [])[:6]]
        if shortlist:
            line += f"\t(이름이 겹치는 소분류: {', '.join(shortlist)} — 업태가 다르면 무시)"
        return line

    async def ask(chunk):
        targets = "\n".join(describe(r) for r in chunk)
        async with AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_s,
            max_retries=2,
        ) as client:
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"[소상공인 소분류 {len(small)}종]\n소분류코드\t소분류명\t중분류코드\n"
                            f"{listing}\n\n[분류할 서울시 업종]\n코드\t업종명\n{targets}"
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                max_completion_tokens=settings.llm_max_tokens,
            )
        payload = json.loads(response.choices[0].message.content or "{}")
        for row in payload.get("matches") or []:
            kept = [c for c in (row.get("small_codes") or []) if c in small]
            if kept:
                picks[str(row.get("seoul_code"))] = (kept, "모델")

    for attempt in (1, 2, 3):
        left = [r for r in pending if r["SVC_INDUTY_CD"] not in picks]
        if not left:
            break
        size = max(1, BATCH // attempt)
        chunks = [left[i : i + size] for i in range(0, len(left), size)]
        for result in await asyncio.gather(*(ask(c) for c in chunks), return_exceptions=True):
            if isinstance(result, BaseException):
                print(f"    배치 실패: {type(result).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())

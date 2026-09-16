"""서울시 생활밀접업종 100종에 소상공인 중분류 75종을 뜻으로 묶는다.

앞서 글자 유사도로 해봤더니 "제과점 → 인쇄 및 제품 제작업"처럼 엉뚱한 게 1순위로 올라왔다.
한글 업종명은 겹치는 글자가 뜻과 무관한 경우가 많아 문자열 비교로는 안 된다.

그래서 모델에게 뜻을 보고 고르게 한다. 대신 **모델이 지어낸 코드는 전부 버린다** —
돌아온 코드를 75종 마스터에 대조해 없는 코드면 그 자리를 비운다.

결과는 후보일 뿐 확정 매핑이 아니다. 최종 판단은 사람이 한다.

사용:
    python examples/match_upjong.py
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.commercial_area.config import Settings, load_dotenv_if_present  # noqa: E402
from app.agents.commercial_area.schemas import MiddleCode  # noqa: E402
from app.agents.commercial_area.upjong import load_middle_master  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "schema_compare"
OUT_PATH = OUT_DIR / "업종매칭_서울시기준.csv"
BATCH = 10

COLUMNS = [
    "(서울시)업종명",
    "(서울시)코드명",
    "top1 (공공데이터포털)업종명",
    "top1 (공공데이터포털)코드명",
    "top2 (공공데이터포털)업종명",
    "top2 (공공데이터포털)코드명",
    "top3 (공공데이터포털)업종명",
    "top3 (공공데이터포털)코드명",
]

SYSTEM = """당신은 한국 표준산업분류와 상권 업종 체계에 정통한 분석가입니다.

서울시 '생활밀접업종'과 소상공인시장진흥공단 '상권업종 중분류'는 서로 다른 체계입니다.
서울시 쪽이 더 잘게 쪼개져 있어 여러 개가 소상공인 중분류 하나로 모이는 경우가 많습니다.

주어진 서울시 업종 각각에 대해, 그 가게가 **실제로 어느 중분류로 집계될지**를 기준으로
후보 3개를 가장 그럴듯한 순서로 고르세요.

규칙
- 반드시 주어진 중분류 목록의 코드만 쓰세요. 목록에 없는 코드를 지어내지 마세요.
- 글자가 겹치는지가 아니라 **업태가 같은지**로 판단하세요.
  예: '제과점'은 빵을 파는 음식점이지 인쇄업이 아닙니다.
      '동물병원'은 사람 병원이 아니라 수의업입니다.
      '편의점'은 종합 소매업입니다.
      '커피-음료'는 비알코올 음료점업입니다.
- 대분류가 맞는지 먼저 보세요. 소매인지 음식인지 서비스인지가 어긋나면 후보가 아닙니다.
- 마땅한 후보가 3개가 안 되면 있는 만큼만 쓰세요. 억지로 채우지 마세요.

출력은 JSON만. 형식:
{"matches":[{"seoul_code":"CS100001","candidates":["I201","I210","I206"]}]}"""


def read_csv(path: Path) -> list[dict[str, str]]:
    """엑셀로 한 번 열었다 저장하면 cp949가 된다. 둘 다 받아준다."""
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


def master_block(master: list[MiddleCode]) -> str:
    lines = [f"{m.code}\t{m.major_name}\t{m.name}" for m in master]
    return "코드\t대분류\t중분류명\n" + "\n".join(lines)


async def ask(settings: Settings, master: list[MiddleCode], chunk: list[dict]) -> dict[str, list]:
    from openai import AsyncOpenAI

    listing = "\n".join(f"{r['SVC_INDUTY_CD']}\t{r['SVC_INDUTY_CD_NM']}" for r in chunk)
    user = (
        f"[소상공인 상권업종 중분류 {len(master)}종]\n{master_block(master)}\n\n"
        f"[분류할 서울시 생활밀접업종 {len(chunk)}종]\n코드\t업종명\n{listing}"
    )
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
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=settings.llm_max_tokens,
        )
    payload = json.loads(response.choices[0].message.content or "{}")
    return {
        str(row.get("seoul_code")): list(row.get("candidates") or [])
        for row in payload.get("matches") or []
    }


async def main_async() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv_if_present()
    settings = Settings.from_env()
    for name, value in (
        ("ELICE_MODEL", settings.llm_model),
        ("ELICE_API_KEY", settings.llm_api_key),
        ("ELICE_BASE_URL", settings.llm_base_url),
    ):
        if not value:
            print(f"{name}이 없습니다.")
            return 1

    master = sorted(load_middle_master(settings), key=lambda m: m.code)
    known = {m.code: m for m in master}
    seoul = sorted(read_csv(OUT_DIR / "seoul_industries.csv"), key=lambda r: r["SVC_INDUTY_CD"])
    print(f"서울시 {len(seoul)}종 × 소상공인 {len(master)}종")

    picks: dict[str, list[str]] = {}
    invalid: list[tuple[str, str]] = []

    async def run(batch_rows: list[dict], size: int) -> None:
        chunks = [batch_rows[i : i + size] for i in range(0, len(batch_rows), size)]
        for chunk_result in await asyncio.gather(
            *(ask(settings, master, c) for c in chunks), return_exceptions=True
        ):
            if isinstance(chunk_result, BaseException):
                print(f"  배치 실패: {type(chunk_result).__name__} {chunk_result}")
                continue
            for code, candidates in chunk_result.items():
                kept: list[str] = []
                for candidate in candidates:
                    if candidate in known and candidate not in kept:
                        kept.append(candidate)
                    elif candidate not in known:
                        invalid.append((code, str(candidate)))
                if kept:
                    picks[code] = kept[:3]

    await run(seoul, BATCH)
    # 배치 하나가 통째로 비어 돌아오는 일이 있다. 빠진 것만 더 작게 잘라 다시 묻는다.
    for attempt in (1, 2):
        pending = [r for r in seoul if not picks.get(r["SVC_INDUTY_CD"])]
        if not pending:
            break
        print(f"  재시도 {attempt}회차: {len(pending)}종")
        await run(pending, max(1, BATCH // (attempt * 2)))

    rows = []
    missing = []
    for entry in seoul:
        code = entry["SVC_INDUTY_CD"]
        row = {"(서울시)업종명": entry["SVC_INDUTY_CD_NM"], "(서울시)코드명": code}
        chosen = picks.get(code, [])
        if not chosen:
            missing.append(f"{code} {entry['SVC_INDUTY_CD_NM']}")
        for rank in (1, 2, 3):
            pick = chosen[rank - 1] if len(chosen) >= rank else None
            row[f"top{rank} (공공데이터포털)업종명"] = known[pick].name if pick else ""
            row[f"top{rank} (공공데이터포털)코드명"] = pick or ""
        rows.append(row)

    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"{len(rows)}행 → {OUT_PATH.name}")
    print(f"  top1까지 채워진 것 {sum(1 for r in rows if r[COLUMNS[3]])}종")
    print(f"  top3까지 채워진 것 {sum(1 for r in rows if r[COLUMNS[7]])}종")
    if invalid:
        print(f"  ⚠️ 마스터에 없어 버린 코드 {len(invalid)}개: {invalid[:8]}")
    if missing:
        print(f"  ⚠️ 후보가 하나도 없는 서울시 업종 {len(missing)}종: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

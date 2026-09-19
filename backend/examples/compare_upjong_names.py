"""소상공인 중분류 75종과 서울시 생활밀접업종 100종의 이름 유사도를 매긴다.

**이건 매핑이 아니라 후보 나열이다.** 글자만 보고 잰 값이라
"비알코올 음료점업" ↔ "커피-음료"처럼 같은 뜻인데 글자가 안 겹치면 점수가 낮게 나온다.
반대로 "일반 교육기관" ↔ "일반교습학원"처럼 글자가 겹쳐도 뜻이 다를 수 있다.
최종 판단은 사람이 한다.

두 체계는 코드가 겹치지 않는다(`I201` vs `CS100001`). 이름 말고는 붙일 단서가 없다.

사용:
    python examples/compare_upjong_names.py
"""

from __future__ import annotations

import csv
import io
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.commercial_area.config import Settings, load_dotenv_if_present  # noqa: E402
from app.agents.commercial_area.industries import load_middle_master  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "schema_compare"
TOP_N = 5

# 뜻을 바꾸지 않으면서 글자만 다르게 만드는 것들을 떨어낸다.
NOISE = re.compile(r"[\s,·ㆍ/\-()]|및|그\s*외|기타")
TAIL = re.compile(r"(서비스업|운영업|관련업|점업|업소|업)$")


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


def normalize(name: str) -> str:
    text = NOISE.sub("", name or "")
    for _ in range(2):
        text = TAIL.sub("", text)
    return text


def bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)} or {text}


def similarity(left: str, right: str) -> float:
    a, b = normalize(left), normalize(right)
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    ga, gb = bigrams(a), bigrams(b)
    jaccard = len(ga & gb) / len(ga | gb)
    score = max(seq, jaccard)
    # 한쪽이 다른 쪽을 통째로 품으면("의원" ⊂ "치과의원") 글자 수 차이로 점수가 깎이는 걸 보정한다.
    if a in b or b in a:
        score = min(1.0, score + 0.15)
    return round(score, 4)


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    try:
        handle = path.open("w", encoding="utf-8-sig", newline="")
    except PermissionError:
        # 엑셀이 열고 있으면 잠긴다. 한 파일 때문에 나머지까지 못 만드는 일은 없게 한다.
        print(f"  ⚠️ {path.name}: 열려 있어 건너뜁니다.")
        return
    with handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv_if_present()
    settings = Settings.from_env()

    sbiz = sorted(load_middle_master(settings), key=lambda m: m.code)
    seoul = sorted(read_csv(OUT_DIR / "seoul_industries.csv"), key=lambda r: r["SVC_INDUTY_CD"])
    print(f"소상공인 중분류 {len(sbiz)}종 · 서울시 생활밀접업종 {len(seoul)}종")

    # 엑셀이 망가뜨린 목록 파일을 다시 만든다.
    side = [
        {
            "system": "소상공인 중분류",
            "code": m.code,
            "name": m.name,
            "parent_code": m.major_code,
            "parent_name": m.major_name,
        }
        for m in sbiz
    ] + [
        {
            "system": "서울시 생활밀접",
            "code": r["SVC_INDUTY_CD"],
            "name": r["SVC_INDUTY_CD_NM"],
            "parent_code": "",
            "parent_name": "",
        }
        for r in seoul
    ]
    write_csv(
        OUT_DIR / "upjong_side_by_side.csv",
        side,
        ["system", "code", "name", "parent_code", "parent_name"],
    )

    pairs = [
        {
            "sbiz_code": m.code,
            "sbiz_major": m.major_name,
            "sbiz_name": m.name,
            "seoul_code": r["SVC_INDUTY_CD"],
            "seoul_name": r["SVC_INDUTY_CD_NM"],
            "score": similarity(m.name, r["SVC_INDUTY_CD_NM"]),
        }
        for m in sbiz
        for r in seoul
    ]
    columns = ["sbiz_code", "sbiz_major", "sbiz_name", "seoul_code", "seoul_name", "score", "rank"]

    ranked = sorted(pairs, key=lambda p: -p["score"])
    write_csv(OUT_DIR / "upjong_similarity_pairs.csv", ranked, columns)

    top: list[dict] = []
    for m in sbiz:
        mine = sorted((p for p in pairs if p["sbiz_code"] == m.code), key=lambda p: -p["score"])[
            :TOP_N
        ]
        for rank, row in enumerate(mine, 1):
            top.append({**row, "rank": rank})
    write_csv(OUT_DIR / "upjong_similarity_top5.csv", top, columns)

    # 서울시 100종을 기준으로 뒤집은 것. 리포트가 서울시 체계를 쓰므로 이쪽이 실제 작업 방향이다.
    seoul_top: list[dict] = []
    seoul_wide: list[dict] = []
    for entry in seoul:
        code = entry["SVC_INDUTY_CD"]
        mine = sorted((p for p in pairs if p["seoul_code"] == code), key=lambda p: -p["score"])
        for rank, row in enumerate(mine[:TOP_N], 1):
            seoul_top.append({**row, "rank": rank})
        wide = {"seoul_code": code, "seoul_name": entry["SVC_INDUTY_CD_NM"]}
        for rank, row in enumerate(mine[:3], 1):
            wide[f"top{rank}_score"] = row["score"]
            wide[f"top{rank}_code"] = row["sbiz_code"]
            wide[f"top{rank}_name"] = row["sbiz_name"]
            wide[f"top{rank}_major"] = row["sbiz_major"]
        seoul_wide.append(wide)

    write_csv(OUT_DIR / "seoul_to_sbiz_top5.csv", seoul_top, columns)
    wide_columns = ["seoul_code", "seoul_name"] + [
        f"top{n}_{field}" for n in (1, 2, 3) for field in ("score", "code", "name", "major")
    ]
    write_csv(OUT_DIR / "seoul_to_sbiz_best.csv", seoul_wide, wide_columns)

    print(f"전체 쌍 {len(pairs):,}개 → upjong_similarity_pairs.csv (점수 내림차순)")
    print(f"소상공인 {len(sbiz)}종 기준 상위 {TOP_N} → upjong_similarity_top5.csv")
    print(f"서울시 {len(seoul)}종 기준 상위 {TOP_N} → seoul_to_sbiz_top5.csv")
    print(f"서울시 {len(seoul_wide)}행 한 줄 요약 → seoul_to_sbiz_best.csv")

    buckets = [(0.8, "거의 같은 이름"), (0.6, "비슷함"), (0.4, "약함"), (0.0, "글자로는 못 붙임")]
    for label, best in (
        ("소상공인 75종 기준", {p["sbiz_code"]: p for p in reversed(ranked)}),
        ("서울시 100종 기준", {p["seoul_code"]: p for p in reversed(ranked)}),
    ):
        print()
        print(f"  [{label}]")
        for floor, name in buckets:
            hit = [p for p in best.values() if p["score"] >= floor]
            best = {k: v for k, v in best.items() if v["score"] < floor}
            print(f"    {name:<16} {len(hit):>3}종")

    used = {row["top1_code"] for row in seoul_wide if row.get("top1_code")}
    unused = [m for m in sbiz if m.code not in used]
    print()
    print(f"  서울시 100종의 1순위로 한 번도 안 뽑힌 소상공인 업종 {len(unused)}종")
    for m in unused:
        print(f"    {m.code} {m.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

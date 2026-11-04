import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class Seed:
    kind: Literal["E1", "E2", "E3"]
    industry_code: str
    field: Literal["reasons_segments", "risks_segments"]
    expected_kind: Literal["missing_evidence", "scope_mismatch"]
    support_fact_ids: tuple[str, ...]
    wrong_fact_id: str | None


@dataclass(frozen=True)
class Case:
    case_id: str
    request_id: str
    split: Literal["tune", "test"]
    source: Literal["clean", "seeded", "real"]
    draft: dict
    seeds: tuple[Seed, ...]


def dump_cases(cases: list[Case], path: Path) -> None:
    payload = [asdict(case) for case in cases]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cases(path: Path) -> list[Case]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    for item in payload:
        seeds = tuple(
            Seed(**{**seed, "support_fact_ids": tuple(seed["support_fact_ids"])})
            for seed in item["seeds"]
        )
        cases.append(Case(**{**item, "seeds": seeds}))
    return cases


def split_requests(request_ids: list[str], seed: int = 20261023) -> dict[str, str]:
    ordered = sorted(request_ids)
    random.Random(seed).shuffle(ordered)
    tune_count = (len(ordered) + 1) // 2
    return {
        request_id: "tune" if index < tune_count else "test"
        for index, request_id in enumerate(ordered)
    }

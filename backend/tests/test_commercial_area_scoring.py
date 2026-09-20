"""요약이 prompt.md 의 규칙을 지켰는지 채점하는 과정을 검사합니다."""

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any

from app.agents.commercial_area.llm import PROMPT_PATH
from app.agents.commercial_area.scoring import (
    EMPTY_STORE_OVERALL,
    MAX_INDEX_NOTE_CHARS,
    MAX_RADIUS_NOTE_CHARS,
    PATH_SPEC,
    PAYLOAD_ERROR_CHARS,
    _has_source,
    check,
    check_payload_size,
    errors,
)

DATA_DIR = Path(__file__).resolve().parent / "data" / "commercial_area_eval"
TABLE_ROW = re.compile(r"^\|\s*`(/[^`]+)`\s*\|\s*([^|]+?)\s*\|")

GOLDEN_NAMES = ("ogeum_176", "wirye_120")


class NotApplicable(Exception):
    pass


def load_golden(name: str) -> dict[str, Any]:
    return json.loads((DATA_DIR / f"{name}.json").read_text(encoding="utf-8"))


def note_with(summary: dict[str, Any], path: str) -> dict[str, Any]:
    for note in summary["index_notes"]:
        if note["path"] == path:
            return note
    raise NotApplicable(path)


def add_unknown_path(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["index_notes"].append({"path": "/made/up", "label": "지어냄", "text": "설명"})


def rename_label(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["index_notes"][0]["label"] = "엉뚱한 이름표"


def reverse_notes(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["index_notes"].reverse()


def drop_index_note(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note = note_with(summary, "/by_major")
    summary["index_notes"].remove(note)


def duplicate_index_note(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["index_notes"].append(copy.deepcopy(summary["index_notes"][0]))


def add_unknown_radius(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["radius_notes"].append({"radius_m": 999, "text": "입력에 없는 반경입니다."})


def reverse_radius_notes(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["radius_notes"].reverse()


def use_jargon(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["overall"] = "HHI 가 높고 마샬리안 집적이 뚜렷합니다."


def name_other_district(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["concentration"] = "강남구 전체와 비교하면 많습니다."


def miscount_trade_areas(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note_with(summary, "/trade_areas")["text"] = "3곳과 겹칩니다."


def flip_percentile(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note_with(summary, "/restaurant_density/value")["text"] = "서울 상권 중 상위 약 99% 입니다."


def hide_baseline(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note_with(summary, "/by_middle")["text"] = "가장 두드러진 업종이 약 1.8배 많습니다."


def drop_district_baseline(data: dict[str, Any], summary: dict[str, Any]) -> None:
    name = (data.get("district_baseline") or {}).get("signgu_name") or ""
    data["district_baseline"] = None
    for note in summary["radius_notes"] + summary["index_notes"]:
        note["text"] = note["text"].replace(name, "이 일대")
    for key in ("overall", "concentration"):
        if summary.get(key):
            summary[key] = summary[key].replace(name, "이 일대")
    note_with(summary, "/by_middle")["text"] = (
        "가장 두드러진 업종이 반경 2km 안에서 약 1.8배, 자치구 전체와 비교하면 약 2.2배입니다."
    )


def drop_franchise(data: dict[str, Any], _: dict[str, Any]) -> None:
    data["franchise"] = None


def empty_store(data: dict[str, Any], summary: dict[str, Any]) -> None:
    data["store_total"] = 0
    summary["overall"] = EMPTY_STORE_OVERALL


def wrong_empty_store_text(data: dict[str, Any], summary: dict[str, Any]) -> None:
    data["store_total"] = 0
    summary["radius_notes"] = []
    summary["overall"] = "이 일대는 점포가 아주 많은 번화가입니다."


def drop_overall(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["overall"] = None


def drop_concentration(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["concentration"] = None


def overlong_index_note(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note = summary["index_notes"][0]
    note["text"] = note["text"] + "가" * MAX_INDEX_NOTE_CHARS


def overlong_radius_note(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note = summary["radius_notes"][0]
    note["text"] = note["text"] + "가" * MAX_RADIUS_NOTE_CHARS


def judge_the_site(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note_with(summary, "/diversity/effective_categories")["text"] = "업종이 고르게 섞여 유리합니다."


def recommend_business(_: dict[str, Any], summary: dict[str, Any]) -> None:
    summary["overall"] = "한식 창업을 추천합니다."


def oversized_payload(data: dict[str, Any], _: dict[str, Any]) -> None:
    data["description"] = "가" * PAYLOAD_ERROR_CHARS


BREAKAGES = (
    ("PATH_UNKNOWN", add_unknown_path),
    ("LABEL_MISMATCH", rename_label),
    ("NOTE_ORDER", reverse_notes),
    ("MISSING_NOTE", drop_index_note),
    ("DUPLICATE_NOTE", duplicate_index_note),
    ("RADIUS_SET", add_unknown_radius),
    ("RADIUS_ORDER", reverse_radius_notes),
    ("FORBIDDEN_TERM", use_jargon),
    ("DISTRICT_NAME", name_other_district),
    ("TRADE_AREA_COUNT", miscount_trade_areas),
    ("PERCENTILE_FLIP", flip_percentile),
    ("BASELINE_MISSING", hide_baseline),
    ("DISTRICT_BASELINE", drop_district_baseline),
    ("NULL_NOTE", drop_franchise),
    ("EMPTY_STORE", empty_store),
    ("EMPTY_STORE_TEXT", wrong_empty_store_text),
    ("MISSING_OVERALL", drop_overall),
    ("MISSING_CONCENTRATION", drop_concentration),
    ("LEN_INDEX_NOTE", overlong_index_note),
    ("LEN_RADIUS_NOTE", overlong_radius_note),
    ("JUDGEMENT_WORD", judge_the_site),
    ("RECOMMENDATION", recommend_business),
    ("PAYLOAD_SIZE", oversized_payload),
)


def quote_other_district(data: dict[str, Any], summary: dict[str, Any]) -> None:
    data["trade_areas"][0]["name"] = "구로구청"
    note_with(summary, "/trade_areas")["text"] = "발달상권인 구로구청 등 8곳과 겹칩니다."


def quote_district_without_baseline(data: dict[str, Any], summary: dict[str, Any]) -> None:
    data["district_baseline"] = None
    data["trade_areas"][0]["name"] = "구로구청"
    note_with(summary, "/trade_areas")["text"] = "발달상권인 구로구청 등 8곳과 겹칩니다."
    note_with(summary, "/by_middle")["text"] = (
        "가장 두드러진 업종이 반경 2km 안에서 약 1.8배입니다."
    )
    summary["concentration"] = "500m 기준 한식 음식점업이 가장 빽빽하게 모여 있습니다."


def split_the_trade_area_count(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note_with(summary, "/trade_areas")["text"] = (
        "골목상권 5곳과 발달상권 2곳, 전통시장 1곳 등 8곳과 겹칩니다."
    )


def use_a_nickname(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note_with(summary, "/trade_areas")["text"] = (
        "송리단길이라고도 불리는 골목상권 등 8곳과 겹칩니다."
    )


def quote_startup_centre(data: dict[str, Any], summary: dict[str, Any]) -> None:
    data["trade_areas"][0]["name"] = "구로창업지원센터"
    note_with(summary, "/trade_areas")["text"] = "골목상권인 구로창업지원센터 등 8곳과 겹칩니다."


def round_the_percentile(_: dict[str, Any], summary: dict[str, Any]) -> None:
    note_with(summary, "/restaurant_density/value")["text"] = (
        "1km²당 음식점이 약 616개로, 서울 상권 중 상위 약 25% 정도입니다."
    )


VALID_REWRITES = (
    ("다른 자치구 이름이 든 상권명", quote_other_district),
    ("자치구 기준이 없을 때의 상권명", quote_district_without_baseline),
    ("유형별로 나눠 적은 상권 개수", split_the_trade_area_count),
    ("별칭을 풀어 쓴 문장", use_a_nickname),
    ("창업이 든 상권명", quote_startup_centre),
    ("5% 단위로 반올림한 백분위", round_the_percentile),
)


class GoldenSummaryTests(unittest.TestCase):
    def test_golden_summaries_have_no_errors(self):
        for name in GOLDEN_NAMES:
            with self.subTest(name=name):
                data = load_golden(name)
                found = errors(check(data, data.get("summary") or {}))
                self.assertEqual([v.code for v in found], [])

    def test_golden_payloads_fit_the_decision_budget(self):
        for name in GOLDEN_NAMES:
            with self.subTest(name=name):
                found = errors(check_payload_size(load_golden(name)))
                self.assertEqual([v.code for v in found], [])

    def test_golden_covers_every_documented_path(self):
        data = load_golden("ogeum_176")
        used = {n["path"] for n in data["summary"]["index_notes"]}
        self.assertEqual(used, {path for path, _ in PATH_SPEC})

    def test_golden_explains_exactly_the_paths_that_have_values(self):
        for name in GOLDEN_NAMES:
            with self.subTest(name=name):
                data = load_golden(name)
                used = [n["path"] for n in data["summary"]["index_notes"]]
                expected = [path for path, _ in PATH_SPEC if _has_source(data, path)]
                self.assertEqual(used, expected)

    def test_no_violation_is_reported_twice(self):
        for name in GOLDEN_NAMES:
            with self.subTest(name=name):
                data = load_golden(name)
                for _, break_it in BREAKAGES:
                    broken = copy.deepcopy(data)
                    summary = broken["summary"]
                    try:
                        break_it(broken, summary)
                    except NotApplicable:
                        continue
                    found = check(broken, summary)
                    self.assertEqual(len(found), len(set(found)))


class ValidSummaryTests(unittest.TestCase):
    def test_rule_abiding_rewrites_raise_no_error(self):
        for label, rewrite in VALID_REWRITES:
            with self.subTest(label=label):
                data = load_golden("ogeum_176")
                summary = data["summary"]
                rewrite(data, summary)
                found = errors(check(data, summary))
                self.assertEqual([v.code for v in found], [], f"{label}: {found}")


class BreakageTests(unittest.TestCase):
    def test_each_rule_catches_its_own_breakage(self):
        for name in GOLDEN_NAMES:
            for code, break_it in BREAKAGES:
                with self.subTest(name=name, code=code):
                    data = load_golden(name)
                    summary = data["summary"]
                    before = {v.code for v in check(data, summary)}
                    try:
                        break_it(data, summary)
                    except NotApplicable:
                        continue
                    self.assertNotIn(code, before)
                    self.assertIn(code, {v.code for v in check(data, summary)})

    def test_breakages_do_not_trip_unrelated_rules(self):
        for name in GOLDEN_NAMES:
            for code, break_it in BREAKAGES:
                with self.subTest(name=name, code=code):
                    data = load_golden(name)
                    summary = data["summary"]
                    before = {v.code for v in check(data, summary)}
                    try:
                        break_it(data, summary)
                    except NotApplicable:
                        continue
                    after = {v.code for v in check(data, summary)}
                    self.assertEqual(after - before, {code})


class PromptSyncTests(unittest.TestCase):
    def test_path_spec_matches_the_prompt_table(self):
        rows = []
        for line in PROMPT_PATH.read_text(encoding="utf-8").splitlines():
            match = TABLE_ROW.match(line)
            if match:
                rows.append((match.group(1), match.group(2)))
        self.assertEqual(rows, list(PATH_SPEC))


if __name__ == "__main__":
    unittest.main()

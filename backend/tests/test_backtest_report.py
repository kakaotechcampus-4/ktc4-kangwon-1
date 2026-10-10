import json
import tempfile
import unittest
from pathlib import Path

from backtest.report import build_report, main


def interval(mean: float, low: float, high: float, wins: bool = False) -> dict:
    return {"mean": mean, "low": low, "high": high, "wins": wins}


def stage1(vs: dict | None = None) -> dict:
    signals = {
        name: {"mean": 0.5, "low": 0.4, "high": 0.6}
        for name in ("lifecycle", "seoul_average", "popularity", "persistence")
    }
    return {
        "pairs": 1445,
        "signals": signals,
        "lifecycle_vs": vs
        if vs is not None
        else {
            "seoul_average": interval(0.05, 0.01, 0.09),
            "popularity": interval(0.05, 0.02, 0.08),
            "persistence": interval(0.05, 0.03, 0.07),
        },
        "errors": {"SeoulOpenAPINoDataError": 3},
        "created": "2026-10-06",
    }


def stage2(**overrides) -> dict:
    base = {
        "samples": 40,
        "ok": 38,
        "recommended_correct_vs_seoul": [0.6, 0.55, 0.65],
        "not_recommended_correct_vs_seoul": [0.5, 0.4, 0.6],
        "recommended_correct_vs_area": [0.45, 0.3, 0.6],
        "not_recommended_correct_vs_area": [0.3, 0.2, 0.4],
        "recommended_minus_not": [0.01, -0.02, 0.04],
        "pending_ratio": 0.25,
        "unscorable_ratio": None,
        "errors": 1,
        "error_types": {"ValueError": 1},
        "stopped": None,
        "calls": 80,
        "created": "2026-10-06",
    }
    return {**base, **overrides}


def verdict(
    status: str,
    kind: str,
    survival=None,
    seoul=None,
    correct=None,
    mean=0.0,
    area=None,
    correct_area=None,
) -> dict:
    return {
        "industry": "CS1",
        "kind": kind,
        "status": status,
        "survival": survival,
        "seoul": seoul,
        "area": area,
        "mean_stores": mean,
        "correct_vs_seoul": correct,
        "correct_vs_area": correct_area,
    }


def item(kind: str, v: dict) -> dict:
    return {"kind": kind, "industry": "CS1", "name": "한식", "verdict": v}


RECORDS = [
    {
        "area": {"kind": "골목상권", "name": "가상권", "code": "1"},
        "status": "ok",
        "items": [
            item("recommended", verdict("scored", "recommended", 0.9, 0.85, True, 12, 0.92, False)),
            item("not_recommended", verdict("scored", "not_recommended", 0.8, 0.85, True, 12)),
            item("recommended", verdict("pending", "recommended", None, None, None, 2.5)),
            item("not_recommended", verdict("unscorable", "not_recommended")),
        ],
    },
    {
        "area": {"kind": "발달상권", "name": "나상권", "code": "2"},
        "status": "ok",
        "items": [
            item("not_recommended", verdict("scored", "not_recommended", 0.9, 0.85, False, 9))
        ],
    },
    {"area": {"kind": "골목상권", "name": "다상권", "code": "3"}, "status": "area_mismatch"},
    {
        "area": {"kind": "골목상권", "name": "라상권", "code": "4"},
        "status": "error",
        "error": "Boom",
    },
    {"area": {"kind": "골목상권", "name": "마상권", "code": "5"}, "status": "waiting"},
]


class ReportTest(unittest.TestCase):
    def test_limitations_come_first_with_all_bullets(self):
        text = build_report(stage1(), stage2(), RECORDS, mock=False)
        head = text.index("## 먼저 읽을 한계")
        self.assertLess(head, text.index("## 1단계"))
        self.assertLess(head, text.index("## 2단계"))
        for line in (
            '기존 가게와 새 가게가 섞인 폐업률이다. "T에 새로 열었다면 버텼을까"의 근사치다.',
            "인과가 아니라 상관이다. 창업자는 자리를 스스로 고른다.",
            "상권 입력은 반경 기준이 아니라 상권 점포 수로 대체했다.",
            "같은 원천(개폐업 에이전트 입력과 같은 API)이다. "
            "시점을 나눴고 관성 기준선으로 이 효과를 걸러야 한다.",
            "2단계는 같은 상가를 반복 실행하지 않아 모델 응답의 흔들림을 재지 않는다.",
            "모델의 학습 자료가 관찰 기간(2024~2026년)을 포함할 수 있어, 입력에서 T 이후 자료를 "
            "가려도 모델이 아는 사후 지식이 판단에 섞일 수 있다.",
        ):
            self.assertIn(f"- {line}", text)
        self.assertLess(text.index("사후 지식"), text.index("## 1단계"))

    def test_stage1_paragraph_names_resampling_unit_and_coverage(self):
        summary = {**stage1(), "areas": 1452, "coverage_mean": 0.618}
        text = build_report(summary, None, None, mock=False)
        self.assertIn(
            "채점한 상권·시점 짝 1445개, 상권 1452곳. 구간은 상권을 다시 뽑아 냈다. "
            "네 점수가 모두 값을 가진 업종만 비교했다"
            "(개폐업 점수가 채점 가능 업종의 평균 62%를 덮음).",
            text,
        )
        old = build_report(stage1(), None, None, mock=False)
        self.assertNotIn("네 점수가 모두 값을 가진 업종만 비교했다", old)

    def test_stage1_all_wins(self):
        text = build_report(stage1(), None, None, mock=False)
        self.assertIn("정보가 있다", text)
        self.assertIn("0.400 ~ 0.600", text)
        self.assertIn("SeoulOpenAPINoDataError 3건", text)

    def test_stage1_not_all_wins(self):
        vs = {
            "seoul_average": interval(-0.05, -0.07, -0.04),
            "popularity": interval(0.05, 0.02, 0.08),
            "persistence": interval(0.0, -0.02, 0.02),
        }
        text = build_report(stage1(vs), None, None, mock=False)
        self.assertNotIn("정보가 있다", text)
        self.assertIn("기준선① 서울 업종 평균(짐)", text)
        self.assertIn("기준선③ 관성(구분 안 됨)", text)
        self.assertIn("이기지 못했다", text)

    def test_stage2_wording(self):
        text = build_report(stage1(), stage2(), None, mock=False)
        self.assertIn("추천과 비추천의 차이가 있다고 말할 수 없다", text)
        self.assertIn("동전 던지기(50%)와 구분할 수 없다", text)
        self.assertIn("50%보다 높다", text)
        self.assertIn("50%보다 낮다", text)
        self.assertNotIn("(대역 모델)", text)

    def test_stage2_line_prints_agent_and_decision_status(self):
        summary = stage2(
            agent_status={
                "business_lifecycle": {"ok": 2},
                "floating_population": {"error": 1, "ok": 1},
            },
            decision_status={"partial": 2},
        )
        text = build_report(stage1(), summary, None, mock=False)
        line = next(line for line in text.splitlines() if line.startswith("성공 38곳"))
        self.assertIn(
            "에이전트 상태: business_lifecycle(ok 2), floating_population(error 1, ok 1). "
            "판정 상태: partial 2.",
            line,
        )
        self.assertNotIn("에이전트 상태", build_report(stage1(), stage2(), None, mock=False))

    def test_ratios_are_read_against_measured_base_rates(self):
        summary = stage2(
            base_rates={"seoul_longer": 0.507, "area_longer": 0.547, "cells": 6219},
            recommended_correct_vs_seoul=[0.6, 0.55, 0.65],
            recommended_correct_vs_area=[0.55, 0.5, 0.6],
            not_recommended_correct_vs_seoul=[0.4, 0.35, 0.45],
            not_recommended_correct_vs_area=[0.45, 0.4, 0.5],
        )
        text = build_report(stage1(), summary, None, mock=False)
        self.assertIn("| 항목 | 값 | 표본 수 | 95% 구간 | 기준 비율 | 해석 |", text)
        rows = {
            line.split(" | ")[0][2:]: line
            for line in text.splitlines()
            if line.startswith("| 추천") or line.startswith("| 비추천")
        }
        self.assertTrue(
            rows["추천 업종이 서울 평균보다 오래 버틴 비율"].endswith(
                "| 50.7% | 기준 비율보다 높다 |"
            )
        )
        self.assertTrue(
            rows["추천 업종이 상권 평균보다 오래 버틴 비율"].endswith(
                "| 54.7% | 아무 업종이나 고른 기준 비율과 구분할 수 없다 |"
            )
        )
        self.assertTrue(
            rows["비추천 업종이 서울 평균보다 덜 버틴 비율"].endswith(
                "| 49.3% | 기준 비율보다 낮다 |"
            )
        )
        self.assertTrue(
            rows["비추천 업종이 상권 평균보다 덜 버틴 비율"].endswith(
                "| 45.3% | 아무 업종이나 고른 기준 비율과 구분할 수 없다 |"
            )
        )
        self.assertTrue(
            rows["추천 − 비추천 평균 생존율"].endswith(
                "| - | 추천과 비추천의 차이가 있다고 말할 수 없다 |"
            )
        )
        self.assertNotIn("동전 던지기(50%)", text)
        self.assertNotIn("50%보다", text)

    def test_missing_base_rates_fall_back_to_half(self):
        text = build_report(stage1(), stage2(), None, mock=False)
        row = next(
            line
            for line in text.splitlines()
            if line.startswith("| 추천 업종이 서울 평균보다 오래 버틴 비율")
        )
        self.assertTrue(row.endswith("| 50.0% | 50%보다 높다 |"))

    def test_missing_or_single_baseline_never_claims_information(self):
        empty = build_report(stage1({}), None, None, mock=False)
        self.assertNotIn("정보가 있다", empty)
        self.assertIn("(비교 없음)", empty)
        self.assertIn("| 개폐업 − 기준선① 서울 업종 평균 | - | - | 비교 없음 |", empty)
        one = build_report(
            stage1({"popularity": interval(0.05, 0.02, 0.08, True)}), None, None, mock=False
        )
        self.assertNotIn("정보가 있다", one)
        self.assertIn("기준선① 서울 업종 평균(비교 없음)", one)

    def test_small_samples_and_degenerate_intervals(self):
        text = build_report(stage1(), stage2(), RECORDS, mock=False)
        self.assertIn("표본이 너무 적어 판단할 수 없다", text)
        self.assertNotIn("50%보다 높다", text)
        flat = stage2(recommended_correct_vs_seoul=[0.0, 0.0, 0.0])
        self.assertIn(
            "표본이 너무 적어 판단할 수 없다",
            build_report(stage1(), flat, None, mock=False),
        )

    def test_reading_uses_displayed_precision(self):
        text = build_report(
            stage1(), stage2(recommended_minus_not=[0.1, 0.0004, 0.2]), None, mock=False
        )
        self.assertIn("추천과 비추천의 차이가 있다고 말할 수 없다", text)
        self.assertNotIn("추천 업종이 더 오래 버텼다", text)

    def test_missing_keys_and_records(self):
        text = build_report({}, {"samples": 3}, None, mock=False)
        self.assertIn("상가별 기록 없음", text)
        self.assertIn("상권 불일치 제외 -곳", text)
        self.assertNotIn("### 상가별", text)

    def test_mock_marker(self):
        text = build_report(stage1(), stage2(), RECORDS, mock=True)
        self.assertIn("대역 모델 결과다", text)
        self.assertIn("## 2단계 — 상가 40곳 (대역 모델)", text)

    def test_null_values_and_missing_stage2(self):
        text = build_report(
            stage1(), stage2(recommended_minus_not=None, pending_ratio=None), RECORDS, mock=False
        )
        self.assertIn("채점된 항목 없음", text)
        self.assertIn("2단계 결과 없음.", build_report(stage1(), None, None, mock=False))

    def test_records_tables(self):
        text = build_report(stage1(), stage2(), RECORDS, mock=False)
        self.assertIn("### 상권 종류별", text)
        self.assertIn("### 상가별", text)
        self.assertIn("판단 보류(점포 2.5개)", text)
        self.assertIn("채점 불가", text)
        self.assertIn(
            "한식 맞음 (서울 평균보다 오래 버팀 +5.0%p) / 틀림 (상권 평균보다 덜 버팀 -2.0%p)", text
        )
        self.assertIn("맞음 (서울 평균보다 덜 버팀", text)
        self.assertIn("틀림 (서울 평균보다 오래 버팀", text)
        self.assertIn("상권 불일치", text)
        self.assertIn("오류: Boom", text)
        self.assertIn("대기", text)

    def test_kind_table_lists_every_kind_with_any_status(self):
        records = [
            *RECORDS,
            {
                "area": {"kind": "관광특구", "name": "바상권", "code": "6"},
                "status": "area_mismatch",
            },
        ]
        text = build_report(stage1(), stage2(), records, mock=False)
        self.assertIn(
            "| 종류 | 전체 표본 | 성공 | 채점된 추천 | 서울 평균보다 오래 버틴 추천 |", text
        )
        self.assertIn("| 골목상권 | 4 | 1 | 1 | 1개 (100.0%) |", text)
        self.assertIn("| 발달상권 | 1 | 1 | 0 | - |", text)
        self.assertIn("| 관광특구 | 1 | 0 | 0 | - |", text)

    def test_limitations_name_the_base_quarter_rule_and_absent_items(self):
        text = build_report(stage1(), stage2(), RECORDS, mock=False)
        self.assertIn("- 채점 업종은 T 시점에 점포가 5개 이상 있던 업종이다.", text)
        self.assertIn("'관찰 불가'로 따로 센다", text)
        self.assertLess(text.index("관찰 불가"), text.index("## 1단계"))

    def test_absent_and_pending_items_say_why(self):
        absent = {**verdict("absent", "not_recommended"), "base_stores": 2.0}
        absent.pop("mean_stores")
        waiting = {**verdict("pending", "recommended", 0.9), "base_stores": 8.0}
        waiting.pop("mean_stores")
        records = [
            {
                "area": {"kind": "골목상권", "name": "가상권", "code": "1"},
                "status": "ok",
                "items": [item("not_recommended", absent), item("recommended", waiting)],
            }
        ]
        summary = stage2(
            absent_ratio=0.5,
            absent_ratio_by_kind={"recommended": 0.0, "not_recommended": 1.0},
        )
        text = build_report(stage1(), summary, records, mock=False)
        self.assertIn("관찰 불가(T 시점 점포 2개)", text)
        self.assertIn("판단 보류(이후 자료 없음)", text)
        self.assertIn("관찰 불가 비율 50.0% (추천 0.0%, 비추천 100.0%)", text)

    def test_call_limit_record_and_stop_reasons_read_in_korean(self):
        records = [
            *RECORDS,
            {"area": {"kind": "골목상권", "name": "사상권", "code": "7"}, "status": "call_limit"},
        ]
        text = build_report(stage1(), stage2(stopped="call_limit"), records, mock=False)
        self.assertIn("| 사상권 | 골목상권 | 호출 상한 도달 |", text)
        self.assertIn("중단 사유 호출 상한,", text)
        for code, words in (
            ("incomplete", "중간에 끊김"),
            ("agent_error", "에이전트 오류"),
            ("repeated_error", "같은 오류 반복"),
        ):
            self.assertIn(
                f"중단 사유 {words},",
                build_report(stage1(), stage2(stopped=code), None, mock=False),
            )

    def test_tied_items_are_not_counted_as_scored(self):
        tie = verdict("scored", "recommended", 0.85, 0.85, None, 12, 0.9, False)
        records = [
            {
                "area": {"kind": "골목상권", "name": "가상권", "code": "1"},
                "status": "ok",
                "items": [item("recommended", tie)],
            }
        ]
        text = build_report(stage1(), stage2(), records, mock=False)
        self.assertIn("| 골목상권 | 1 | 1 | 0 | - |", text)
        row = next(
            line
            for line in text.splitlines()
            if line.startswith("| 추천 업종이 서울 평균보다 오래 버틴 비율")
        )
        self.assertIn("| 0 |", row)

    def test_interval_unit_is_named(self):
        site = build_report(stage1(), stage2(interval_unit="site"), None, mock=False)
        self.assertIn("비율 구간은 상가를 다시 뽑아 냈다.", site)
        old = build_report(stage1(), stage2(), None, mock=False)
        self.assertIn("비율 구간은 항목을 다시 뽑아 냈다", old)

    def test_main_reads_a_chosen_stage2_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            chosen = out / "real_diag3"
            chosen.mkdir()
            (out / "stage1_summary.json").write_text(json.dumps(stage1()), encoding="utf-8")
            (chosen / "stage2_summary.json").write_text(
                json.dumps(stage2(samples=2, model="gpt-test")), encoding="utf-8"
            )
            self.assertEqual(main(["--out", tmp, "--stage2", str(chosen)]), 0)
            text = (chosen / "백테스트_보고서.md").read_text(encoding="utf-8")
            self.assertIn("## 2단계 — 상가 2곳", text)
            self.assertNotIn("(대역 모델)", text)
            self.assertFalse((out / "백테스트_보고서.md").exists())

    def test_main_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "mock").mkdir()
            (out / "stage1_summary.json").write_text(json.dumps(stage1()), encoding="utf-8")
            (out / "mock" / "stage2_summary.json").write_text(
                json.dumps(stage2()), encoding="utf-8"
            )
            (out / "mock" / "stage2_records.json").write_text(
                json.dumps(RECORDS, ensure_ascii=False), encoding="utf-8"
            )
            self.assertEqual(main(["--out", tmp]), 0)
            text = (out / "백테스트_보고서.md").read_text(encoding="utf-8")
            self.assertIn("(대역 모델)", text)


if __name__ == "__main__":
    unittest.main()

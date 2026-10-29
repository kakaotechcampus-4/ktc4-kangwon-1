"""심사위원 패킷이 초안 문장·문항 근거·근거 카드를 상한 안에서 보존하는지 검증합니다."""

import json
import re
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agentic import evaluators, examiner
from app.agentic.contracts import SubmitDraftInput, SubmitLInput
from app.canonical import canonical_json
from app.db.connection import connect
from app.text import has_digit
from tests import test_agentic_runtime as fixtures

ALIAS = re.compile(r"^[0-9a-f]{8}$")
FACT = {name: index for index, name in enumerate(examiner.FACT_COLUMNS)}
SCORE = {name: index for index, name in enumerate(examiner.SCORE_COLUMNS)}


def fact_id(index):
    return f"f_00000000-0000-4000-8000-{index:012d}"


def row(fid, **changes):
    return {
        "fact_id": fid,
        "source": "commercial_area",
        "metric": "store_count",
        "industry_code": "I201",
        "unit": "개",
        "period": "2023Q4",
        "status": "observed",
        "citable": 1,
        "value_json": json.dumps("값" * 200, ensure_ascii=False),
        "spatial_scope_json": '{"radius_m":500}',
    } | changes


def draft(segments):
    payload = {
        "report_id": "draft",
        "score_snapshot_id": "score",
        "top5": [
            {
                "industry_code": "I201",
                "industry_name": "시험 업종",
                "badge": "추천",
                "reasons_segments": segments,
                "risks_segments": [{"type": "text", "text": "위험 문장"}],
                "confirmation_conditions_segments": [],
                "fact_ids": [],
            }
        ],
        "summary_segments": [{"type": "text", "text": "요약 문장"}],
        "limitations_segments": [],
    }
    return SimpleNamespace(report_id="draft", model_dump=MagicMock(return_value=payload))


class ExaminerPersonaTests(unittest.TestCase):
    def test_persona_is_used_and_has_no_digit_to_copy(self):
        self.assertIs(evaluators.PERSONAS["examiner"], examiner.PERSONA)
        self.assertFalse(has_digit(examiner.PERSONA))
        for word in ("missing_evidence", "scope_mismatch", "duplicate_score", "action_condition"):
            self.assertIn(word, examiner.PERSONA)


class ExaminerPacketLimitTests(unittest.TestCase):
    def build(self, count, rows=None):
        ids = [fact_id(i) for i in range(count)]
        rows = rows or {fid: row(fid) for fid in ids}
        items = {
            "I201": [
                {"item": "D1", "status": "observed", "grade": 3, "points": 7.5, "fact_ids": ids}
            ]
        }
        segments = [
            {"type": "text", "text": "이유 문장"},
            {"type": "fact", "fact_id": ids[-1], "format": "count"},
        ]
        with (
            patch("app.agentic.examiner._score_items", return_value=items),
            patch("app.agentic.examiner.fact_rows", return_value=rows),
            patch("app.agentic.examiner.encode", side_effect=lambda scope, value: value),
        ):
            return ids, segments, examiner.review_packet(None, draft(segments))

    def test_sentence_facts_come_first_and_values_drop_from_the_tail(self):
        ids, segments, packet = self.build(40)
        self.assertLessEqual(len(canonical_json(packet)), examiner.MAX_PACKET_CHARS)
        candidate = packet["candidates"][0]
        self.assertEqual(candidate["reasons_segments"], segments)
        self.assertEqual(packet["summary_segments"], [{"type": "text", "text": "요약 문장"}])
        cards = packet["facts"]
        self.assertEqual([c[FACT["fact_id"]] for c in cards], [ids[-1], *ids[:-1]])
        self.assertEqual(cards[0][FACT["value"]], "값" * 200)
        self.assertIsNone(cards[-1][FACT["value"]])
        self.assertEqual(packet["omitted_fact_ids"], [])
        self.assertEqual(packet["fact_columns"], list(examiner.FACT_COLUMNS))
        for card in cards:
            self.assertIn(card[FACT["spatial_scope_ref"]], packet["spatial_scopes"])
            self.assertEqual(card[FACT["period"]], "2023Q4")
            self.assertEqual(card[FACT["source"]], "commercial_area")

    def test_cards_are_omitted_after_values_but_ids_stay_citable(self):
        ids, segments, packet = self.build(100)
        self.assertLessEqual(len(canonical_json(packet)), examiner.MAX_PACKET_CHARS)
        cards = [c[FACT["fact_id"]] for c in packet["facts"]]
        self.assertTrue(packet["omitted_fact_ids"])
        self.assertEqual(cards + packet["omitted_fact_ids"][::-1], [ids[-1], *ids[:-1]])
        self.assertTrue(all(c[FACT["value"]] is None for c in packet["facts"]))
        item = packet["candidates"][0]["score_items"][0]
        self.assertEqual(item[SCORE["item"]], "D1")
        self.assertEqual(item[SCORE["fact_ids"]], ids)

    def test_unobserved_or_uncitable_facts_are_not_offered(self):
        ids = [fact_id(i) for i in range(3)]
        rows = {
            ids[0]: row(ids[0], status="unknown"),
            ids[1]: row(ids[1], citable=0),
            ids[2]: row(ids[2]),
        }
        _, _, packet = self.build(3, rows)
        self.assertEqual([c[FACT["fact_id"]] for c in packet["facts"]], [ids[2]])
        item = packet["candidates"][0]["score_items"][0]
        self.assertEqual(item[SCORE["fact_ids"]], [ids[2]])

    def test_packet_periods_are_spelled_out(self):
        ids = [fact_id(0)]
        rows = {ids[0]: row(ids[0], period="20231~20234")}
        _, _, packet = self.build(1, rows)
        self.assertEqual(packet["facts"][0][FACT["period"]], "2023년 1분기~4분기")

    def test_long_value_is_left_for_reading(self):
        ids = [fact_id(0)]
        rows = {ids[0]: row(ids[0], value_json=json.dumps(list(range(400))))}
        _, _, packet = self.build(1, rows)
        self.assertIsNone(packet["facts"][0][FACT["value"]])
        self.assertIn("null", packet["note"])


class ExaminerChecksTests(unittest.TestCase):
    def build(self, items, rows, reasons):
        with (
            patch("app.agentic.examiner._score_items", return_value={"I201": items}),
            patch("app.agentic.examiner.fact_rows", return_value=rows),
            patch("app.agentic.examiner.encode", side_effect=lambda scope, value: value),
        ):
            return examiner.review_packet(None, draft(reasons))

    def test_persona_points_to_checks(self):
        self.assertIn("checks", examiner.PERSONA)
        self.assertIn("checks를 본 뒤에도 폐업률처럼 기간이 있는 문장", examiner.PERSONA)
        self.assertIn("이유·위험 칸을 가리지 말고", examiner.PERSONA)
        self.assertFalse(has_digit(examiner.PERSONA))

    def test_persona_limits_fact_reads(self):
        self.assertIn("서른두 개 이하", examiner.PERSONA)
        self.assertIn("나눠서", examiner.PERSONA)
        self.assertFalse(has_digit(examiner.PERSONA))

    def test_persona_separates_wrong_metric_from_missing_evidence(self):
        self.assertIn("슬롯이 있는데 엉뚱한 지표를 가리키면", examiner.PERSONA)
        self.assertIn("missing_evidence로 쓰지 마세요", examiner.PERSONA)
        self.assertFalse(has_digit(examiner.PERSONA))

    def test_persona_keeps_less_detailed_period_as_condition(self):
        self.assertIn("실제로 다를 때만 scope_mismatch", examiner.PERSONA)
        self.assertIn("덜 자세히 썼을 뿐 어긋나지 않으면 kind=action_condition", examiner.PERSONA)
        self.assertFalse(has_digit(examiner.PERSONA))

    def test_persona_names_hidden_digits_and_word_periods(self):
        hidden = ("연도·분기", "업종 코드", "문항 이름", "fact_id 별칭")
        for word in (*hidden, "최근 한 해", "가장 이른 해"):
            self.assertIn(word, examiner.PERSONA)
        self.assertFalse(has_digit(examiner.PERSONA))

    def test_checks_list_uncited_sentences(self):
        ids = [fact_id(0)]
        items = [{"item": "D1", "status": "observed", "grade": 3, "points": 7.5, "fact_ids": ids}]
        reasons = [
            {"type": "text", "text": "점포가 "},
            {"type": "fact", "fact_id": ids[0], "format": "count"},
            {"type": "text", "text": "개로 많습니다. 손님이 꾸준합니다."},
        ]
        packet = self.build(items, {ids[0]: row(ids[0])}, reasons)
        self.assertEqual(
            packet["checks"]["uncited"],
            [
                {"industry_code": "I201", "field": "reasons_segments", "sentence": 1},
                {"industry_code": "I201", "field": "risks_segments", "sentence": 0},
            ],
        )

    def test_checks_group_shared_sources(self):
        ids = [fact_id(i) for i in range(3)]
        rows = {
            ids[0]: row(ids[0], source="floating_population", metric="by_time"),
            ids[1]: row(ids[1], source="floating_population", metric="by_time"),
            ids[2]: row(ids[2]),
        }
        items = [
            {"item": "D1", "status": "observed", "grade": 3, "points": 7.5, "fact_ids": [ids[0]]},
            {"item": "D3", "status": "observed", "grade": 2, "points": 2.5, "fact_ids": [ids[1]]},
            {"item": "C1", "status": "observed", "grade": 2, "points": 7.5, "fact_ids": [ids[2]]},
        ]
        packet = self.build(items, rows, [{"type": "text", "text": "이유 문장"}])
        self.assertEqual(
            packet["checks"]["shared_sources"],
            [
                {
                    "industry_code": "I201",
                    "source": "floating_population",
                    "metric": "by_time",
                    "items": ["D1", "D3"],
                }
            ],
        )

    def test_checks_group_items_sharing_an_input(self):
        ids = [fact_id(i) for i in range(3)]
        rows = {
            ids[0]: row(ids[0], source="business_lifecycle", metric="close_rate_ratio"),
            ids[1]: row(ids[1], source="business_lifecycle", metric="close_trend_ratio"),
            ids[2]: row(ids[2], source="business_lifecycle", metric="turnover_ratio"),
        }
        items = [
            {"item": "S1", "status": "observed", "grade": 3, "points": 5.0, "fact_ids": [ids[0]]},
            {"item": "S3", "status": "observed", "grade": 3, "points": 5.0, "fact_ids": [ids[2]]},
            {"item": "S4", "status": "observed", "grade": 3, "points": 5.0, "fact_ids": [ids[1]]},
        ]
        packet = self.build(items, rows, [{"type": "text", "text": "이유 문장"}])
        self.assertEqual(
            packet["checks"]["shared_sources"],
            [
                {
                    "industry_code": "I201",
                    "source": "business_lifecycle",
                    "metric": "recent_year_close_rate",
                    "items": ["S1", "S4"],
                }
            ],
        )

    def test_sentences_keep_trailing_fact_and_punctuation_runs(self):
        fact = {"type": "fact", "fact_id": fact_id(0), "format": "count"}
        segments = [
            {"type": "text", "text": "폐업률이 높습니다."},
            fact,
            {"type": "text", "text": " 점포가 많습니다... 정말요?! 네."},
        ]
        self.assertEqual(
            examiner._sentences(segments),
            [
                ("폐업률이 높습니다.", True),
                ("점포가 많습니다...", False),
                ("정말요?!", False),
                ("네.", False),
            ],
        )
        leading = [
            {"type": "text", "text": "첫 문장입니다. "},
            fact,
            {"type": "text", "text": "가 둘째 문장입니다."},
        ]
        self.assertEqual(
            examiner._sentences(leading),
            [("첫 문장입니다.", False), ("가 둘째 문장입니다.", True)],
        )

    def test_packet_with_checks_stays_under_cap(self):
        ids = [fact_id(i) for i in range(100)]
        items = [{"item": "D1", "status": "observed", "grade": 3, "points": 7.5, "fact_ids": ids}]
        reasons = [{"type": "text", "text": "근거 없는 이유 문장입니다. " * 20}]
        packet = self.build(items, {fid: row(fid) for fid in ids}, reasons)
        self.assertLessEqual(len(canonical_json(packet)), examiner.MAX_PACKET_CHARS)
        self.assertEqual(len(packet["checks"]["uncited"]), 21)
        self.assertTrue(packet["omitted_fact_ids"])


class ExaminerPacketStoreTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.RuntimeTests.asyncSetUp
    asyncTearDown = fixtures.RuntimeTests.asyncTearDown

    async def test_packet_from_saved_draft_cites_only_observed_aliases(self):
        from app.agentic.runtime import DecisionLoop

        loop = await DecisionLoop.create(self.scope, self.site)
        await loop.submit_l(SubmitLInput(finish=True))
        await loop.submit_draft(SubmitDraftInput(phase="draft", report={}))
        codes = [c.industry_code for c in loop.done.top5[:5]]
        stored = examiner._score_items(self.scope, loop.done.score_snapshot_id, codes)
        self.assertEqual(set(stored), set(codes))
        for items in stored.values():
            self.assertEqual([i["item"] for i in items], list(examiner.ITEMS))
        with connect(self.scope.path) as db:
            observed, unknown = (
                db.execute(
                    "SELECT fact_id FROM facts WHERE industry_code=? AND status=? ORDER BY fact_id",
                    (codes[0], status),
                ).fetchone()[0]
                for status in ("observed", "unknown")
            )

        stored_items = examiner._score_items

        def linked(scope, score_snapshot_id, industry_codes):
            found = stored_items(scope, score_snapshot_id, industry_codes)
            found[industry_codes[0]][0]["fact_ids"] += [observed, unknown]
            return found

        with patch("app.agentic.examiner._score_items", side_effect=linked):
            packet = examiner.review_packet(self.scope, loop.done)
        self.assertEqual(packet["draft_id"], loop.done.report_id)
        self.assertEqual([c["industry_code"] for c in packet["candidates"]], codes)
        self.assertLessEqual(len(canonical_json(packet)), examiner.MAX_PACKET_CHARS)
        for candidate in packet["candidates"]:
            for key in examiner.SEGMENTS:
                self.assertIn(key, candidate)
        for candidate in packet["candidates"]:
            self.assertEqual(
                [i[SCORE["item"]] for i in candidate["score_items"]], list(examiner.ITEMS)
            )
        offered = packet["candidates"][0]["score_items"][0][SCORE["fact_ids"]]
        self.assertEqual(len(offered), 1)
        self.assertTrue(ALIAS.match(offered[0]))
        with connect(self.scope.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT fact_id FROM fact_aliases WHERE request_id=? AND alias=?",
                    (self.scope.request_id, offered[0]),
                ).fetchone()[0],
                observed,
            )
        card = next(f for f in packet["facts"] if f[FACT["fact_id"]] == offered[0])
        self.assertEqual(card[FACT["source"]], "industry_profile")
        self.assertIn(card[FACT["spatial_scope_ref"]], packet["spatial_scopes"])

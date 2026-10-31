"""심사위원 시험용 초안 생성 테스트."""

import random
import re
import unittest

from app.schemas import Site
from app.text import has_digit
from examiner_eval.generator import (
    BARE_PHRASES,
    COMPARE_PHRASES,
    PHRASES,
    build_cases,
    clean_draft,
    seeded_draft,
)
from examiner_eval.store import RequestContext

CS = "commercial_area"
FP = "floating_population"
BL = "business_lifecycle"

FULL = (
    (CS, "store_count"),
    (FP, "pattern_fit_index"),
    (BL, "recent_year_close_rate"),
    (BL, "oldest_year_close_rate"),
)


def make_ctx(request_id, spec, with_segments=False, ratios=None):
    facts = {}
    top5 = []
    for index, (code, metrics) in enumerate(spec.items()):
        for source, metric in metrics:
            facts[(code, source, metric)] = f"{request_id}-{code}-{metric}"
        top5.append(
            {
                "industry_code": code,
                "industry_name": f"업종{index}",
                "code_points": 50,
                "B": 1,
                "H": 2,
                "coverage": 0.5,
                "badge": "A",
                "L_status": "ok",
                "reasons_segments": [{"type": "text", "text": "기존 글"}] if with_segments else [],
                "risks_segments": [],
                "confirmation_conditions_segments": [],
                "fact_ids": [],
            }
        )
    return RequestContext(
        request_id=request_id,
        snapshot_id="snap",
        run_id="run",
        site=Site(
            input_address="주소",
            road_address="도로명 주소",
            latitude=37.0,
            longitude=127.0,
        ),
        stored_draft={
            "report_id": f"rep-{request_id}",
            "score_snapshot_id": "snap",
            "top5": top5,
            "summary_segments": [{"type": "text", "text": "요약"}],
            "limitations_segments": [],
        },
        facts=facts,
        ratios=ratios or {},
    )


def full_spec(count=5):
    return {f"CS{i}": FULL for i in range(count)}


def fact_slots(segments):
    return [s for s in segments if s["type"] == "fact"]


class GeneratorTest(unittest.TestCase):
    def test_clean_every_sentence_has_one_fact_and_no_digit(self):
        ctx = make_ctx("r1", full_spec())
        draft = clean_draft(ctx, random.Random(1))
        self.assertEqual(draft["report_id"], "rep-r1:clean")
        self.assertEqual(draft["score_snapshot_id"], "snap")
        for cand in draft["top5"]:
            self.assertEqual(cand["confirmation_conditions_segments"], [])
            self.assertEqual(len(fact_slots(cand["reasons_segments"])), 3)
            self.assertEqual(cand["risks_segments"], [])
            for field in ("reasons_segments", "risks_segments"):
                for seg in cand[field]:
                    if seg["type"] == "text":
                        self.assertFalse(has_digit(seg["text"]))
                    else:
                        self.assertEqual(seg["format"], "text")

    def test_clean_omits_sentences_without_facts(self):
        spec = {"CS0": ((CS, "store_count"),), "CS1": ()}
        draft = clean_draft(make_ctx("r1", spec), random.Random(1))
        self.assertEqual(len(fact_slots(draft["top5"][0]["reasons_segments"])), 1)
        self.assertEqual(draft["top5"][0]["risks_segments"], [])
        self.assertEqual(draft["top5"][1]["reasons_segments"], [])

    def test_close_rate_sentence_follows_seoul_comparison(self):
        with_ratio = (*FULL, (BL, "close_rate_ratio"))
        spec = {"CS0": with_ratio, "CS1": with_ratio, "CS2": FULL}
        ctx = make_ctx("r1", spec, ratios={"CS0": 1.4, "CS1": 0.6})
        draft = clean_draft(ctx, random.Random(1))
        high, low, missing = draft["top5"]

        def text(segments):
            return "".join(s.get("text", "") for s in segments)

        self.assertEqual(
            [s["fact_id"] for s in fact_slots(high["risks_segments"])],
            ["r1-CS0-recent_year_close_rate", "r1-CS0-close_rate_ratio"],
        )
        self.assertIn("높습니다", text(high["risks_segments"]))
        self.assertEqual(low["risks_segments"], [])
        self.assertEqual(
            [s["fact_id"] for s in fact_slots(low["reasons_segments"])][2:],
            ["r1-CS1-recent_year_close_rate", "r1-CS1-close_rate_ratio"],
        )
        self.assertIn("낮습니다", text(low["reasons_segments"]))
        self.assertEqual(missing["risks_segments"], [])
        self.assertEqual(len(fact_slots(missing["reasons_segments"])), 3)

    def test_seeded_three_errors_on_distinct_candidates(self):
        ctx = make_ctx("r1", full_spec())
        draft, seeds = seeded_draft(ctx, random.Random(2))
        self.assertEqual(draft["report_id"], "rep-r1:seeded")
        self.assertEqual(len(seeds), 3)
        self.assertEqual(sorted(s.kind for s in seeds), ["E1", "E2", "E3"])
        self.assertEqual(len({s.industry_code for s in seeds}), 3)

    def test_e1_removes_fact_slot(self):
        ctx = make_ctx("r1", full_spec())
        draft, seeds = seeded_draft(ctx, random.Random(2))
        seed = next(s for s in seeds if s.kind == "E1")
        self.assertEqual(seed.expected_kind, "missing_evidence")
        self.assertIsNone(seed.wrong_fact_id)
        cand = next(c for c in draft["top5"] if c["industry_code"] == seed.industry_code)
        ids = [s["fact_id"] for s in fact_slots(cand[seed.field])]
        self.assertNotIn(seed.support_fact_ids[0], ids)

    def test_e2_uses_other_source_and_falls_back(self):
        spec = {
            "CS0": ((CS, "store_count"), (BL, "recent_year_close_rate")),
            "CS1": ((CS, "store_count"), (FP, "pattern_fit_index")),
            "CS2": FULL,
            "CS3": ((CS, "store_count"),),
        }
        seen = set()
        for seed_value in range(30):
            draft, seeds = seeded_draft(make_ctx("r1", spec), random.Random(seed_value))
            for seed in seeds:
                if seed.kind != "E2":
                    continue
                self.assertNotEqual(seed.industry_code, "CS3")
                self.assertEqual(seed.expected_kind, "scope_mismatch")
                self.assertEqual(seed.field, "reasons_segments")
                cand = next(c for c in draft["top5"] if c["industry_code"] == seed.industry_code)
                ids = [s["fact_id"] for s in fact_slots(cand["reasons_segments"])]
                self.assertIn(seed.wrong_fact_id, ids)
                self.assertFalse(seed.wrong_fact_id.endswith("store_count"))
                seen.add(seed.industry_code)
                if seed.industry_code == "CS0":
                    self.assertTrue(seed.wrong_fact_id.endswith("recent_year_close_rate"))
                if seed.industry_code == "CS1":
                    self.assertTrue(seed.wrong_fact_id.endswith("pattern_fit_index"))
        self.assertIn("CS0", seen)
        self.assertIn("CS1", seen)

    def test_e2_skipped_when_nothing_to_swap(self):
        spec = {f"CS{i}": ((CS, "store_count"),) for i in range(5)}
        _, seeds = seeded_draft(make_ctx("r1", spec), random.Random(3))
        self.assertEqual([s for s in seeds if s.kind == "E2"], [])
        self.assertEqual([s.kind for s in seeds], ["E1"])

    def test_e3_cites_oldest_year_in_recent_sentence(self):
        ctx = make_ctx("r1", full_spec())
        draft, seeds = seeded_draft(ctx, random.Random(4))
        seed = next(s for s in seeds if s.kind == "E3")
        self.assertEqual(seed.field, "reasons_segments")
        self.assertEqual(seed.expected_kind, "scope_mismatch")
        self.assertTrue(seed.wrong_fact_id.endswith("oldest_year_close_rate"))
        self.assertTrue(seed.support_fact_ids[0].endswith("recent_year_close_rate"))
        cand = next(c for c in draft["top5"] if c["industry_code"] == seed.industry_code)
        ids = [s["fact_id"] for s in fact_slots(cand[seed.field])]
        self.assertIn(seed.wrong_fact_id, ids)
        self.assertNotIn(seed.support_fact_ids[0], ids)
        text = "".join(s.get("text", "") for s in cand[seed.field])
        self.assertIn("최근 한 해", text)

    def test_phrases_have_three_variants_without_digits(self):
        self.assertEqual(
            set(PHRASES),
            {
                "store_count",
                "pattern_fit_index",
                "recent_year_close_rate",
                "oldest_year_close_rate",
            },
        )
        for phrases in PHRASES.values():
            self.assertGreaterEqual(len(phrases), 3)
            for phrase in phrases:
                self.assertEqual(phrase.count("{fact}"), 1)
                self.assertFalse(has_digit(phrase))
        for phrase in PHRASES["recent_year_close_rate"]:
            self.assertIn("최근 한 해", phrase)
        for phrase in PHRASES["oldest_year_close_rate"]:
            self.assertIn("가장 이른 해", phrase)
        self.assertEqual(set(COMPARE_PHRASES), {"high", "low"})
        for key, word in (("high", "높습니다"), ("low", "낮습니다")):
            for phrase in COMPARE_PHRASES[key]:
                self.assertEqual(phrase.count("{fact}"), 2)
                self.assertIn("최근 한 해", phrase)
                self.assertIn(word, phrase)
                self.assertFalse(has_digit(phrase))

    def test_clean_phrases_state_values_without_judgment(self):
        judgments = ("위험", "주의", "부담", "수요", "형성된", "가늠", "해석")
        for metric, phrases in (*PHRASES.items(), *COMPARE_PHRASES.items()):
            for phrase in phrases:
                for word in judgments:
                    with self.subTest(metric=metric, word=word):
                        self.assertNotIn(word, phrase)

    def test_unique_assignment_always_places_three_seeds(self):
        spec = {
            "CSA": FULL,
            "CSB": (
                (CS, "store_count"),
                (BL, "recent_year_close_rate"),
                (BL, "oldest_year_close_rate"),
            ),
            "CSC": ((CS, "store_count"),),
        }
        for seed_value in range(30):
            _, seeds = seeded_draft(make_ctx("r1", spec), random.Random(seed_value))
            self.assertEqual(len(seeds), 3)
            self.assertEqual(len({s.industry_code for s in seeds}), 3)

    def test_e1_replaces_sentence_with_bare_phrase(self):
        metrics = ("store_count", "pattern_fit_index")
        for seed_value in range(10):
            ctx = make_ctx("r1", full_spec())
            draft, seeds = seeded_draft(ctx, random.Random(seed_value))
            seed = next(s for s in seeds if s.kind == "E1")
            cand = next(c for c in draft["top5"] if c["industry_code"] == seed.industry_code)
            slot_ids = [s["fact_id"] for s in fact_slots(cand[seed.field])]
            self.assertNotIn(seed.support_fact_ids[0], slot_ids)
            metric = next(m for m in metrics if seed.support_fact_ids[0].endswith(m))
            texts = [
                s["text"].strip()
                for s in cand[seed.field]
                if s["type"] == "text" and s["text"].strip() in BARE_PHRASES[metric]
            ]
            self.assertEqual(len(texts), 1)

    def test_bare_phrases_shape(self):
        self.assertEqual(
            set(BARE_PHRASES),
            {"store_count", "pattern_fit_index"},
        )
        for phrases in BARE_PHRASES.values():
            self.assertGreaterEqual(len(phrases), 3)
            for phrase in phrases:
                self.assertNotIn("{fact}", phrase)
                self.assertFalse(has_digit(phrase))

    def test_sentences_are_separated_by_space(self):
        for seed_value in range(10):
            ctx = make_ctx("r1", full_spec())
            drafts = [
                clean_draft(ctx, random.Random(seed_value)),
                seeded_draft(ctx, random.Random(seed_value))[0],
            ]
            for draft in drafts:
                for cand in draft["top5"]:
                    for field in ("reasons_segments", "risks_segments"):
                        text = "".join(s.get("text", "|") for s in cand[field])
                        self.assertIsNone(re.search(r"\.\S", text))

    def test_build_cases_rejects_duplicate_request_ids(self):
        with self.assertRaises(ValueError):
            build_cases([make_ctx("r1", full_spec()), make_ctx("r1", full_spec())])

    def test_deterministic_regardless_of_order(self):
        a = make_ctx("ra", full_spec())
        b = make_ctx("rb", full_spec())
        by_id = {c.case_id: c for c in build_cases([b, a])}
        for case in build_cases([a, b]):
            self.assertEqual(case, by_id[case.case_id])

    def test_build_cases_counts(self):
        contexts = [make_ctx(f"r{i:02d}", full_spec(), with_segments=i < 5) for i in range(10)]
        cases = build_cases(contexts)
        self.assertEqual(len(cases), 25)
        counts = {s: sum(1 for c in cases if c.source == s) for s in ("clean", "seeded", "real")}
        self.assertEqual(counts, {"clean": 10, "seeded": 10, "real": 5})
        splits = {}
        for case in cases:
            splits.setdefault(case.request_id, set()).add(case.split)
        self.assertTrue(all(len(v) == 1 for v in splits.values()))
        self.assertEqual(sum(1 for v in splits.values() if "tune" in v), 5)
        self.assertEqual(sum(1 for v in splits.values() if "test" in v), 5)
        for case in cases:
            self.assertTrue(case.case_id.startswith(case.request_id + ":"))
            if case.source != "seeded":
                self.assertEqual(case.seeds, ())


if __name__ == "__main__":
    unittest.main()

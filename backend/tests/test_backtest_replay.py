import asyncio
import unittest
from collections import Counter

import pandas as pd
from test_backtest_outcome import row

from app.agents import decision
from app.agents.business_lifecycle import preprocess
from app.agents.business_lifecycle.area_resolver import resolve_area
from app.agents.data_models import parse_data
from app.industries.catalog import SEOUL_TO_INDUSTRY
from app.schemas import DecisionRequest
from backtest.data import quarters_until
from backtest.mock import backtest_generate
from backtest.replay import (
    UNCOMPUTED,
    AreaInfo,
    commercial_substitute,
    load_areas,
    replay_store_rows,
    sample_areas,
    site_for,
)

SEOUL_CODES = {}
for seoul_code, industry_code in sorted(SEOUL_TO_INDUSTRY.items()):
    SEOUL_CODES.setdefault(industry_code, seoul_code)
THREE = list(SEOUL_CODES.items())[:3]


def synthetic():
    counts = {"A1": (10, 3, 7), "B1": (20, 20, 10)}
    rows = []
    for area, stores in counts.items():
        for (_, seoul_code), count in zip(THREE, stores, strict=True):
            rows.append(row("20234", area, seoul_code, count, 0))
            rows.append(row("20241", area, seoul_code, count + 1, 0))
    return pd.DataFrame(rows)


class SampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.areas = load_areas()
        cls.sample = sample_areas(cls.areas)

    def test_sample_counts_per_kind(self):
        counts = Counter(info.kind for info in self.sample)
        self.assertEqual(counts, {"골목상권": 26, "발달상권": 6, "전통시장": 7, "관광특구": 1})
        self.assertEqual(len(self.sample), 40)

    def test_same_seed_gives_same_sample(self):
        self.assertEqual(self.sample, sample_areas(self.areas))

    def test_site_resolves_back_to_same_area(self):
        matched = [i for i in self.sample if resolve_area(site_for(i)).area_code == i.code]
        self.assertGreaterEqual(len(matched), 38)

    def test_site_address_is_the_area_name_only(self):
        for info in self.sample:
            site = site_for(info)
            self.assertEqual(site.input_address, info.name)
            self.assertNotIn("백테스트", site.input_address)


class ReplayTests(unittest.TestCase):
    def test_store_rows_stop_at_base_quarter(self):
        data = synthetic()
        with replay_store_rows(data, "20234"):
            rows = asyncio.run(preprocess.fetch_recent_store_data("A1", "20241", 12))
        self.assertTrue(rows)
        self.assertTrue(all(r["stdr_yyqu_cd"] <= "20234" for r in rows))

    def test_unknown_area_is_empty(self):
        with replay_store_rows(synthetic(), "20234"):
            rows = asyncio.run(preprocess.fetch_recent_store_data("X", "20241", 12))
        self.assertEqual(rows, [])
        self.assertIn("20234", quarters_until("20234", 2))


class SubstituteTests(unittest.TestCase):
    def setUp(self):
        info = AreaInfo("A1", "가상상권", "골목상권", "종로구", 197093.0, 453418.0, 1_000_000.0)
        self.result = commercial_substitute(synthetic(), info, "20234", "req-1")
        self.parsed = parse_data("commercial_area", self.result.data)
        self.middle = {m.code: m for m in self.parsed.by_middle}

    def test_passes_schema(self):
        self.assertEqual(self.result.agent_id, "commercial_area")
        self.assertEqual(self.parsed.store_total, 20)

    def test_lq_is_area_share_over_seoul_share(self):
        code = THREE[0][0]
        self.assertAlmostEqual(self.middle[code].lq, round((10 / 20) / (30 / 70), 4))

    def test_few_stores_are_not_citable_for_lq(self):
        small = self.middle[THREE[1][0]]
        large = self.middle[THREE[0][0]]
        self.assertIs(small.citable["lq"], False)
        self.assertNotIn("lq", large.citable)

    def test_by_middle_is_ordered_by_count_like_the_live_agent(self):
        codes = [m.code for m in self.parsed.by_middle]
        self.assertEqual(codes, [THREE[0][0], THREE[2][0], THREE[1][0]])
        counts = [(-m.count, m.code) for m in self.parsed.by_middle]
        self.assertEqual(counts, sorted(counts))

    def test_uncomputed_metrics_are_never_citable(self):
        for m in self.parsed.by_middle:
            for name in UNCOMPUTED:
                self.assertIs(m.citable[name], False)


class MockDecisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_runs_with_substitute_data(self):
        info = AreaInfo("A1", "가상상권", "골목상권", "종로구", 197093.0, 453418.0, 1_000_000.0)
        analysis = commercial_substitute(synthetic(), info, "20234", "req-1")
        request = DecisionRequest(request_id="req-1", address="서울 종로구", analyses=[analysis])
        result = await decision.analyze(request, generate=backtest_generate)
        self.assertEqual(len(result.recommendations), 1)
        self.assertEqual(len(result.not_recommended), 1)
        for item in (*result.recommendations, *result.not_recommended):
            for reason in item.reasons:
                self.assertNotIn("{", reason)

    async def test_not_recommended_is_an_industry_that_has_stores(self):
        info = AreaInfo("A1", "가상상권", "골목상권", "종로구", 197093.0, 453418.0, 1_000_000.0)
        analysis = commercial_substitute(synthetic(), info, "20234", "req-1")
        request = DecisionRequest(request_id="req-1", address="서울 종로구", analyses=[analysis])
        result = await decision.analyze(request, generate=backtest_generate)
        self.assertEqual(result.not_recommended[0].category.code, THREE[2][0])
        self.assertNotEqual(result.recommendations[0].category.code, THREE[2][0])


if __name__ == "__main__":
    unittest.main()

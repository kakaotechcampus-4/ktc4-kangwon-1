"""고정 후보 재현·원문 상태 보존·L 재계산·운영 참고 분포의 경계를 확인합니다."""

import asyncio
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.ai.read_tools import get_scorecard
from app.application.facts import register_fact
from app.application.report import load_base, recompute_l_scores
from app.application.snapshot import persist_snapshot_scores
from app.domain import code90
from app.domain.contracts import GetScorecardInput, LRecord, NewFactor, ScoreItem
from app.domain.geo import to_epsg5181
from app.domain.report import code90_uses_metric, complete_l_records
from app.domain.schemas import AnalysisTask, Site
from app.domain.scoring import profiles, rank_candidates, result, summarize
from app.domain.stats import calculate_rate
from app.infrastructure.market_data.local.score_reference import (
    attach_reference,
    city_reference,
    inverse_center,
)
from app.infrastructure.persistence.connection import connect, initialize
from app.infrastructure.persistence.raw_capture import capture_scope
from app.infrastructure.persistence.repository import create_request


class Code90RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(
            (Path(__file__).parent / "fixtures/code90_reference.json").read_text(encoding="utf-8")
        )
        cls.profiles = profiles()

    def calculate(self, fixture):
        reference = sorted(
            int(value) for value, n in fixture["reference_histogram"].items() for _ in range(n)
        )
        return code90.calculate(
            fixture["items"],
            self.profiles[fixture["code"]],
            fixture["code"],
            fixture["data"],
            city=fixture["city"],
            quarter="20252",
            reference=reference,
            components=fixture["components"],
            facility_floors=fixture["facility_floors"],
        )

    def test_frozen_contributions_and_source_fields_are_reproduced(self):
        for name, fixture in self.cases.items():
            with self.subTest(name=name):
                before = deepcopy(fixture)
                actual = self.calculate(fixture)
                for item in code90.WEIGHTS:
                    self.assertAlmostEqual(
                        actual[item]["scoring"]["points"],
                        fixture["expected_points"][item],
                        places=10,
                    )
                    self.assertEqual(
                        {k: v for k, v in actual[item].items() if k != "scoring"},
                        fixture["items"][item],
                    )
                self.assertAlmostEqual(
                    code90.summary(actual)["code_points"], fixture["expected_normalized"], places=10
                )
                self.assertEqual(fixture, before)

    def test_incomplete_partial_and_filled_rows_receive_no_S2_estimate(self):
        for change in ("partial", "filled", "missing", "unsupported"):
            with self.subTest(change=change):
                fixture = deepcopy(self.cases["complete_full_period_S2_half"])
                if change == "partial":
                    fixture["data"]["runtime_partial_sources"] = ["business_lifecycle"]
                elif change == "filled":
                    fixture["data"]["lifecycle_quarterly"]["industries"][0][
                        "zero_filled_sources"
                    ] = 1
                elif change == "missing":
                    fixture["data"]["lifecycle_quarterly"]["industries"][0]["closed_counts"].pop()
                else:
                    fixture["city"] = None
                actual = self.calculate(fixture)["S2"]
                self.assertEqual(
                    (actual["status"], actual["grade"], actual["points"]), ("unknown", None, None)
                )
                self.assertEqual(actual["scoring"]["points"], 0)

    def test_json_key_order_does_not_change_the_score(self):
        for fixture in self.cases.values():
            items = self.calculate(fixture)
            restored = json.loads(json.dumps(items, sort_keys=True))
            reversed_items = dict(reversed(list(items.items())))
            self.assertEqual(code90.summary(items), code90.summary(restored))
            self.assertEqual(code90.summary(items), code90.summary(reversed_items))

    def test_saved_rates_on_rounding_boundary_are_accepted(self):
        fixture = deepcopy(self.cases["complete_full_period_S2_half"])
        quarterly = fixture["data"]["lifecycle_quarterly"]["industries"][0]
        quarterly["store_counts"] = [40] * 12
        quarterly["opened_counts"] = [0] * 12
        quarterly["closed_counts"] = [0] * 8 + [5, 6, 6, 6]
        stores, opened, closed = (
            quarterly[k] for k in ("store_counts", "opened_counts", "closed_counts")
        )
        fixture["data"]["business_lifecycle"]["industries"][0]["metrics"] = {
            "avg_store_count": sum(stores) / 12,
            "recent_year_close_rate": calculate_rate(sum(closed[-4:]), sum(stores[-4:])),
            "oldest_year_close_rate": calculate_rate(sum(closed[:4]), sum(stores[:4])),
            "net_change_rate": calculate_rate(sum(opened) - sum(closed), sum(stores)),
            "turnover_rate": calculate_rate(sum(opened) + sum(closed), sum(stores)),
        }
        self.assertNotEqual(round(100 * 23 / 160, 2), calculate_rate(23, 160))
        self.calculate(fixture)

    def test_conflicting_raw_counts_are_rejected(self):
        fixture = deepcopy(self.cases["complete_full_period_S2_half"])
        fixture["data"]["lifecycle_quarterly"]["industries"][0]["store_counts"][0] += 100
        with self.assertRaises(ValueError):
            self.calculate(fixture)

    def test_observed_facilities_replace_unknown_policy_points(self):
        fixture = deepcopy(self.cases["medical_subset_floor"])
        fixture["components"] = {
            "HP8": {"status": "observed", "points": 7.5},
            "SC4": {"status": "observed", "points": 2.5},
        }
        fixture["items"]["C4"] = result("C4", 1, value={"HP8": 100, "SC4": 600})
        actual = self.calculate(fixture)["C4"]
        self.assertEqual(actual["scoring"]["points"], 5)
        self.assertFalse(actual["scoring"]["estimated"])

    def test_L_is_added_after_code90_normalization(self):
        fixture = self.cases["complete_full_period_S2_half"]
        items = self.calculate(fixture)
        before = summarize(fixture["code"], items, "해당 없음")
        items["L"] = result("L", 4)
        after = summarize(fixture["code"], items, "해당 없음")
        self.assertEqual(before["code90"]["code_points"], after["code90"]["code_points"])
        self.assertEqual(after["code90"]["ranking_points"], before["code90"]["ranking_points"] + 10)
        self.assertEqual(after["upper"] - before["upper"], 0)

    def test_rank_uses_selected_score_and_preserves_exclusions(self):
        rows = [
            {
                "code": code,
                "lower": lower,
                "coverage": 0.8,
                "regulation": regulation,
                "code90": {"ranking_points": score},
            }
            for code, lower, score, regulation in [
                ("G204", 80, 40, "해당 없음"),
                ("I201", 40, 80, "해당 없음"),
                ("I211", 90, 90, "금지"),
            ]
        ]
        self.assertEqual([r["code"] for r in rank_candidates(rows)], ["I201", "G204"])

    def test_unknown_score_contract_does_not_turn_estimate_into_observation(self):
        item = self.calculate(self.cases["complete_full_period_S2_half"])["S2"]
        value = ScoreItem(
            item="S2",
            status="unknown",
            grade=None,
            points=None,
            fact_ids=[],
            scoring=item["scoring"],
        )
        self.assertGreater(value.scoring.points, 0)
        with self.assertRaises(ValidationError):
            ScoreItem(
                item="S2",
                status="observed",
                grade=None,
                points=None,
                fact_ids=[],
                scoring=item["scoring"],
            )

    def test_actual_customer_change_requires_same_population_and_area_set(self):
        profile = {"target_population": "직장", "target_age_bands": "30"}
        data = {
            "floating_population": {"period_code": "20251"},
            "score90_customer_population": {
                "직장": {"20241": {"a": {"30": 100}}, "20251": {"a": {"30": 100}}}
            },
        }
        self.assertEqual(code90.customer_change(profile, data), 0)
        data["score90_customer_population"]["직장"]["20251"]["b"] = {"30": 100}
        self.assertIsNone(code90.customer_change(profile, data))
        data["score90_customer_population"]["유동"] = data["score90_customer_population"].pop(
            "직장"
        )
        self.assertIsNone(code90.customer_change(profile, data))

    def test_inverse_projection_uses_existing_coordinate_definition(self):
        for lat, lon in ((37.5, 127), (37.7, 126.9), (37.55, 127.1)):
            actual = inverse_center(*to_epsg5181(lat, lon))
            self.assertAlmostEqual(actual[0], lat, places=6)
            self.assertAlmostEqual(actual[1], lon, places=6)

    def test_LQ_used_by_new_C1_is_not_a_new_L_factor(self):
        fixture = self.cases["city_count_rank_and_LQ"]
        row = {"items": self.calculate(fixture)}
        self.assertTrue(code90_uses_metric(row, "lq"))
        self.assertFalse(code90_uses_metric(row, "place_name"))
        self.assertFalse(code90_uses_metric({"items": fixture["items"]}, "lq"))

    def test_reference_pins_versions_excludes_nearby_and_refuses_wrong_quarter(self):
        adapter = SimpleNamespace(
            path=Path("market.sqlite3"),
            versions=[
                {"source": "stores", "version_id": "s", "file_hash": "hs", "quarter": "20262"},
                {"source": "areas", "version_id": "a", "file_hash": "ha"},
            ],
        )
        task = SimpleNamespace(site=SimpleNamespace(latitude=37.5, longitude=127))
        data = {
            "floating_population": {"period_code": "20262"},
            "area_selection": {"area_code": "same"},
        }
        samples = [
            {"area": code, "latitude": lat, "longitude": 127, "counts": {}}
            for code, lat in (("same", 37.7), ("near", 37.50001), ("far", 37.7))
        ]
        with patch(
            "app.infrastructure.market_data.local.score_reference.city_reference",
            return_value=(samples, []),
        ) as build:
            attach_reference(adapter, task, data)
            self.assertEqual([r["area"] for r in data["score90_reference"]["samples"]], ["far"])
            self.assertEqual(build.call_args.args[1:], ("s", "a", "hs", "ha"))
            data = {"floating_population": {"period_code": "20252"}}
            attach_reference(adapter, task, data)
            self.assertNotIn("score90_reference", data)
            self.assertEqual(build.call_count, 1)

    def test_reference_cache_is_invalidated_by_source_version_and_corruption(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch("app.infrastructure.market_data.local.score_reference.CACHE_DIR", Path(folder)),
            patch(
                "app.infrastructure.market_data.local.score_reference._build_reference",
                return_value=([{"area": "a", "counts": {}}], []),
            ) as build,
        ):
            city_reference.cache_clear()
            first = city_reference("path", "s", "a", "hash", "areas")
            city_reference.cache_clear()
            second = city_reference("path", "s", "a", "hash", "areas")
            self.assertEqual(json.dumps(first), json.dumps(second))
            self.assertEqual(build.call_count, 1)
            target = next(Path(folder).rglob("*.json"))
            target.write_text("broken", encoding="utf-8")
            city_reference.cache_clear()
            city_reference("path", "s", "a", "hash", "areas")
            city_reference("path", "changed", "a", "hash", "areas")
            self.assertEqual(build.call_count, 3)
            city_reference.cache_clear()


class Code90PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_saved_detail_and_L_recalculation_preserve_code90(self):
        with tempfile.TemporaryDirectory() as folder:
            path = initialize(Path(folder) / "requests.sqlite3")
            create_request("code90", "서울 테스트", db_path=path)
            task = AnalysisTask(
                request_id="code90",
                site=Site(
                    input_address="서울 테스트",
                    road_address="서울 테스트",
                    latitude=37.5,
                    longitude=127,
                ),
                radius_m=500,
            )
            async with capture_scope("code90", path) as scope:
                await persist_snapshot_scores(task)
                query = GetScorecardInput(industry_codes=["M103"], mode="detail", limit=1)
                before = (await get_scorecard(scope, query)).scorecards[0]
                c1 = next(item for item in before.items if item.item == "C1")
                self.assertEqual(c1.points, 7.5)
                self.assertEqual(c1.scoring.weight, 30)
                base_id, rows = await asyncio.to_thread(load_base, scope)
                records = complete_l_records([], base_id, rows)
                original = next(r for r in records if r.industry_code == "M103")
                await scope.record(
                    source="map",
                    source_type="api",
                    args={},
                    page="offline",
                    status=200,
                    payload={"rows": [{"name": "새 확인 점포"}]},
                )
                with connect(path) as db:
                    ref = db.execute(
                        "SELECT raw_row_id FROM raw_response_rows JOIN raw_responses "
                        "USING(response_id) WHERE source='map'"
                    ).fetchone()[0]
                fact = await asyncio.to_thread(
                    register_fact,
                    scope,
                    industry_code="M103",
                    source="map",
                    metric="place_name",
                    value="새 확인 점포",
                    unit="상호",
                    status="observed",
                    row_ids=[ref],
                )
                replacement = LRecord(
                    industry_code="M103",
                    selection=original.selection,
                    review_state="reviewed",
                    status="observed",
                    grade=2,
                    checked_questions=["새 조건 확인"],
                    tool_call_ids=["offline"],
                    new_factors=[
                        NewFactor(direction="neutral", claim="새 점포 관측", fact_ids=[fact])
                    ],
                )
                records = [replacement if r.industry_code == "M103" else r for r in records]
                await asyncio.to_thread(recompute_l_scores, scope, records, base_id, rows)
                after = (await get_scorecard(scope, query)).scorecards[0]
                self.assertEqual(after.code_points, before.code_points)
                self.assertEqual(
                    after.calculation.ranking_points, before.calculation.ranking_points + 5
                )
                self.assertEqual(after.L_points, 5)
                self.assertEqual(
                    next(item for item in after.items if item.item == "C1").scoring, c1.scoring
                )

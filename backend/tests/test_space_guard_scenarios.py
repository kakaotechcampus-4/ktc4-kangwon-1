"""멘토 리뷰의 네 가지 비추천 경우를 서비스 경로와 채점 단계에서 끝까지 확인합니다."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agentic import scoring
from app.agentic.scoring import evaluate, profiles, result
from app.agentic.space_rules import load_requirements
from app.agents.commercial_area.baseline import SEOUL_INDUSTRY_DENSITY_PERCENTILES
from app.agents.floating_population.baseline import DAILY_TOTAL_PERCENTILES
from app.main import create_app
from app.schemas import DecisionResult
from app.services.settings import ExecutionSettings


def codes_with(level, key):
    return {code for code, row in load_requirements().items() if row[key] == level}


REAL_SCORE_ITEM = scoring.score_item


def raised(grades):
    def score_item(item, profile, code, *args, **kwargs):
        if item == "C1" and code in grades:
            return result("C1", grades[code], reason="시험용 고정 등급", agglomeration="무관")
        return REAL_SCORE_ITEM(item, profile, code, *args, **kwargs)

    return patch("app.agentic.scoring.score_item", side_effect=score_item)


class ServicePathScenarioTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch(
                "httpx.AsyncHTTPTransport.handle_async_request",
                side_effect=AssertionError("외부 연결 금지"),
            )
        )
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.path = Path(self.directory) / "scenario.sqlite3"
        self.client = self.enterContext(
            TestClient(create_app(settings=ExecutionSettings(db_path=self.path), load_env=False))
        )

    def run_analysis(self, **fields):
        response = self.client.post(
            "/api/v1/analyses?mock=true", json={"address": "시험", **fields}
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def stored_top5(self, request_id):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT top5_json FROM score_snapshots WHERE request_id=? "
                "AND L_review_state='reviewed' ORDER BY created_at DESC LIMIT 1",
                (request_id,),
            ).fetchone()
        return json.loads(row[0])

    def submitted_top5(self, request_id):
        with closing(sqlite3.connect(self.path)) as db:
            replies = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT reply_json FROM tool_calls WHERE request_id=? AND tool_name='submit_l' "
                    "ORDER BY created_at",
                    (request_id,),
                )
            ]
        closed = [r["data"] for r in replies if r["status"] == "ok" and r["data"]["closed"]]
        return [s["industry_code"] for s in closed[-1]["scorecard"]["summaries"]]

    def codes(self, result):
        return [c.industry_code for c in result.top5]

    def test_fourth_floor_excludes_ground_required(self):
        self.enterContext(raised({"S203": 4}))
        plain = DecisionResult.model_validate(self.run_analysis())
        self.assertEqual(self.codes(plain)[0], "S203")
        result = DecisionResult.model_validate(self.run_analysis(floor="4층"))
        ground_required = codes_with("ground_required", "floor_preference")
        self.assertEqual(ground_required, {"S203", "S204"})
        self.assertFalse(set(self.codes(result)) & ground_required)
        excluded = {c.industry_code: c for c in result.condition_excluded}
        self.assertEqual(set(excluded), ground_required)
        self.assertEqual(excluded["S203"].reasons, ["1층이 아님"])
        self.assertEqual(excluded["S203"].score_rank, 1)

    def test_upper_floor_lowers_ground_preferred_by_floor(self):
        self.enterContext(raised({"G202": 4}))
        plain = DecisionResult.model_validate(self.run_analysis())
        self.assertEqual(self.codes(plain)[0], "G202")
        second = DecisionResult.model_validate(self.run_analysis(floor="2층"))
        self.assertEqual(self.codes(second)[0], "G202")
        self.assertEqual(second.top5[0].B, plain.top5[0].B)
        fourth = DecisionResult.model_validate(self.run_analysis(floor="4층"))
        self.assertNotEqual(self.codes(fourth)[0], "G202")
        self.assertNotIn("G202", {c.industry_code for c in fourth.condition_excluded})

    def test_ventilation_unavailable_excludes_required(self):
        self.enterContext(raised({"I201": 4}))
        plain = DecisionResult.model_validate(self.run_analysis())
        self.assertEqual(self.codes(plain)[0], "I201")
        result = DecisionResult.model_validate(
            self.run_analysis(facilities={"ventilation": "unavailable"})
        )
        required = codes_with("required", "ventilation_needed")
        self.assertEqual(len(required), 8)
        self.assertFalse(set(self.codes(result)) & required)
        excluded = {c.industry_code: c for c in result.condition_excluded}
        self.assertEqual(set(excluded), required)
        self.assertTrue(all(c.reasons == ["배기(덕트) 설치 불가"] for c in excluded.values()))
        self.assertEqual(excluded["I201"].score_rank, 1)

    def test_resume_keeps_space_guard(self):
        self.enterContext(raised({"I201": 4, "S203": 4}))
        fields = {"floor": "4층", "facilities": {"ventilation": "unavailable"}}
        straight = DecisionResult.model_validate(self.run_analysis(**fields))
        waiting = self.run_analysis(**fields, allow_questions=True)
        self.assertEqual(waiting["status"], "waiting_for_input")
        response = self.client.post(
            f"/api/v1/analyses/{waiting['request_id']}/answers?mock=true",
            json={
                "question_session_id": waiting["question_session_id"],
                "answers": {q["field"]: "1층" for q in waiting["questions"]},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        resumed = DecisionResult.model_validate(response.json())
        self.assertEqual(self.codes(resumed), self.codes(straight))
        excluded = {c.industry_code for c in resumed.condition_excluded}
        self.assertTrue({"S203", "S204"} <= excluded)
        self.assertTrue(codes_with("required", "ventilation_needed") <= excluded)

    def test_decision_top5_matches_final_with_exclusion(self):
        self.enterContext(raised({"I201": 4}))
        payload = self.run_analysis(floor="4층", facilities={"ventilation": "unavailable"})
        result = DecisionResult.model_validate(payload)
        self.assertNotIn("I201", self.codes(result))
        self.assertEqual(self.codes(result), self.stored_top5(result.request_id))
        self.assertEqual(self.codes(result), self.submitted_top5(result.request_id))
        self.assertTrue(result.condition_excluded)


class ScoringScenarioTests(unittest.TestCase):
    def test_absolute_school_zone_excludes_lodging_bar_amusement(self):
        report = evaluate(
            {
                "address": "시험",
                "education_zones": {"status": "ok", "zones": [{"name": "절대보호구역"}]},
            }
        )
        banned = {"I101", "I102", "I211", "R104"}
        rows = {r["code"]: r for r in report["rows"]}
        self.assertTrue(all(rows[c]["regulation"] == "금지" for c in banned))
        self.assertFalse({r["code"] for r in report["top5"]} & banned)

    def test_relative_school_zone_keeps_bar_and_amusement_conditional(self):
        report = evaluate(
            {
                "address": "시험",
                "education_zones": {"status": "ok", "zones": [{"name": "상대보호구역"}]},
            }
        )
        rows = {r["code"]: r for r in report["rows"]}
        self.assertEqual(rows["I211"]["regulation"], "조건부")
        self.assertEqual(rows["R104"]["regulation"], "조건부")

    def test_extreme_density_nearby_type_not_first(self):
        nearby = [code for code, p in profiles().items() if p["agglomeration"] == "근처형"]
        self.assertIn("G204", nearby)
        by_middle = [
            {"code": code, "density_per_km2": SEOUL_INDUSTRY_DENSITY_PERCENTILES[code][50]}
            for code in nearby
            if code in SEOUL_INDUSTRY_DENSITY_PERCENTILES
        ]
        crowded = SEOUL_INDUSTRY_DENSITY_PERCENTILES["G204"][95] * 3
        by_middle = [
            {**m, "density_per_km2": crowded} if m["code"] == "G204" else m for m in by_middle
        ]
        report = evaluate(
            {
                "address": "시험",
                "commercial_area": {"radius_m": 500, "by_middle": by_middle},
                "commercial_collection_complete": True,
                "floating_population": {
                    "benchmark": {"mean_daily_per_trade_area": DAILY_TOTAL_PERCENTILES[50]}
                },
            }
        )
        rows = {r["code"]: r for r in report["rows"]}
        self.assertEqual(rows["G204"]["items"]["C1"]["status"], "observed")
        self.assertNotEqual(report["top5"][0]["code"], "G204")

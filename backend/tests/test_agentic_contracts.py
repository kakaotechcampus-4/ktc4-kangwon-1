"""새 계약 경계는 네트워크·모델 없이 검증합니다."""

import json
import re
import unittest
from pathlib import Path

from pydantic import ValidationError

from app import schemas as s
from app.agentic import contracts as c
from app.industries.catalog import INDUSTRIES

FACT = "f_12345678-1234-4234-8234-123456789abc"


class AgenticContractsTests(unittest.TestCase):
    def test_input_roundtrips(self):
        examples = {
            c.GetScorecardInput: {},
            c.GetFactsInput: {"fact_ids": [FACT]},
            c.QueryRawInput: {"sql": "SELECT raw_row_id FROM v_raw_stores", "max_rows": 50},
            c.MapSearchInput: {"facility_code": "SC4", "radius_m": 500},
            c.CheckRegulationInput: {},
            c.AskAdvisorInput: {"question": "상충 해석", "fact_ids": [FACT]},
            c.AskUserInput: {
                "questions": [{"field": "floor", "question": "몇 층인가요?", "reason": "동선 확인"}]
            },
            c.SubmitDraftInput: {
                "phase": "draft",
                "report": {"summary_segments": [{"type": "text", "text": "초안"}]},
            },
            c.SubmitReviewInput: {"draft_id": "draft", "verdict": "agree", "issues": []},
        }
        for model, value in examples.items():
            with self.subTest(model=model.__name__):
                instance = model.model_validate(value)
                self.assertEqual(instance, model.model_validate_json(instance.model_dump_json()))
                with self.assertRaises(ValidationError):
                    model.model_validate(value | {"unexpected": True})

    def test_bounds(self):
        examples = [
            (
                c.AskUserInput,
                {"questions": [{"field": "floor", "question": "가" * 201, "reason": "근거"}]},
            ),
            (c.GetFactsInput, {"fact_ids": [FACT] * 33}),
            (c.GetScorecardInput, {"mode": "detail", "limit": 6}),
            (c.QueryRawInput, {"sql": "SELECT 1", "max_rows": 51}),
            (c.QueryRawInput, {"sql": "x" * 4001}),
            (c.MapSearchInput, {"industry_code": "I201", "radius_m": 501}),
            (c.AskAdvisorInput, {"question": "x" * 801, "fact_ids": [FACT]}),
        ]
        for model, value in examples:
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model.model_validate(value)

    def test_exclusive_modes(self):
        c.GetFactsInput(industry_code="I201", source="commercial_area", metrics=["density_per_km2"])
        for value in (
            {},
            {"fact_ids": [FACT], "source": "commercial_area", "metrics": ["density_per_km2"]},
            {"industry_code": "I201"},
            {"source": "commercial_area", "metrics": ["density_per_km2"]},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                c.GetFactsInput.model_validate(value)
        for value in (
            {"radius_m": 500},
            {"radius_m": 500, "industry_code": "I201", "facility_code": "SC4"},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                c.MapSearchInput.model_validate(value)

    def test_fact_id_and_catalog(self):
        s.Evidence(fact_id=FACT)
        for value in ("f_nope", FACT + "x", FACT[2:]):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                s.Evidence(fact_id=value)
        schema = c.MapSearchInput.model_json_schema()
        self.assertEqual(
            set(schema["properties"]["industry_code"]["anyOf"][0]["enum"]), set(INDUSTRIES)
        )
        with self.assertRaises(ValidationError):
            c.MapSearchInput(industry_code="G206", radius_m=500)

    def test_report_has_no_scores(self):
        for key in (
            "score",
            "code_points",
            "L_points",
            "badge",
            "value",
            "number",
            "review_resolutions",
        ):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                c.ReportProposal.model_validate({key: 1})
        candidate = {
            "industry_code": "I201",
            "reasons_segments": [{"type": "fact", "fact_id": FACT, "format": "count"}],
        }
        c.Candidate.model_validate(candidate)
        with self.assertRaises(ValidationError):
            c.Candidate.model_validate(candidate | {"points": 90})

    def test_tool_schemas(self):
        definitions = c.tool_definitions()
        self.assertEqual(len(definitions), 9)
        self.assertEqual({d["function"]["name"] for d in definitions}, set(c.TOOL_INPUTS))
        forbidden = {"$defs", "$ref", "title", "default", "discriminator", "oneOf"}

        def check(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)

        for definition in definitions:
            json.dumps(definition, ensure_ascii=False, allow_nan=False)
            self.assertEqual(definition["type"], "function")
            self.assertFalse(definition["function"]["strict"])
            check(definition["function"]["parameters"])
        schemas = {d["function"]["name"]: d["function"]["parameters"] for d in definitions}
        self.assertEqual(schemas["query_raw"]["properties"]["max_rows"]["maximum"], 50)

    def test_fact_and_score_status(self):
        fact = {
            "fact_id": FACT,
            "source": "commercial_area",
            "metric": "density_per_km2",
            "value": 10.0,
            "unit": "개/km²",
            "period": "2026Q2",
            "spatial_scope": {"radius_m": 500},
            "industry_code": "I201",
            "status": "observed",
            "citable": True,
            "calc_version": "1",
            "provenance_ref": "raw-demo",
        }
        obj = c.FactView.model_validate(fact)
        self.assertEqual(obj, c.FactView.model_validate_json(obj.model_dump_json()))
        with self.assertRaises(ValidationError):
            c.FactView.model_validate(fact | {"status": "unknown"})
        c.ScoreItem(item="D1", status="unknown", grade=None, points=None, fact_ids=[])
        with self.assertRaises(ValidationError):
            c.ScoreItem(item="D1", status="unknown", grade=0, points=0.0, fact_ids=[])

    def test_api_example(self):
        document = (Path(__file__).resolve().parents[2] / "docs/API_CONTRACT.md").read_text(
            encoding="utf-8"
        )
        section = document.split("## 새 결과 형태(PR7 전환 후)", 1)[1]
        example = json.loads(re.search(r"```json\s*(.*?)\s*```", section, re.S).group(1))
        result = s.DecisionResult.model_validate_json(json.dumps(example, ensure_ascii=False))
        self.assertEqual(result, s.DecisionResult.model_validate_json(result.model_dump_json()))

    def test_output_model_roundtrips(self):
        document = (Path(__file__).resolve().parents[2] / "docs/API_CONTRACT.md").read_text(
            encoding="utf-8"
        )
        section = document.split("## 새 결과 형태(PR7 전환 후)", 1)[1]
        result = json.loads(re.search(r"```json\s*(.*?)\s*```", section, re.S).group(1))
        final = result["top5"][0]
        summary = {name: final[name] for name in c.ScorecardSummary.model_fields}
        selection = {
            "basis": "code_lower_top10",
            "code_score_snapshot_id": "scores",
            "code_lower_rank": 1,
            "reason": "코드 하한 순위",
        }
        l_record = {
            "industry_code": "I201",
            "selection": selection,
            "review_state": "reviewed",
            "status": "observed",
            "grade": 2,
            "checked_questions": ["새 요인이 있나?"],
            "tool_call_ids": ["call-demo"],
        }
        issue = {
            "issue_id": "issue",
            "target": "L",
            "kind": "missing_evidence",
            "comment": "확인 필요",
            "fact_ids": [FACT],
            "suggested_check": "지도 확인",
        }
        request = {
            "request_id": "request-demo",
            "run_id": "run-demo",
            "snapshot_id": "snapshot-demo",
            "site": {
                "input_address": "서울 목업",
                "road_address": "서울 목업",
                "latitude": 37.5,
                "longitude": 127.0,
            },
        }
        score = {"item": "D1", "status": "unknown", "grade": None, "points": None, "fact_ids": []}
        card = summary | {
            "items": [
                score | {"item": item}
                for item in ("D1", "D2", "D3", "D4", "C1", "C4", "S1", "S2", "S3", "S4", "L")
            ]
        }
        place = {
            "place_id": "p",
            "name": "목업 학교",
            "kakao_category": "학교",
            "distance_fact_id": FACT,
            "match_status": "category_match",
            "match_rule_id": "rule-1",
            "fact_ids": [FACT],
        }
        map_result = {
            "observation_id": "map-demo",
            "places": [place],
            "coverage": 1.0,
            "has_more": False,
        }
        interpretation = {
            "claim": "확인 필요",
            "fact_ids": [FACT],
            "conditions": [],
            "confidence": "medium",
        }
        restriction = {
            "industry_code": "I201",
            "status": "unknown",
            "scope": "unknown",
            "fact_ids": [],
        }
        raw_row = {"raw_row_refs": ["raw"], "values": {"store_count": 1}, "fact_ids": [FACT]}
        examples = {
            c.ToolError: {"code": "TIMEOUT", "message": "시간 초과"},
            c.ToolReply[c.MapResult]: {"status": "ok", "data": map_result},
            s.Evidence: {"fact_id": FACT},
            c.FactView: result["facts"][0],
            c.ScoreItem: score,
            c.ScorecardSummary: summary,
            c.Scorecard: card,
            c.TextSegment: {"type": "text", "text": "목업"},
            c.FactReferenceSegment: {"type": "fact", "fact_id": FACT, "format": "count"},
            c.Candidate: {"industry_code": "I201"},
            c.LSelection: selection,
            c.NewFactor: {"direction": "neutral", "claim": "확인됨", "fact_ids": [FACT]},
            c.LRecord: l_record,
            c.ReviewIssue: issue,
            c.ReviewResolution: {
                "issue_id": "issue",
                "disposition": "accepted",
                "reason": "근거 확인",
            },
            c.ReportProposal: {"candidates": [{"industry_code": "I201"}], "L_records": [l_record]},
            c.ScorecardResult: {"summaries": [summary]},
            c.FactsResult: {"facts": result["facts"]},
            c.RawQueryRow: raw_row,
            c.RawQueryResult: {"columns": ["store_count"], "rows": [raw_row]},
            c.MapPlace: place,
            c.MapResult: map_result,
            c.IndustryRestriction: restriction,
            c.RegulationResult: {
                "status": "error",
                "queried_at": "2026-10-14",
                "contains_verified": False,
                "zones": [],
                "fact_ids": [],
                "industry_restrictions": [restriction],
            },
            c.AdvisorInterpretation: interpretation,
            c.AdvisorAnswer: {
                "consult_id": "a",
                "status": "ok",
                "interpretations": [interpretation],
            },
            c.QuestionSessionRef: {"question_session_id": "q"},
            c.SubmitResult: {
                "report_id": "report",
                "validation_status": "valid",
                "rendered_preview_ref": "preview",
                "score_snapshot_id": "scores",
            },
            c.ReviewRef: {"review_id": "review"},
            s.DecisionRequest: request,
            c.FinalCandidate: final,
            c.EvaluatorReview: result["evaluator_reviews"][0],
            s.DecisionResult: result,
            s.QuestionSnapshot: {
                "request": request,
                "score_snapshot_id": "scores",
                "question_session_id": "q",
                "questions": [{"field": "floor", "question": "층?", "reason": "동선"}],
            },
            c.UserQuestion: {"field": "floor", "question": "층?", "reason": "동선"},
        }
        for model, payload in examples.items():
            with self.subTest(model=model.__name__):
                instance = model.model_validate(payload)
                self.assertEqual(instance, model.model_validate_json(instance.model_dump_json()))
                with self.assertRaises(ValidationError):
                    model.model_validate(payload | {"extra": True})

    def test_failures_remain_unknown(self):
        with self.assertRaises(ValidationError):
            c.ToolReply[c.MapResult](status="error", data=None, error=None)
        with self.assertRaises(ValidationError):
            c.MapPlace(
                place_id="p",
                name="점포",
                kakao_category="상점",
                distance_fact_id=FACT,
                match_status="same",
                fact_ids=[FACT],
            )
        with self.assertRaises(ValidationError):
            c.RegulationResult(
                status="error",
                queried_at="now",
                contains_verified=False,
                zones=[],
                fact_ids=[],
                industry_restrictions=[
                    {"industry_code": "I201", "status": "해당 없음", "scope": "none"}
                ],
            )
        with self.assertRaises(ValidationError):
            c.EvaluatorReview(actor="examiner", status="failed", verdict="agree", issues=[])

    def test_sdk_function_shape(self):
        from openai.types.chat import ChatCompletionFunctionToolParam
        from pydantic import TypeAdapter

        adapter = TypeAdapter(ChatCompletionFunctionToolParam)
        for definition in c.tool_definitions():
            self.assertEqual(adapter.validate_python(definition), definition)

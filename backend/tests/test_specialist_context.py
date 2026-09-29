"""축약 입력이 원본 수치와 업종 근거를 보존하는지 확인합니다."""

import importlib.util
import unittest

from app.schemas import AgentAnalysis, AnalysisTask, DecisionRequest, Finding, Scope, Site


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("app.evidence"))
        from app.agents.decision.context import build_context
        from app.evidence import validate_findings

        self.build_context, self.validate_findings = build_context, validate_findings
        self.data = {
            "by_middle": [
                {"code": "I201", "count": 0, "lq": 2.31, "citable": {"lq": False}},
                {"code": "I202", "count": 7, "lq": 1.234},
            ]
        }
        self.source = AgentAnalysis(
            request_id="r",
            agent_id="commercial_area",
            status="ok",
            scope=Scope(area="반경", period="분기"),
            data=self.data,
        )

    def finding(self, path, claim="점포 7개", code="I202"):
        return Finding(claim=claim, signal="context", industry_code=code, evidence=[{"path": path}])

    def test_digest_keeps_all_industries_and_zero(self):
        request = DecisionRequest(request_id="r", address="주소", analyses=[self.source])
        context = self.build_context(request, briefs=[], answers=[])
        rows = {row["code"]: row for row in context["industry_digest"]}
        self.assertEqual(len(rows), 75)
        metrics = rows["I201"]["metrics"]
        self.assertTrue(any(m["path"] == "/by_middle/0/count" and m["value"] == 0 for m in metrics))
        self.assertFalse(any(m["path"].endswith("/lq") for m in metrics))
        self.assertEqual(rows["I203"]["metrics"], [])
        self.assertNotIn("analyses", context)
        self.assertEqual(self.source.data, self.data)

    def test_invalid_or_other_industry_and_parent_bypass_dropped(self):
        bad = [
            self.finding("/by_middle/0/count"),
            self.finding("/by_middle/0/lq", code="I201"),
            self.finding("/by_middle/0", code="I201"),
            self.finding("/missing"),
        ]
        valid, warnings = self.validate_findings(bad, agent_id="commercial_area", data=self.data)
        self.assertEqual(valid, [])
        self.assertEqual(len(warnings), 4)

    def test_radius_metrics_keep_their_own_scope(self):
        source = self.source.model_copy(
            update={
                "data": {
                    "radius_m": 500,
                    "by_middle": [{"code": "I202", "count": 30}],
                    "by_radius": [
                        {"radius_m": 100, "top_by_count": [{"code": "I202", "count": 7}]}
                    ],
                }
            }
        )
        context = self.build_context(
            DecisionRequest(request_id="r", address="주소", analyses=[source]),
            briefs=[],
            answers=[],
        )
        row = next(r for r in context["industry_digest"] if r["code"] == "I202")
        metric = next(m for m in row["metrics"] if m["value"] == 7)
        self.assertEqual(metric["radius_m"], {"path": "/by_radius/0/radius_m", "value": 100})

    def test_number_rounding_without_percentage_rescaling(self):
        findings = [
            self.finding("/by_middle/1/count"),
            self.finding("/by_middle/1/lq", "LQ 1.23배"),
            self.finding("/by_middle/1/lq", "LQ 123.4%"),
            self.finding("/by_middle/1/count", "점포 9개"),
        ]
        valid, warnings = self.validate_findings(
            findings, agent_id="commercial_area", data=self.data
        )
        self.assertEqual([f.claim for f in valid], ["점포 7개", "LQ 1.23배"])
        self.assertEqual(len(warnings), 2)

    def test_attached_korean_number_is_not_skipped(self):
        valid, _ = self.validate_findings(
            [self.finding("/by_middle/1/count", "점포9개")],
            agent_id="commercial_area",
            data=self.data,
        )
        self.assertEqual(valid, [])
        valid, _ = self.validate_findings(
            [self.finding("/by_middle/1/count", "2026-09-29 I202 점포 7개")],
            agent_id="commercial_area",
            data=self.data,
        )
        self.assertEqual(len(valid), 1)

    def test_context_preserves_population_types_and_units(self):
        source = self.source.model_copy(
            update={
                "agent_id": "floating_population",
                "data": {
                    "population": {"daily_avg": 120, "unit": "명/일"},
                    "resident": {"count": 100, "unit": "명"},
                    "worker": {"count": 30, "unit": "명"},
                },
            }
        )
        context = self.build_context(
            DecisionRequest(request_id="r", address="주소", analyses=[source]),
            briefs=[],
            answers=[],
        )
        values = {v["path"]: v["value"] for v in context["neighborhood"]}
        self.assertEqual(values["/population/daily_avg"], 120)
        self.assertEqual(values["/resident/count"], 100)
        self.assertEqual(values["/worker/count"], 30)
        self.assertEqual(values["/population/unit"], "명/일")

    def test_wrong_unit_cannot_reuse_a_matching_number(self):
        valid, _ = self.validate_findings(
            [self.finding("/by_middle/1/count", "점포 7명")],
            agent_id="commercial_area",
            data=self.data,
        )
        self.assertEqual(valid, [])

    def test_lifecycle_rate_basis_is_preserved_from_real_nested_field(self):
        data = {
            "scoring_method": {"rate_basis": {"unit": "%/분기", "annualized": False}},
            "industries": [{"industry_code": "I201", "metrics": {"recent_year_close_rate": 3.5}}],
        }
        source = self.source.model_copy(update={"agent_id": "business_lifecycle", "data": data})
        context = self.build_context(
            DecisionRequest(request_id="r", address="주소", analyses=[source]),
            briefs=[],
            answers=[],
        )
        self.assertEqual(context["sources"][0]["rate_basis"], data["scoring_method"]["rate_basis"])
        valid, _ = self.validate_findings(
            [
                self.finding(
                    "/industries/0/metrics/recent_year_close_rate",
                    "분기 평균 폐업 비율 3.5%",
                    "I201",
                )
            ],
            agent_id="business_lifecycle",
            data=data,
        )
        self.assertEqual(len(valid), 1)

    def test_fallback_includes_both_score_extremes(self):
        from app.agents.specialists.tools import fallback_brief
        from app.industries.catalog import INDUSTRIES
        from app.mocks import mock_site

        data = {
            "industries": [
                {"industry_code": code, "score": i + 1} for i, code in enumerate(INDUSTRIES)
            ]
        }
        source = self.source.model_copy(update={"agent_id": "business_lifecycle", "data": data})
        brief = fallback_brief(AnalysisTask(request_id="r", site=mock_site()), source)
        paths = {ref.path for f in brief.findings for ref in f.evidence}
        self.assertIn("/industries/74/score", paths)
        self.assertIn("/industries/0/score", paths)

    def test_fallback_has_real_paths_and_is_not_model_output(self):
        from app.agents.specialists.tools import fallback_brief

        task = AnalysisTask(
            request_id="r",
            site=Site(input_address="주소", road_address="주소", latitude=37.5, longitude=127.0),
        )
        brief = fallback_brief(task, self.source)
        self.assertEqual(brief.source, "fallback")
        self.assertTrue(brief.limitations)
        valid, _ = self.validate_findings(brief.findings, agent_id=brief.agent_id, data=self.data)
        self.assertEqual(valid, brief.findings)


class ContextNumberTests(unittest.TestCase):
    def test_radius_and_period_words_are_context_not_metrics(self):
        from app.evidence import validate_findings

        data = {
            "lq_baseline": {"applied_radius_m": 2000},
            "by_middle": [{"code": "Q102", "count": 51, "lq": 1.8664}],
        }

        def check(claim):
            finding = Finding(
                claim=claim,
                signal="context",
                industry_code="Q102",
                evidence=[{"path": "/by_middle/0/count"}, {"path": "/by_middle/0/lq"}],
            )
            return len(validate_findings([finding], agent_id="commercial_area", data=data)[0])

        self.assertEqual(check("의원 51개, 반경 2,000m 대비 lq 1.8664, 최근 12개 분기"), 1)
        # 원자료에 없는 반경이나 틀린 지표 숫자는 여전히 거절합니다.
        self.assertEqual(check("의원 51개, 반경 300m 대비 lq 1.8664"), 0)
        self.assertEqual(check("의원 52개, 반경 2,000m 대비"), 0)

    def test_band_labels_pass_but_self_computed_numbers_fail(self):
        from app.evidence import validate_findings

        data = {
            "population": {"daily_avg": 43440.7, "unit": "명/일", "age_share": {"10": 0.1967}},
        }

        def check(claim, path):
            finding = Finding(claim=claim, signal="context", evidence=[{"path": path}])
            return len(validate_findings([finding], agent_id="floating_population", data=data)[0])

        self.assertEqual(check("일평균 유동인구는 43,440.7명입니다.", "/population/daily_avg"), 1)
        self.assertEqual(check("10대 비중은 0.1967입니다.", "/population/age_share/10"), 1)
        self.assertEqual(check("유동인구는 43,440.7명의 2배입니다.", "/population/daily_avg"), 0)

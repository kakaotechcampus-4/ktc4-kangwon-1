"""축약 입력이 원본 수치와 업종 근거를 보존하는지 확인합니다."""

import importlib.util
import unittest

from app.agents.commercial_area.schemas import (
    CategoryRank,
    RadiusSlice,
    SliceExplanations,
)
from app.evidence import validate_findings
from app.industries import lookup
from app.industries.catalog import INDUSTRIES
from app.mocks import (
    mock_business_lifecycle_data,
    mock_commercial_area_data,
    mock_floating_population_data,
)
from app.schemas import (
    AgentAnalysis,
    AnalysisTask,
    DecisionRequest,
    EvidenceRef,
    Finding,
    Scope,
    Site,
)


def site_task():
    return AnalysisTask(
        request_id="r",
        site=Site(input_address="주소", road_address="주소", latitude=37.5, longitude=127.0),
    )


class ContextTests(unittest.TestCase):
    def test_finding_numbers_are_rendered_and_long_results_dropped(self):
        data = mock_commercial_area_data()
        path = "/by_middle/0/count"
        ok = Finding(
            claim="점포 {0}개",
            signal="context",
            industry_code="SV020",
            evidence=[EvidenceRef(path=path)],
        )
        long = Finding(
            claim="가" * 197 + "{0}",
            signal="context",
            industry_code="SV020",
            evidence=[EvidenceRef(path="/by_middle/0/lq")],
        )
        bare = ok.model_copy(update={"claim": "점포가 96개"})
        valid, warnings = validate_findings([ok, long, bare], agent_id="commercial_area", data=data)
        self.assertEqual([f.claim for f in valid], ["점포 96개"])
        self.assertEqual(len(warnings), 2)

    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec("app.evidence"))
        from app.agents.decision.context import build_context

        self.build_context, self.validate_findings = build_context, validate_findings
        self.data = mock_commercial_area_data()
        self.data["by_middle"][0].update(count=0, citable={"lq": False})
        self.data["by_middle"][1].update(count=7, lq=1.234)
        self.source = AgentAnalysis(
            request_id="r",
            agent_id="commercial_area",
            status="ok",
            scope=Scope(area="반경", period="분기"),
            data=self.data,
        )

    def finding(self, path, claim="점포 {0}개", code="SV026"):
        return Finding(claim=claim, signal="context", industry_code=code, evidence=[{"path": path}])

    def test_digest_keeps_all_industries_and_zero(self):
        request = DecisionRequest(request_id="r", address="주소", analyses=[self.source])
        context = self.build_context(request, briefs=[], answers=[])
        rows = {row["code"]: row for row in context["industry_digest"]}
        self.assertEqual(len(rows), 51)
        metrics = rows["SV020"]["metrics"]
        self.assertTrue(any(m["path"] == "/by_middle/0/count" and m["value"] == 0 for m in metrics))
        self.assertFalse(any(m["path"].endswith("/lq") for m in metrics))
        self.assertEqual(rows["SV022"]["metrics"], [])
        self.assertNotIn("analyses", context)
        self.assertEqual(self.source.data, self.data)

    def test_rendered_brief_findings_survive_context_building(self):
        from app.agents.specialists.tools import fallback_brief

        brief = fallback_brief(site_task(), self.source)
        self.assertTrue(brief.findings)
        context = self.build_context(
            DecisionRequest(request_id="r", address="주소", analyses=[self.source]),
            briefs=[brief],
            answers=[],
        )
        self.assertEqual(
            [f["claim"] for f in context["briefs"][0]["findings"]],
            [f.claim for f in brief.findings],
        )

    def test_invalid_or_other_industry_and_parent_bypass_dropped(self):
        bad = [
            self.finding("/by_middle/0/count"),
            self.finding("/by_middle/0/lq", code="SV020"),
            self.finding("/by_middle/0", code="SV020"),
            self.finding("/missing"),
        ]
        valid, warnings = self.validate_findings(bad, agent_id="commercial_area", data=self.data)
        self.assertEqual(valid, [])
        self.assertEqual(len(warnings), 4)

    def test_radius_metrics_keep_their_own_scope(self):
        industry = lookup.get("SV026")
        slice_ = RadiusSlice(
            radius_m=100,
            store_total=40,
            category_count=10,
            absent_category_count=65,
            top_by_count=[
                CategoryRank(
                    rank=1,
                    code="SV026",
                    name=industry.name,
                    count=7,
                    density_per_km2=222.8,
                    note="반경 안 최다",
                )
            ],
            explanations=SliceExplanations(
                store_total="점포",
                top="최다",
                bottom="최소",
                concentration="집중",
                specialization="특화",
            ),
        )
        data = {**self.data, "by_radius": [slice_.model_dump()]}
        data["by_middle"][1]["count"] = 30
        source = self.source.model_copy(update={"data": data})
        context = self.build_context(
            DecisionRequest(request_id="r", address="주소", analyses=[source]),
            briefs=[],
            answers=[],
        )
        row = next(r for r in context["industry_digest"] if r["code"] == "SV026")
        metric = next(m for m in row["metrics"] if m["value"] == 7)
        self.assertEqual(metric["radius_m"], {"path": "/by_radius/0/radius_m", "value": 100})

    def test_placeholder_units_follow_the_path(self):
        findings = [
            self.finding("/by_middle/1/count"),
            self.finding("/by_middle/1/lq", "LQ {0}배"),
            self.finding("/by_middle/1/lq", "LQ {0}%"),
            self.finding("/by_middle/1/count", "점포 9개"),
        ]
        valid, warnings = self.validate_findings(
            findings, agent_id="commercial_area", data=self.data
        )
        self.assertEqual([f.claim for f in valid], ["점포 7개", "LQ 1.234배"])
        self.assertEqual(len(warnings), 2)

    def test_bare_numbers_in_words_dates_or_codes_are_rejected(self):
        for claim in ("점포9개", "2026-09-29 I212 점포 {0}개"):
            valid, _ = self.validate_findings(
                [self.finding("/by_middle/1/count", claim)],
                agent_id="commercial_area",
                data=self.data,
            )
            self.assertEqual(valid, [], claim)

    def test_context_preserves_population_types_and_units(self):
        data = mock_floating_population_data()
        source = self.source.model_copy(update={"agent_id": "floating_population", "data": data})
        context = self.build_context(
            DecisionRequest(request_id="r", address="주소", analyses=[source]),
            briefs=[],
            answers=[],
        )
        values = {v["path"]: v["value"] for v in context["neighborhood"]}
        self.assertEqual(values["/population/daily_avg"], data["population"]["daily_avg"])
        self.assertEqual(values["/resident/count"], data["resident"]["count"])
        self.assertEqual(values["/worker/count"], data["worker"]["count"])
        self.assertEqual(values["/population/unit"], data["population"]["unit"])

    def test_wrong_unit_cannot_reuse_a_matching_number(self):
        valid, _ = self.validate_findings(
            [self.finding("/by_middle/1/count", "점포 {0}명")],
            agent_id="commercial_area",
            data=self.data,
        )
        self.assertEqual(valid, [])

    def test_lifecycle_rate_basis_is_preserved_from_real_nested_field(self):
        data = mock_business_lifecycle_data()
        data["scoring_method"] = {"rate_basis": {"unit": "%/분기", "annualized": False}}
        data["industries"][0]["metrics"]["recent_year_close_rate"] = 3.5
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
                    "분기 평균 폐업 비율 {0}%",
                    "SV020",
                )
            ],
            agent_id="business_lifecycle",
            data=data,
        )
        self.assertEqual([f.claim for f in valid], ["분기 평균 폐업 비율 3.5%"])

    def test_fallback_includes_both_score_extremes(self):
        from app.agents.specialists.tools import fallback_brief

        data = mock_business_lifecycle_data()
        template = data["industries"][0]
        data["industries"] = [
            {**template, "industry_id": code, "industry_name": name, "score": float(i + 1)}
            for i, (code, name) in enumerate(INDUSTRIES.items())
        ]
        source = self.source.model_copy(update={"agent_id": "business_lifecycle", "data": data})
        brief = fallback_brief(site_task(), source)
        paths = {ref.path for f in brief.findings for ref in f.evidence}
        self.assertIn("/industries/50/score", paths)
        self.assertIn("/industries/0/score", paths)

    def test_fallback_has_real_paths_and_is_not_model_output(self):
        from app.agents.specialists.tools import fallback_brief

        brief = fallback_brief(site_task(), self.source)
        self.assertEqual(brief.source, "fallback")
        self.assertTrue(brief.limitations)
        self.assertTrue(brief.findings)
        self.assertTrue(all("{" not in f.claim for f in brief.findings))


class ContextNumberTests(unittest.TestCase):
    def test_radius_must_be_cited_not_written(self):
        data = mock_commercial_area_data()
        data["lq_baseline"]["applied_radius_m"] = 2000
        paths = ["/by_middle/1/count", "/by_middle/1/lq", "/lq_baseline/applied_radius_m"]

        def check(claim):
            finding = Finding(
                claim=claim,
                signal="context",
                industry_code="SV026",
                evidence=[{"path": p} for p in paths],
            )
            return len(validate_findings([finding], agent_id="commercial_area", data=data)[0])

        self.assertEqual(check("음료점 {0}개, 반경 {2}m 대비 LQ {1}배"), 1)
        # 원자료에 없는 반경이나 틀린 지표 숫자는 여전히 거절합니다.
        self.assertEqual(check("음료점 {0}개, 반경 300m 대비 LQ {1}배"), 0)
        self.assertEqual(check("음료점 {0}개, 최근 12개 분기"), 0)

    def test_band_labels_pass_but_self_computed_numbers_fail(self):
        data = mock_floating_population_data()

        def check(claim, path):
            finding = Finding(claim=claim, signal="context", evidence=[{"path": path}])
            return len(validate_findings([finding], agent_id="floating_population", data=data)[0])

        self.assertEqual(check("일평균 유동인구는 {0}명입니다.", "/population/daily_avg"), 1)
        self.assertEqual(check("10대 비중은 {0}입니다.", "/population/age_share/10"), 1)
        self.assertEqual(check("유동인구는 {0}명의 2배입니다.", "/population/daily_avg"), 0)


if __name__ == "__main__":
    unittest.main()

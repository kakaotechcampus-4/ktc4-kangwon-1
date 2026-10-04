"""질문별 동종 판단과 지도 인용 연결의 회귀 시험입니다."""

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from test_map_mapping import plan, task

from app.industries.lookup import get
from app.schemas import MapLookupPlan, MapObservation


def observation():
    queries = {}
    industries = {}
    for i, code in enumerate(("I212", "I210"), 1):
        query = plan().queries[0].model_dump()
        query.update(industry_code=code)
        queries[f"q{i}"] = dict(
            request=query,
            status="ok",
            method="keyword",
            total_count=1,
            place_ids=["x"],
            matches={"x": "same"},
        )
        industries[code] = dict(
            name=get(code).name, major=get(code).major_name, place_ids=["x"], sampled_count=1
        )
    return dict(
        request_id=task().request_id,
        observation_id="test",
        site=task().site.model_dump(),
        radius_m=300,
        queried_at="2026-10-02T00:00:00+00:00",
        master_version="test",
        status="ok",
        data=dict(
            queries=queries,
            places={"x": dict(name="시험 카페", distance_m=10, category_name="음식점 > 카페")},
            industries=industries,
        ),
    )


class MatchingContractTests(unittest.TestCase):
    def test_citations_are_valid_bounded_and_escape_place_ids(self):
        import random

        from app.evidence import map_citations, valid_map_path

        for seed in range(5):
            rng = random.Random(seed)
            raw = observation()["data"]
            ids = [f"x/{i}~" for i in range(15)]
            raw["places"] = {
                pid: {
                    "name": "시험",
                    "category_name": "음식점 > 카페",
                    "distance_m": rng.randrange(1000),
                    "mapping_status": "not_applicable",
                }
                for pid in ids
            }
            for group in raw["industries"].values():
                group.update(place_ids=ids, sampled_count=15)
            for query in raw["queries"].values():
                query.update(place_ids=ids, matches=dict.fromkeys(ids, "same"), total_count=15)
            raw = MapObservation.model_validate({**observation(), "data": raw}).data.model_dump()
            citations = map_citations(raw)
            for code, rows in citations.items():
                self.assertTrue(all(valid_map_path(x["path"], code, raw) for x in rows))
                distances = [x["value"] for x in rows if x["path"].endswith("/distance_m")]
                self.assertEqual(
                    distances, sorted(p["distance_m"] for p in raw["places"].values())[:10]
                )
                self.assertTrue(any("~1" in x["path"] and "~0" in x["path"] for x in rows))

    def test_bad_map_paths_report_safe_reasons(self):
        from app.evidence import validate_findings
        from app.schemas import Finding

        for path, reason in (
            ("/queries/q2/total_count", "필드"),
            ("/places/x/category_name", "필드"),
            ("/data/places/x/name", "형식"),
            ("/places/missing/name", "없음"),
            ("/other/x/name", "구역"),
        ):
            finding = Finding(
                claim="확인", signal="context", industry_code="I212", evidence=[{"path": path}]
            )
            kept, warnings = validate_findings(
                [finding], agent_id="map_analysis", data=observation()["data"]
            )
            self.assertEqual(kept, [])
            self.assertEqual(warnings, [f"전문가 근거 제외: 1번 경로·업종 불일치(지도: {reason})"])
            self.assertNotIn(path, warnings[0])

    def test_generated_terms_preserve_csv_order_and_unlinked_industries(self):
        from app.industries import lookup

        terms = lookup.industry_terms("P105")
        self.assertEqual(terms["name"], "일반 교육기관")
        self.assertIn("일반교습학원", terms["includes"])
        self.assertEqual(len(terms["includes"]), len(set(terms["includes"])))
        terms["includes"].clear()
        self.assertTrue(lookup.industry_terms("P105")["includes"])
        self.assertEqual(lookup.industry_terms("Q101")["includes"], [])

    def test_shared_place_and_old_observation_are_valid(self):
        from app.evidence import valid_map_path

        raw = observation()
        parsed = MapObservation.model_validate(raw)
        self.assertEqual(set(parsed.data.industries), {"I212", "I210"})
        del raw["data"]["queries"]["q2"]
        del raw["data"]["industries"]["I210"]
        del raw["data"]["queries"]["q1"]["matches"]
        raw["data"]["places"]["x"].update(
            mapping_status="mapped", industry_code="I212", mapping_method="llm"
        )
        old = MapObservation.model_validate(raw)
        self.assertEqual(old.data.queries["q1"].matches, {})
        self.assertTrue(valid_map_path("/places/x/name", "I212", old.data.model_dump()))
        self.assertFalse(valid_map_path("/places/x/name", "I210", old.data.model_dump()))

    def test_invalid_matches_and_unclear_ok_are_rejected(self):
        for change in ("outside", "facility", "error", "unclear"):
            raw = observation()
            q = raw["data"]["queries"]["q1"]
            if change == "outside":
                q["matches"] = {"missing": "same"}
            elif change == "facility":
                q["request"] = dict(
                    kind="infrastructure",
                    facility_code="SW8",
                    why_needed="교통",
                    expected_impact="수요",
                )
            elif change == "error":
                q.update(status="error", error="TIMEOUT", total_count=None, place_ids=[])
            else:
                q["matches"] = {"x": "unclear"}
                del raw["data"]["industries"]["I212"]
            with self.subTest(change=change), self.assertRaises(ValidationError):
                MapObservation.model_validate(raw)
            if change == "unclear":
                raw["status"] = "partial"
                MapObservation.model_validate(raw)

    def test_eight_queries_allowed_nine_rejected(self):
        raw = plan().model_dump()
        raw["queries"] *= 8
        self.assertEqual(len(MapLookupPlan.model_validate(raw).queries), 8)
        raw["queries"].append(raw["queries"][0])
        with self.assertRaises(ValidationError):
            MapLookupPlan.model_validate(raw)
        observed = observation()
        query = observed["data"]["queries"]["q1"]
        observed["data"]["queries"].update({f"q{i}": query for i in range(3, 9)})
        MapObservation.model_validate(observed)
        observed["data"]["queries"]["q9"] = query
        with self.assertRaises(ValidationError):
            MapObservation.model_validate(observed)


class MatchingObserveTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_expert_uses_fresh_citations_and_context_keeps_place_paths(self):
        from types import SimpleNamespace

        from app.agents.decision.context import build_context
        from app.agents.orchestration.consult import build_specialist_tools
        from app.agents.specialists.agent import answer_query
        from app.api.v1 import mock
        from app.evidence import valid_map_path
        from app.mocks import mock_agents
        from app.schemas import DecisionRequest, SpecialistQuery

        context = {}
        query = SpecialistQuery(
            agent_id="map_analysis",
            question="동종 확인",
            industry_codes=["I212"],
            why_needed="경쟁",
            expected_impact="추천",
        )
        tools, context = build_specialist_tools(
            task(),
            "map_analysis",
            analyses=[],
            supplements=[],
            map_lookup=mock.map_observation,
            hooks=SimpleNamespace(on_map_requested=None, on_map_completed=None, on_map_result=None),
            state=context,
            query=query,
        )
        first = await tools["search_industry"].execute({"code": "I212", "query": "카페"})
        self.assertIn("I212", first["citations"])
        second = await tools["search_industry"].execute({"code": "I210", "query": "제과점"})
        self.assertEqual(set(second["citations"]), {"I210"})
        self.assertEqual(second["match_summary"], {"same": 1, "different": 0, "unclear": 0})
        cached = await tools["search_industry"].execute({"code": "I212", "query": "카페"})
        self.assertEqual(cached["citations"], first["citations"])

        async def generate(messages, definitions):
            payload = json.loads(messages[1]["content"])
            self.assertNotIn("industry_paths", payload)
            self.assertIn("I212", payload["industry_terms"])
            return await mock.specialist(messages, definitions)

        answer = await answer_query(
            task(),
            query,
            1,
            analysis=None,
            observation=context["map_observation"],
            generate=generate,
            tools=tools,
            get_data=lambda: context["map_observation"].data.model_dump(),
        )
        self.assertEqual(answer.status, "answered")
        analyses = [await agent(task()) for agent in mock_agents().values()]
        request = DecisionRequest(
            request_id=task().request_id,
            address="시험",
            analyses=analyses,
            map_observation=context["map_observation"],
        )
        payload = build_context(request, briefs=[], answers=[answer])
        rows = [r for r in payload["neighborhood"] if r["agent_id"] == "map_analysis"]
        self.assertTrue(any(r["path"].startswith("/places/") for r in rows))
        evidence = next(
            r
            for r in payload["industry_evidence"]
            if r["agent_id"] == "map_analysis" and r["industry_code"] == "I212"
        )
        self.assertTrue(any(p.startswith("/places/") for p in evidence["paths"]))
        self.assertTrue(
            all(
                valid_map_path(p, "I212", context["map_observation"].data.model_dump())
                for p in evidence["paths"]
            )
        )

    async def test_requery_keeps_same_places_before_adoption(self):
        from app.agents.orchestration.consult import map_adoptable

        old = MapObservation.model_validate(observation())
        raw = observation()
        raw["data"]["queries"]["q1"]["matches"]["x"] = "different"
        del raw["data"]["industries"]["I212"]
        self.assertFalse(map_adoptable(old, MapObservation.model_validate(raw)))
        self.assertTrue(map_adoptable(old, MapObservation.model_validate(observation())))

    async def test_single_decision_receives_all_terms_only_when_map_allowed(self):
        from app.agents.decision.agent import evaluate
        from app.mocks import mock_agents, mock_generate
        from app.schemas import DecisionRequest

        request = DecisionRequest(
            request_id=task().request_id,
            address="시험",
            analyses=[await f(task()) for f in mock_agents().values()],
        )
        for allowed in (True, False):

            def generate(prompt, raw, allowed=allowed):
                payload = json.loads(raw)
                self.assertEqual(len(payload.get("industry_terms", {})), 75 if allowed else 0)
                return mock_generate(prompt, raw)

            await evaluate(request, allow_map_lookup=allowed, generate=generate)

    async def test_ogeum_school_matches_are_question_specific(self):
        from app.agents.map_analysis.agent import observe

        page = json.loads((Path(__file__).parent / "fixtures/map_ogeum404.json").read_text("utf-8"))
        seen = []

        class Places:
            async def search_keyword(self, *args, **kwargs):
                self_filter = kwargs["category_group_code"]
                seen.append(self_filter)
                return page

        batches = []

        async def judge(_prompt, raw):
            pairs = json.loads(raw)["pairs"]
            batches.append(pairs)
            return {
                key: {
                    "status": "same"
                    if any(word in item["category"]["name"] for word in ("수학", "논술"))
                    else "unclear"
                    if item.get("place_names")
                    else "different",
                    "reason": "고정 자료의 동종 여부",
                }
                for key, item in pairs.items()
            }

        request = plan()
        request.queries[0].industry_code = "P105"
        request.queries[0].query = "수학학원"
        request.queries.append(request.queries[0].model_copy(update={"query": "입시학원"}))
        result = await observe(task(), request, client=Places(), generate_mapping=judge)
        self.assertEqual(result.data.industries["P105"].sampled_count, 2)
        self.assertEqual(len(result.data.places), 15)
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 13)
        self.assertEqual(seen, ["AC5", "AC5"])
        pairs = list(batches[0].values())
        self.assertEqual(sum(bool(x.get("place_names")) for x in pairs), 4)
        self.assertTrue(all(x["target"]["includes"] for x in pairs))
        self.assertTrue(all(p.industry_code is None for p in result.data.places.values()))
        from app.evidence import map_citations, valid_map_path, validate_findings
        from app.schemas import Finding

        data = result.data.model_dump()
        citations = map_citations(data)
        self.assertTrue(
            all(
                valid_map_path(row["path"], code, data)
                for code, rows in citations.items()
                for row in rows
            )
        )
        finding = Finding(
            claim="동종 표본 {0}개",
            signal="context",
            industry_code="P105",
            evidence=[{"path": citations["P105"][0]["path"]}],
        )
        self.assertEqual(
            validate_findings([finding], agent_id="map_analysis", data=data),
            ([finding.model_copy(update={"claim": "동종 표본 2개"})], []),
        )

    async def test_named_pairs_are_not_cached_and_different_is_cached(self):
        from app.agents.map_analysis.mapping import judge_matches

        calls = []
        pairs = {
            "specific": {"target": {"code": "P105"}, "category": {"name": "교육 > 학원 > 미술"}},
            "named": {
                "target": {"code": "P105"},
                "category": {"name": "교육 > 학원"},
                "place_names": ["시험 수학학원"],
            },
        }

        def judge(_prompt, raw):
            pending = json.loads(raw)["pairs"]
            calls.append(set(pending))
            return {
                key: {"status": "same" if key == "named" else "different", "reason": "시험"}
                for key in pending
            }

        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                await judge_matches(
                    pairs, generate=judge, cache_path=Path(folder) / "cache.sqlite3"
                )
        self.assertEqual(calls, [{"specific", "named"}, {"named"}])
